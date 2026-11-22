from __future__ import annotations

import json
from pathlib import Path

import pytest

from rag_docs.cli import main
from rag_docs.evaluation import (
    AnswerMetrics,
    CaseResult,
    CitedSource,
    RetrievalMetrics,
    RetrievedSource,
    evaluate_cases,
    load_golden,
)
from rag_docs.report import render_html
from rag_docs.service import RagService

from .conftest import CORPUS, GOLDEN


def _case(**overrides: object) -> CaseResult:
    base: dict[str, object] = {
        "question": "Quantos dias posso vender?",
        "answerable": True,
        "expected_sources": ["politica-de-ferias.md"],
        "must_contain": ["10 dias"],
        "retrieved": [RetrievedSource("politica-de-ferias.md", "Abono", 0.03, 1, 2, True)],
        "first_relevant_rank": 1,
        "answer": "Até 10 dias [1].",
        "grounded": True,
        "citations": [CitedSource(1, "politica-de-ferias.md", "Abono", "trecho", True)],
        "cites_expected": True,
        "contains_facts": True,
    }
    base.update(overrides)
    return CaseResult(**base)  # type: ignore[arg-type]


def test_case_passes_only_with_source_citation_and_facts() -> None:
    assert _case().passed
    assert not _case(first_relevant_rank=None).passed
    assert not _case(cites_expected=False).passed
    assert not _case(contains_facts=False).passed


def test_out_of_scope_case_passes_only_when_refused() -> None:
    assert _case(answerable=False, grounded=False).passed
    assert not _case(answerable=False, grounded=True).passed


def test_evaluate_cases_details_every_question(corpus_service: RagService) -> None:
    cases = load_golden(GOLDEN)
    results = evaluate_cases(corpus_service, cases, k=5)
    assert [r.question for r in results] == [c.question for c in cases]
    answerable = [r for r in results if r.answerable]
    assert all(len(r.retrieved) <= 5 for r in results)
    assert sum(r.first_relevant_rank is not None for r in answerable) / len(answerable) >= 0.9
    assert all(not r.grounded for r in results if not r.answerable)


def test_html_escapes_corpus_and_question_content() -> None:
    hostile = '<script>alert("x")</script>'
    html = render_html(
        [RetrievalMetrics("hybrid", 5, 1.0, 1.0, 1)],
        AnswerMetrics(1, 1.0, 1.0, 1.0),
        [_case(question=hostile, answer=hostile, retrieved=[RetrievedSource(hostile, hostile, 0.1, 1, None, False)])],
        generator="extractive",
        generated_at="2026-11-22 22:00 UTC",
        revision="abcdef1234567",
    )
    assert hostile not in html
    assert "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;" in html
    assert "default-src 'none'" in html
    assert "abcdef1" in html and "abcdef12" not in html


def test_cli_writes_html_and_json_reports(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = str(tmp_path / "r.db")
    assert main(["--db", db, "ingest", str(CORPUS)]) == 0
    html_path, json_path = tmp_path / "site" / "index.html", tmp_path / "eval.json"
    code = main(["--db", db, "eval", str(GOLDEN), "--html", str(html_path), "--json-out", str(json_path)])
    assert code == 0
    assert "Perguntas aprovadas" in html_path.read_text(encoding="utf-8")
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert len(payload["cases"]) == len(load_golden(GOLDEN))
    assert {"passed", "retrieved", "citations"} <= payload["cases"][0].keys()
    assert "gravado:" in capsys.readouterr().err
