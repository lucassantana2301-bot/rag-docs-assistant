"""Avaliação offline da recuperação e das respostas com um conjunto de perguntas de referência."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .retrieval import SearchMode
from .service import RagService
from .text import fold


@dataclass(frozen=True, slots=True)
class GoldenCase:
    question: str
    expected_sources: frozenset[str]
    must_contain: tuple[str, ...] = ()
    answerable: bool = True


@dataclass(frozen=True, slots=True)
class RetrievalMetrics:
    mode: str
    k: int
    hit_rate: float
    mrr: float
    cases: int


@dataclass(frozen=True, slots=True)
class AnswerMetrics:
    cases: int
    faithful_citation_rate: float
    contains_rate: float
    correct_refusal_rate: float


def load_golden(path: Path) -> list[GoldenCase]:
    cases = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
            cases.append(
                GoldenCase(
                    question=raw["question"],
                    expected_sources=frozenset(raw.get("sources", [])),
                    must_contain=tuple(raw.get("must_contain", [])),
                    answerable=bool(raw.get("answerable", True)),
                )
            )
        except (json.JSONDecodeError, KeyError) as error:
            raise ValueError(f"{path}:{number}: linha inválida ({error})") from error
    return cases


def evaluate_retrieval(service: RagService, cases: list[GoldenCase], *, mode: SearchMode, k: int) -> RetrievalMetrics:
    """Hit rate@k (alguma fonte esperada no top k) e MRR (1/posição da primeira fonte certa)."""
    answerable = [c for c in cases if c.answerable]
    hits = 0
    reciprocal = 0.0
    for case in answerable:
        results = service.search(case.question, limit=k, mode=mode)
        for position, hit in enumerate(results, start=1):
            if hit.source in case.expected_sources:
                hits += 1
                reciprocal += 1 / position
                break
    total = len(answerable) or 1
    return RetrievalMetrics(mode, k, round(hits / total, 4), round(reciprocal / total, 4), len(answerable))


def evaluate_answers(service: RagService, cases: list[GoldenCase]) -> AnswerMetrics:
    """
    - citação fiel: a resposta cita pelo menos uma fonte esperada (e nada fora das recuperadas);
    - conteúdo: a resposta contém os fatos-chave (valor, prazo) da referência;
    - recusa correta: pergunta fora do escopo dos documentos recebe "não encontrei".
    """
    answerable = [c for c in cases if c.answerable]
    unanswerable = [c for c in cases if not c.answerable]
    faithful = 0
    contains = 0
    for case in answerable:
        answer = service.ask(case.question)
        if any(citation.source in case.expected_sources for citation in answer.citations):
            faithful += 1
        if all(fold(term) in fold(answer.text) for term in case.must_contain):
            contains += 1
    refusals = sum(1 for case in unanswerable if not service.ask(case.question).grounded)
    return AnswerMetrics(
        cases=len(cases),
        faithful_citation_rate=round(faithful / (len(answerable) or 1), 4),
        contains_rate=round(contains / (len(answerable) or 1), 4),
        correct_refusal_rate=round(refusals / (len(unanswerable) or 1), 4),
    )


def render_markdown(retrieval: list[RetrievalMetrics], answers: AnswerMetrics | None) -> str:
    lines = ["| Modo | k | Hit rate | MRR |", "| --- | --- | --- | --- |"]
    lines += [f"| {m.mode} | {m.k} | {m.hit_rate:.0%} | {m.mrr:.3f} |" for m in retrieval]
    if answers:
        lines += [
            "",
            "| Respostas | Valor |",
            "| --- | --- |",
            f"| Citam a fonte esperada | {answers.faithful_citation_rate:.0%} |",
            f"| Contêm os fatos-chave | {answers.contains_rate:.0%} |",
            f"| Recusam pergunta fora do escopo | {answers.correct_refusal_rate:.0%} |",
        ]
    return "\n".join(lines)
