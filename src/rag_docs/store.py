"""Índice em SQLite: FTS5 para busca lexical (BM25) e vetores em BLOB para busca semântica."""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from .embeddings import Vector
from .models import Chunk, DocumentInfo, DocumentNotFoundError, IndexMismatchError, SearchHit
from .text import tokenize

SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
  id INTEGER PRIMARY KEY,
  source TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  media_type TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  indexed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chunks (
  id INTEGER PRIMARY KEY,
  document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  ordinal INTEGER NOT NULL,
  heading TEXT NOT NULL,
  page INTEGER,
  text TEXT NOT NULL,
  embedding BLOB NOT NULL
);
CREATE INDEX IF NOT EXISTS chunks_document ON chunks(document_id);

-- remove_diacritics 2: "férias" encontra "ferias" e vice-versa.
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
  text, heading, title,
  content='',
  contentless_delete=1,
  tokenize='unicode61 remove_diacritics 2'
);
"""


class Store:
    """
    Thread-safe por lock: o SQLite aceita uma escrita por vez e a API do FastAPI roda handlers síncronos em
    threads. Para muitos milhões de chunks, troque por pgvector ou um banco vetorial: a interface é pequena.
    """

    def __init__(self, path: Path | str) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._lock = threading.RLock()
        self._matrix: Vector | None = None
        self._matrix_ids: list[int] = []

    def close(self) -> None:
        self._conn.close()

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            try:
                yield self._conn
                self._conn.commit()
            except BaseException:
                self._conn.rollback()
                raise
            finally:
                self._matrix = None

    def bind_embedder(self, name: str, dim: int) -> None:
        """Grava qual embedder gerou o índice. Vetores de modelos diferentes não são comparáveis."""
        with self._lock:
            row = self._conn.execute("SELECT value FROM meta WHERE key = 'embedder'").fetchone()
            expected = f"{name}:{dim}"
            if row is None:
                self._conn.execute("INSERT INTO meta (key, value) VALUES ('embedder', ?)", (expected,))
                self._conn.commit()
            elif row["value"] != expected:
                raise IndexMismatchError(
                    f"o índice foi criado com o embedder {row['value']} e a configuração atual é {expected}. "
                    "Apague o banco (ou use `rag reindex`) para reindexar com o novo modelo."
                )

    def find_by_source(self, source: str) -> DocumentInfo | None:
        with self._lock:
            row = self._conn.execute(
                """SELECT d.*, COUNT(c.id) AS chunk_count FROM documents d
                   LEFT JOIN chunks c ON c.document_id = d.id WHERE d.source = ? GROUP BY d.id""",
                (source,),
            ).fetchone()
        return _document(row) if row else None

    def replace_document(
        self,
        *,
        source: str,
        title: str,
        media_type: str,
        sha256: str,
        chunks: list[Chunk],
        embeddings: Vector,
    ) -> int:
        if len(chunks) != embeddings.shape[0]:
            raise ValueError("quantidade de chunks e embeddings diferente")
        now = datetime.now(UTC).isoformat(timespec="seconds")
        with self._transaction() as conn:
            existing = conn.execute("SELECT id FROM documents WHERE source = ?", (source,)).fetchone()
            if existing:
                self._delete_chunks(conn, existing["id"])
                conn.execute(
                    "UPDATE documents SET title = ?, media_type = ?, sha256 = ?, indexed_at = ? WHERE id = ?",
                    (title, media_type, sha256, now, existing["id"]),
                )
                document_id = int(existing["id"])
            else:
                cursor = conn.execute(
                    "INSERT INTO documents (source, title, media_type, sha256, indexed_at) VALUES (?, ?, ?, ?, ?)",
                    (source, title, media_type, sha256, now),
                )
                document_id = int(cursor.lastrowid or 0)
            for chunk, vector in zip(chunks, embeddings, strict=True):
                cursor = conn.execute(
                    "INSERT INTO chunks (document_id, ordinal, heading, page, text, embedding)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        document_id,
                        chunk.ordinal,
                        chunk.heading,
                        chunk.page,
                        chunk.text,
                        vector.astype(np.float32).tobytes(),
                    ),
                )
                conn.execute(
                    "INSERT INTO chunks_fts (rowid, text, heading, title) VALUES (?, ?, ?, ?)",
                    (cursor.lastrowid, chunk.text, chunk.heading, title),
                )
        return document_id

    @staticmethod
    def _delete_chunks(conn: sqlite3.Connection, document_id: int) -> None:
        ids = [row["id"] for row in conn.execute("SELECT id FROM chunks WHERE document_id = ?", (document_id,))]
        conn.executemany("DELETE FROM chunks_fts WHERE rowid = ?", [(i,) for i in ids])
        conn.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))

    def delete_document(self, document_id: int) -> None:
        with self._transaction() as conn:
            if conn.execute("SELECT 1 FROM documents WHERE id = ?", (document_id,)).fetchone() is None:
                raise DocumentNotFoundError(f"documento {document_id} não existe")
            self._delete_chunks(conn, document_id)
            conn.execute("DELETE FROM documents WHERE id = ?", (document_id,))

    def list_documents(self) -> list[DocumentInfo]:
        with self._lock:
            rows = self._conn.execute(
                """SELECT d.*, COUNT(c.id) AS chunk_count FROM documents d
                   LEFT JOIN chunks c ON c.document_id = d.id GROUP BY d.id ORDER BY d.source"""
            ).fetchall()
        return [_document(row) for row in rows]

    def stats(self) -> dict[str, int]:
        with self._lock:
            documents = self._conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
            chunks = self._conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        return {"documents": int(documents), "chunks": int(chunks)}

    def lexical_search(self, query: str, limit: int) -> list[SearchHit]:
        """
        BM25 do FTS5. A consulta do usuário nunca vai crua para o MATCH: cada termo vira uma string entre
        aspas, o que neutraliza a sintaxe do FTS5 (NEAR, *, :coluna) e impede erro ou injeção na consulta.
        """
        terms = list(dict.fromkeys(tokenize(query)))
        if not terms:
            return []
        match = " OR ".join(f'"{term}"' for term in terms)
        with self._lock:
            rows = self._conn.execute(
                """SELECT c.id AS chunk_id, c.document_id, d.source, d.title, c.heading, c.page, c.text,
                          bm25(chunks_fts, 1.0, 0.6, 0.4) AS rank
                   FROM chunks_fts JOIN chunks c ON c.id = chunks_fts.rowid JOIN documents d ON d.id = c.document_id
                   WHERE chunks_fts MATCH ? ORDER BY rank LIMIT ?""",
                (match, limit),
            ).fetchall()
        # bm25() do SQLite é negativo (menor = melhor); invertemos para "maior = melhor".
        return [_hit(row, -float(row["rank"]), lexical_rank=i + 1) for i, row in enumerate(rows)]

    def _load_matrix(self) -> tuple[Vector, list[int]]:
        if self._matrix is None:
            rows = self._conn.execute("SELECT id, embedding FROM chunks ORDER BY id").fetchall()
            self._matrix_ids = [int(row["id"]) for row in rows]
            if rows:
                self._matrix = np.vstack([np.frombuffer(row["embedding"], dtype=np.float32) for row in rows])
            else:
                self._matrix = np.zeros((0, 1), dtype=np.float32)
        return self._matrix, self._matrix_ids

    def vector_search(self, query_vector: Vector, limit: int) -> list[SearchHit]:
        """
        Busca exata por produto interno (vetores normalizados, logo é o cosseno).

        A matriz fica em cache até a próxima escrita. Exata e simples até ~1 milhão de chunks; acima disso,
        um índice aproximado (HNSW no pgvector, por exemplo) passa a valer a pena.
        """
        with self._lock:
            matrix, ids = self._load_matrix()
            if not ids:
                return []
            scores = matrix @ query_vector.astype(np.float32)
            top = np.argsort(-scores)[:limit]
            chosen = [(ids[i], float(scores[i])) for i in top]
            placeholders = ",".join("?" * len(chosen))
            rows = {
                int(row["chunk_id"]): row
                for row in self._conn.execute(
                    f"""SELECT c.id AS chunk_id, c.document_id, d.source, d.title, c.heading, c.page, c.text
                        FROM chunks c JOIN documents d ON d.id = c.document_id WHERE c.id IN ({placeholders})""",  # noqa: S608
                    [chunk_id for chunk_id, _ in chosen],
                )
            }
        return [_hit(rows[chunk_id], score, vector_rank=i + 1) for i, (chunk_id, score) in enumerate(chosen)]


def _document(row: sqlite3.Row) -> DocumentInfo:
    return DocumentInfo(
        id=int(row["id"]),
        source=row["source"],
        title=row["title"],
        media_type=row["media_type"],
        sha256=row["sha256"],
        chunk_count=int(row["chunk_count"]),
        indexed_at=row["indexed_at"],
    )


def _hit(
    row: sqlite3.Row, score: float, *, lexical_rank: int | None = None, vector_rank: int | None = None
) -> SearchHit:
    return SearchHit(
        chunk_id=int(row["chunk_id"]),
        document_id=int(row["document_id"]),
        source=row["source"],
        title=row["title"],
        heading=row["heading"],
        page=row["page"],
        text=row["text"],
        score=score,
        lexical_rank=lexical_rank,
        vector_rank=vector_rank,
    )
