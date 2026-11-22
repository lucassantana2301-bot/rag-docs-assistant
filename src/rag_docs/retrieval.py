"""Busca híbrida: BM25 e vetores fundidos por Reciprocal Rank Fusion."""

from __future__ import annotations

from dataclasses import replace
from typing import Literal

from .embeddings import Embedder
from .models import SearchHit
from .store import Store

SearchMode = Literal["hybrid", "lexical", "vector"]

RRF_K = 60


def reciprocal_rank_fusion(
    rankings: list[list[SearchHit]], *, weights: list[float] | None = None, k: int = RRF_K
) -> list[SearchHit]:
    """
    RRF (Cormack et al., 2009): score = Σ peso / (k + posição).

    Usa só a posição, não o score bruto, por isso dispensa calibrar BM25 (sem teto) contra cosseno
    (entre -1 e 1). k=60 é o valor do artigo original e funciona bem sem ajuste.
    """
    weights = weights or [1.0] * len(rankings)
    fused: dict[int, float] = {}
    best: dict[int, SearchHit] = {}
    for ranking, weight in zip(rankings, weights, strict=True):
        for position, hit in enumerate(ranking, start=1):
            fused[hit.chunk_id] = fused.get(hit.chunk_id, 0.0) + weight / (k + position)
            previous = best.get(hit.chunk_id)
            best[hit.chunk_id] = (
                hit
                if previous is None
                else replace(
                    previous,
                    lexical_rank=previous.lexical_rank or hit.lexical_rank,
                    vector_rank=previous.vector_rank or hit.vector_rank,
                )
            )
    ordered = sorted(fused, key=lambda chunk_id: (-fused[chunk_id], chunk_id))
    return [replace(best[chunk_id], score=round(fused[chunk_id], 6)) for chunk_id in ordered]


def diversify(hits: list[SearchHit], limit: int, max_per_document: int) -> list[SearchHit]:
    """Limita chunks por documento: evita que um documento longo ocupe todo o contexto do LLM."""
    chosen: list[SearchHit] = []
    per_document: dict[int, int] = {}
    for hit in hits:
        if per_document.get(hit.document_id, 0) >= max_per_document:
            continue
        chosen.append(hit)
        per_document[hit.document_id] = per_document.get(hit.document_id, 0) + 1
        if len(chosen) == limit:
            break
    return chosen


class Retriever:
    def __init__(self, store: Store, embedder: Embedder, *, candidates: int = 30, max_per_document: int = 3) -> None:
        self._store = store
        self._embedder = embedder
        self._candidates = candidates
        self._max_per_document = max_per_document

    def search(self, query: str, *, limit: int = 5, mode: SearchMode = "hybrid") -> list[SearchHit]:
        if not query.strip():
            return []
        if mode == "lexical":
            ranked = self._store.lexical_search(query, self._candidates)
        elif mode == "vector":
            ranked = self._store.vector_search(self._embedder.embed([query])[0], self._candidates)
        else:
            lexical = self._store.lexical_search(query, self._candidates)
            vector = self._store.vector_search(self._embedder.embed([query])[0], self._candidates)
            ranked = reciprocal_rank_fusion([lexical, vector])
        return diversify(ranked, limit, self._max_per_document)
