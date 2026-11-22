from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from rag_docs.embeddings import HashingEmbedder
from rag_docs.models import DocumentNotFoundError, IndexMismatchError, SearchHit
from rag_docs.retrieval import diversify, reciprocal_rank_fusion
from rag_docs.service import RagService
from rag_docs.store import Store

from .conftest import make_settings


def hit(chunk_id: int, document_id: int = 1) -> SearchHit:
    return SearchHit(chunk_id, document_id, "doc.md", "Doc", "", None, "texto", 0.0)


def test_reingest_is_idempotent_and_update_replaces_chunks(empty_service: RagService) -> None:
    first = empty_service.ingest_bytes(b"# Guia\nO prazo de reembolso e de 30 dias.", "guia.md")
    again = empty_service.ingest_bytes(b"# Guia\nO prazo de reembolso e de 30 dias.", "guia.md")
    assert (first.status, again.status) == ("created", "unchanged")

    updated = empty_service.ingest_bytes(b"# Guia\nAgora o prazo e de 45 dias.", "guia.md")
    assert updated.status == "updated"
    assert updated.document_id == first.document_id
    assert empty_service.store.stats() == {"documents": 1, "chunks": 1}
    # O texto antigo some também do índice FTS (nada de resultado "fantasma").
    assert empty_service.search("reembolso", mode="lexical") == []
    assert empty_service.search("45 dias", mode="lexical")[0].text.endswith("45 dias.")


def test_delete_document(empty_service: RagService) -> None:
    result = empty_service.ingest_bytes(b"conteudo sobre ferias", "a.txt")
    empty_service.delete(result.document_id)
    assert empty_service.documents() == []
    assert empty_service.search("ferias") == []
    with pytest.raises(DocumentNotFoundError):
        empty_service.delete(result.document_id)


def test_index_refuses_a_different_embedder(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    RagService(settings).close()
    with pytest.raises(IndexMismatchError, match="reindexar"):
        RagService(settings, embedder=HashingEmbedder(dim=128))


@pytest.mark.parametrize(
    "query", ['" OR 1=1 --', "NEAR(a b)", "ferias*", "title:segredo", "'; DROP TABLE chunks; --", "   "]
)
def test_lexical_query_syntax_is_neutralized(empty_service: RagService, query: str) -> None:
    empty_service.ingest_bytes(b"politica de ferias", "f.txt")
    empty_service.search(query, mode="lexical")  # não pode lançar erro de sintaxe do FTS5
    assert empty_service.store.stats()["chunks"] == 1


def test_accent_insensitive_search(empty_service: RagService) -> None:
    empty_service.ingest_bytes("Política de férias e licença".encode(), "f.md")
    assert empty_service.search("ferias licenca", mode="lexical")
    assert empty_service.search("FÉRIAS", mode="lexical")


def test_rrf_rewards_agreement_between_rankings() -> None:
    fused = reciprocal_rank_fusion([[hit(1), hit(2), hit(3)], [hit(3), hit(2), hit(4)]])
    # 2 e 3 aparecem nas duas listas e ficam à frente de 1 (só primeiro numa lista).
    assert {h.chunk_id for h in fused[:2]} == {2, 3}
    assert fused[0].chunk_id == 3  # 1/61 + 1/63 > 2/62
    assert fused[0].score == pytest.approx(1 / 61 + 1 / 63, abs=1e-6)


def test_diversify_limits_chunks_per_document() -> None:
    hits = [hit(1, 1), hit(2, 1), hit(3, 1), hit(4, 2)]
    assert [h.chunk_id for h in diversify(hits, limit=3, max_per_document=2)] == [1, 2, 4]


def test_hashing_embedder_is_deterministic_and_normalized() -> None:
    embedder = HashingEmbedder(dim=256)
    a, b = embedder.embed(["reembolso de despesas", "reembolsos das despesas"])
    again = embedder.embed(["reembolso de despesas"])[0]
    assert np.allclose(a, again)
    assert np.linalg.norm(a) == pytest.approx(1.0, abs=1e-5)
    assert float(a @ b) > 0.5  # variações de forma ficam próximas
    assert float(a @ embedder.embed(["escala de plantão"])[0]) < 0.3


def test_vector_search_on_empty_store(tmp_path: Path) -> None:
    store = Store(tmp_path / "x.db")
    assert store.vector_search(np.ones(4, dtype=np.float32), 5) == []
    store.close()
