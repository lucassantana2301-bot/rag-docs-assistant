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
class RetrievedSource:
    source: str
    heading: str
    score: float
    lexical_rank: int | None
    vector_rank: int | None
    relevant: bool


@dataclass(frozen=True, slots=True)
class CitedSource:
    number: int
    source: str
    heading: str
    excerpt: str
    expected: bool


@dataclass(frozen=True, slots=True)
class CaseResult:
    """Resultado de uma pergunta de referência, com o que foi recuperado e respondido."""

    question: str
    answerable: bool
    expected_sources: list[str]
    must_contain: list[str]
    retrieved: list[RetrievedSource]
    first_relevant_rank: int | None
    answer: str
    grounded: bool
    citations: list[CitedSource]
    cites_expected: bool
    contains_facts: bool

    @property
    def passed(self) -> bool:
        if not self.answerable:
            return not self.grounded
        return self.first_relevant_rank is not None and self.cites_expected and self.contains_facts


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


def evaluate_cases(service: RagService, cases: list[GoldenCase], *, k: int = 5) -> list[CaseResult]:
    """Detalha cada pergunta (busca híbrida + resposta) para o relatório navegável."""
    results: list[CaseResult] = []
    for case in cases:
        hits = service.search(case.question, limit=k, mode="hybrid")
        retrieved = [
            RetrievedSource(
                source=hit.source,
                heading=hit.heading,
                score=round(hit.score, 6),
                lexical_rank=hit.lexical_rank,
                vector_rank=hit.vector_rank,
                relevant=hit.source in case.expected_sources,
            )
            for hit in hits
        ]
        first_relevant = next((i for i, hit in enumerate(retrieved, start=1) if hit.relevant), None)
        answer = service.ask(case.question)
        citations = [
            CitedSource(
                number=c.number,
                source=c.source,
                heading=c.heading,
                excerpt=c.excerpt,
                expected=c.source in case.expected_sources,
            )
            for c in answer.citations
        ]
        results.append(
            CaseResult(
                question=case.question,
                answerable=case.answerable,
                expected_sources=sorted(case.expected_sources),
                must_contain=list(case.must_contain),
                retrieved=retrieved,
                first_relevant_rank=first_relevant,
                answer=answer.text,
                grounded=answer.grounded,
                citations=citations,
                cites_expected=any(c.expected for c in citations),
                contains_facts=all(fold(term) in fold(answer.text) for term in case.must_contain),
            )
        )
    return results


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
