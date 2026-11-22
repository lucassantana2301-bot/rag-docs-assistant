from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from rag_docs.config import Settings
from rag_docs.service import RagService

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "corpus"
GOLDEN = ROOT / "eval" / "golden.jsonl"


def make_settings(tmp_path: Path, **overrides: Any) -> Settings:
    return Settings(db_path=tmp_path / "index.db", _env_file=None, **overrides)  # type: ignore[call-arg]


@pytest.fixture
def empty_service(tmp_path: Path) -> Iterator[RagService]:
    service = RagService(make_settings(tmp_path))
    yield service
    service.close()


@pytest.fixture(scope="session")
def corpus_service(tmp_path_factory: pytest.TempPathFactory) -> Iterator[RagService]:
    """Índice com o corpus de exemplo, criado uma vez por sessão de testes."""
    service = RagService(make_settings(tmp_path_factory.mktemp("corpus")))
    _, errors = service.ingest_directory(CORPUS)
    assert errors == []
    yield service
    service.close()
