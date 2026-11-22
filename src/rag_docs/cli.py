"""Linha de comando: rag ingest | ask | search | eval | serve."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from .config import Settings
from .evaluation import evaluate_answers, evaluate_cases, evaluate_retrieval, load_golden, render_markdown
from .models import RagError
from .report import render_html
from .service import RagService


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rag", description="Assistente de documentos com busca híbrida e citações.")
    parser.add_argument("--db", type=Path, help="caminho do índice SQLite (padrão: RAG_DB_PATH ou data/index.db)")
    sub = parser.add_subparsers(dest="command", required=True)

    ingest = sub.add_parser("ingest", help="indexa arquivos ou pastas (md, txt, html, pdf)")
    ingest.add_argument("paths", nargs="+", type=Path)

    ask = sub.add_parser("ask", help="faz uma pergunta")
    ask.add_argument("question")
    ask.add_argument("--json", action="store_true", help="saída em JSON")

    search = sub.add_parser("search", help="mostra os trechos recuperados")
    search.add_argument("query")
    search.add_argument("--mode", choices=["hybrid", "lexical", "vector"], default="hybrid")
    search.add_argument("--limit", type=int, default=5)

    evaluate = sub.add_parser("eval", help="mede a qualidade com um conjunto de referência (JSONL)")
    evaluate.add_argument("golden", type=Path)
    evaluate.add_argument("--k", type=int, default=5)
    evaluate.add_argument("--answers", action="store_true", help="avalia também as respostas (chama o LLM)")
    evaluate.add_argument("--min-hit-rate", type=float, help="falha (código 3) se o hit rate híbrido ficar abaixo")
    evaluate.add_argument("--html", type=Path, help="grava o relatório navegável (HTML) neste caminho")
    evaluate.add_argument("--json-out", type=Path, help="grava o resultado detalhado por pergunta (JSON)")
    evaluate.add_argument("--revision", help="commit avaliado, exibido no relatório")

    serve = sub.add_parser("serve", help="sobe a API e a interface web")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    overrides = {"db_path": args.db} if args.db else {}
    try:
        settings = Settings(**overrides)
    except ValueError as error:
        print(f"configuração inválida: {error}", file=sys.stderr)
        return 2

    if args.command == "serve":
        import uvicorn  # só carrega o servidor quando necessário

        from .api import create_app

        uvicorn.run(create_app(settings), host=args.host, port=args.port)
        return 0

    try:
        service = RagService(settings)
    except RagError as error:
        print(f"erro: {error}", file=sys.stderr)
        return 1

    try:
        return _run(args, service)
    except RagError as error:
        print(f"erro: {error}", file=sys.stderr)
        return 1
    finally:
        service.close()


def _run(args: argparse.Namespace, service: RagService) -> int:
    if args.command == "ingest":
        failures = 0
        for path in args.paths:
            if path.is_dir():
                results, errors = service.ingest_directory(path)
            else:
                results, errors = [service.ingest_bytes(path.read_bytes(), path.name)], []
            for result in results:
                print(f"{result.status:9} {result.source} ({result.chunks} chunks)")
            for name, message in errors:
                failures += 1
                print(f"erro      {name}: {message}", file=sys.stderr)
        return 1 if failures else 0

    if args.command == "ask":
        answer = service.ask(args.question)
        if args.json:
            print(json.dumps(asdict(answer), ensure_ascii=False, indent=2))
            return 0
        print(answer.text)
        if answer.citations:
            print()
            for citation in answer.citations:
                where = f" › {citation.heading}" if citation.heading else ""
                page = f", p. {citation.page}" if citation.page else ""
                print(f"[{citation.number}] {citation.source}{where}{page}")
        return 0

    if args.command == "search":
        for position, hit in enumerate(service.search(args.query, limit=args.limit, mode=args.mode), start=1):
            preview = hit.text.replace("\n", " ")[:160]
            print(f"{position}. {hit.source} › {hit.heading} (score {hit.score:.4f})\n   {preview}")
        return 0

    if args.command == "eval":
        cases = load_golden(args.golden)
        retrieval = [
            evaluate_retrieval(service, cases, mode=mode, k=args.k) for mode in ("lexical", "vector", "hybrid")
        ]
        answers = evaluate_answers(service, cases) if args.answers or args.html else None
        print(render_markdown(retrieval, answers))
        if args.html or args.json_out:
            details = evaluate_cases(service, cases, k=args.k)
            if args.json_out:
                payload = {
                    "retrieval": [asdict(m) for m in retrieval],
                    "answers": asdict(answers) if answers else None,
                    "cases": [asdict(c) | {"passed": c.passed} for c in details],
                }
                _write(args.json_out, json.dumps(payload, ensure_ascii=False, indent=2))
            if args.html and answers:
                html = render_html(
                    retrieval,
                    answers,
                    details,
                    generator=service.generator.name,
                    generated_at=datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
                    revision=args.revision,
                    repository_url="https://github.com/lucassantana2301-bot/rag-docs-assistant",
                )
                _write(args.html, html)
        hybrid = retrieval[-1]
        if args.min_hit_rate is not None and hybrid.hit_rate < args.min_hit_rate:
            print(
                f"\nhit rate híbrido {hybrid.hit_rate:.0%} abaixo do mínimo {args.min_hit_rate:.0%}",
                file=sys.stderr,
            )
            return 3
        return 0
    return 2


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"gravado: {path}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
