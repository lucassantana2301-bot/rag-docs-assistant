from __future__ import annotations

from pathlib import Path

import pytest

from rag_docs.cli import main
from rag_docs.evaluation import evaluate_answers, evaluate_retrieval, load_golden, render_markdown
from rag_docs.service import RagService

from .conftest import CORPUS, GOLDEN


def test_retrieval_quality_gate(corpus_service: RagService) -> None:
    """Regressão de qualidade: se uma mudança piorar a busca, o teste falha antes do merge."""
    cases = load_golden(GOLDEN)
    hybrid = evaluate_retrieval(corpus_service, cases, mode="hybrid", k=5)
    assert hybrid.hit_rate >= 0.9
    assert hybrid.mrr >= 0.8


def test_answer_quality_gate(corpus_service: RagService) -> None:
    metrics = evaluate_answers(corpus_service, load_golden(GOLDEN))
    assert metrics.correct_refusal_rate == 1.0
    assert metrics.faithful_citation_rate >= 0.8
    assert metrics.contains_rate >= 0.6
    assert "Recusam pergunta fora do escopo" in render_markdown([], metrics)


def test_golden_file_errors_point_to_the_line(tmp_path: Path) -> None:
    path = tmp_path / "g.jsonl"
    path.write_text('{"question": "ok", "sources": ["a.md"]}\n{"sem_pergunta": 1}\n', encoding="utf-8")
    with pytest.raises(ValueError, match=r"g\.jsonl:2"):
        load_golden(path)


def test_cli_end_to_end(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = str(tmp_path / "cli.db")
    assert main(["--db", db, "ingest", str(CORPUS)]) == 0
    assert "created   politica-de-ferias.md" in capsys.readouterr().out

    assert main(["--db", db, "ask", "Posso fazer deploy na sexta-feira?"]) == 0
    out = capsys.readouterr().out
    assert "sexta-feira" in out and "[1] guia-de-deploy.md" in out

    assert main(["--db", db, "search", "idempotência", "--mode", "lexical", "--limit", "1"]) == 0
    assert "arquitetura-de-pagamentos.md" in capsys.readouterr().out

    assert main(["--db", db, "eval", str(GOLDEN), "--min-hit-rate", "0.9"]) == 0
    assert main(["--db", db, "eval", str(GOLDEN), "--min-hit-rate", "1.01"]) == 3


def test_cli_reports_bad_files_without_stopping(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = tmp_path / "docs"
    folder.mkdir()
    (folder / "ok.md").write_text("# Ok\nconteúdo válido", encoding="utf-8")
    (folder / "ruim.pdf").write_bytes(b"%PDF quebrado")
    assert main(["--db", str(tmp_path / "x.db"), "ingest", str(folder)]) == 1
    captured = capsys.readouterr()
    assert "created   ok.md" in captured.out
    assert "ruim.pdf" in captured.err
