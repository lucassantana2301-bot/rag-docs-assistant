from __future__ import annotations

import json
from pathlib import Path

import httpx
import numpy as np
import pytest

from rag_docs.config import Settings
from rag_docs.embeddings import OllamaEmbedder, OpenAIEmbedder
from rag_docs.generation import AnthropicGenerator, ExtractiveGenerator, OllamaGenerator, OpenAIGenerator
from rag_docs.models import ProviderError
from rag_docs.service import build_embedder, build_generator


def client(handler: object) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))  # type: ignore[arg-type]


def test_openai_embedder_batches_and_restores_order() -> None:
    batches: list[int] = []

    def handle(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        batches.append(len(body["input"]))
        # A API pode devolver fora de ordem; o índice define a posição.
        data = [{"index": i, "embedding": [float(i + 1), 0.0, 0.0]} for i in range(len(body["input"]))]
        return httpx.Response(200, json={"data": list(reversed(data))})

    embedder = OpenAIEmbedder("sk", dim=3, client=client(handle))
    matrix = embedder.embed([f"t{i}" for i in range(130)])
    assert batches == [128, 2]
    assert matrix.shape == (130, 3)
    assert np.allclose(np.linalg.norm(matrix, axis=1), 1.0)


def test_ollama_embedder_validates_dimension() -> None:
    def handle(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"embeddings": [[0.1, 0.2]]})

    with pytest.raises(ProviderError, match="esperado"):
        OllamaEmbedder(dim=768, client=client(handle)).embed(["x"])


def test_embedder_network_failure_becomes_provider_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("rag_docs.embeddings.time.sleep", lambda _: None)

    def handle(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sem rede", request=request)

    with pytest.raises(ProviderError, match="falha de rede"):
        OllamaEmbedder(client=client(handle)).embed(["x"])


def test_ollama_generator() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content)["stream"] is False
        return httpx.Response(200, json={"message": {"content": "ok [1]"}})

    assert OllamaGenerator("llama3", client=client(handle)).generate("q", []) == "ok [1]"


def test_unexpected_llm_payload_is_a_provider_error() -> None:
    def handle(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": True})

    with pytest.raises(ProviderError, match="formato inesperado"):
        OpenAIGenerator("sk", "m", client=client(handle)).generate("q", [])


def test_settings_validation(tmp_path: Path) -> None:
    base = {"db_path": tmp_path / "x.db", "_env_file": None}
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        Settings(**base, llm_provider="openai", llm_model="gpt")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="LLM_MODEL"):
        Settings(**base, llm_provider="ollama")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        Settings(**base, llm_provider="anthropic", llm_model="claude")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="32"):
        Settings(**base, api_key="curta")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="CHUNK_OVERLAP"):
        Settings(**base, chunk_size=400, chunk_overlap=300)  # type: ignore[arg-type]


def test_factories_pick_configured_providers(tmp_path: Path) -> None:
    settings = Settings(
        db_path=tmp_path / "x.db",
        _env_file=None,  # type: ignore[call-arg]
        embedding_provider="openai",
        llm_provider="anthropic",
        llm_model="claude-test",
        openai_api_key="sk-test",  # type: ignore[arg-type]
        anthropic_api_key="ak-test",  # type: ignore[arg-type]
    )
    assert build_embedder(settings).name == "openai-text-embedding-3-small-1536"
    assert isinstance(build_generator(settings), AnthropicGenerator)
    ollama = settings.model_copy(update={"embedding_provider": "ollama", "llm_provider": "ollama"})
    assert build_embedder(ollama).name == "ollama-nomic-embed-text-768"
    assert isinstance(build_generator(ollama), OllamaGenerator)
    local = settings.model_copy(update={"embedding_provider": "hashing", "llm_provider": "extractive"})
    assert isinstance(build_generator(local), ExtractiveGenerator)
