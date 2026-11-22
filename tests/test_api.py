from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from rag_docs.api import create_app

from .conftest import CORPUS, make_settings

KEY = "k" * 40


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    settings = make_settings(tmp_path, api_key=KEY, corpus_dir=CORPUS, max_upload_mb=1)
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def test_health_and_documents(client: TestClient) -> None:
    health = client.get("/health").json()
    assert health["documents"] == 11
    assert health["generator"] == "extractive"
    sources = {d["source"] for d in client.get("/api/documents").json()}
    assert {
        "politica-de-ferias.md",
        "politica-de-viagens.pdf",
        "politica-de-trabalho-hibrido.html",
    } <= sources


def test_ask_returns_cited_answer(client: TestClient) -> None:
    body = client.post("/api/ask", json={"question": "Quantos dias de férias posso vender?"}).json()
    assert body["grounded"] is True
    assert "10 dias" in body["answer"]
    assert body["citations"][0]["source"] == "politica-de-ferias.md"
    assert body["retrieved"][0]["score"] > 0


def test_ask_out_of_scope_is_refused(client: TestClient) -> None:
    body = client.post("/api/ask", json={"question": "Qual é a política de stock options?"}).json()
    assert body["grounded"] is False
    assert body["citations"] == []


def test_ask_validation(client: TestClient) -> None:
    assert client.post("/api/ask", json={"question": ""}).status_code == 422
    assert client.post("/api/ask", json={"question": "x" * 2000}).json()["error"] == "RAG_ERROR"


def test_search_modes(client: TestClient) -> None:
    for mode in ("hybrid", "lexical", "vector"):
        results = client.get("/api/search", params={"q": "canary", "mode": mode, "limit": 3}).json()
        assert results and len(results) <= 3
    assert client.get("/api/search", params={"q": "x", "mode": "magic"}).status_code == 422


def test_upload_requires_key_and_validates(client: TestClient) -> None:
    files = {"file": ("nota.md", b"# Nota\nO refeitorio abre as 11h30.", "text/markdown")}
    assert client.post("/api/documents", files=files).status_code == 401
    assert client.post("/api/documents", files=files, headers={"x-api-key": "errada"}).status_code == 401

    created = client.post("/api/documents", files=files, headers={"authorization": f"Bearer {KEY}"})
    assert created.status_code == 201
    assert created.json()["status"] == "created"

    big = {"file": ("big.txt", b"a" * (1024 * 1024 + 1), "text/plain")}
    assert client.post("/api/documents", files=big, headers={"x-api-key": KEY}).status_code == 413

    bad = {"file": ("planilha.xlsx", b"PK", "application/octet-stream")}
    response = client.post("/api/documents", files=bad, headers={"x-api-key": KEY})
    assert response.status_code == 422
    assert response.json()["error"] == "UNSUPPORTED_FORMAT"

    document_id = created.json()["document_id"]
    assert client.delete(f"/api/documents/{document_id}", headers={"x-api-key": KEY}).status_code == 204
    assert client.delete(f"/api/documents/{document_id}", headers={"x-api-key": KEY}).status_code == 404


def test_write_routes_disabled_without_api_key(tmp_path: Path) -> None:
    with TestClient(create_app(make_settings(tmp_path))) as client:
        response = client.post("/api/documents", files={"file": ("a.txt", b"x", "text/plain")})
        assert response.status_code == 503


def test_web_ui_and_security_headers(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "RAG Docs Assistant" in response.text
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
