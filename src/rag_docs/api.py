"""API HTTP (FastAPI) e interface web estática."""

# Sem `from __future__ import annotations`: o FastAPI precisa resolver os Annotated locais em tempo de execução.
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict
from importlib import resources
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .config import Settings
from .models import DocumentNotFoundError, ProviderError, RagError
from .service import RagService


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=10_000)
    top_k: int | None = Field(default=None, ge=1, le=20)


def create_app(settings: Settings | None = None, service: RagService | None = None) -> FastAPI:
    settings = settings or Settings()
    state: dict[str, RagService] = {}

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        rag = service or RagService(settings)
        if settings.corpus_dir and service is None:
            rag.ingest_directory(settings.corpus_dir)
        state["rag"] = rag
        yield
        rag.close()

    app = FastAPI(
        title="RAG Docs Assistant",
        version=__version__,
        lifespan=lifespan,
        description="Perguntas sobre documentos internos com busca híbrida e respostas citadas.",
    )
    if settings.cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["GET", "POST", "DELETE"])

    def rag() -> RagService:
        return state["rag"]

    def require_api_key(
        authorization: Annotated[str | None, Header()] = None,
        x_api_key: Annotated[str | None, Header()] = None,
    ) -> None:
        """Escrita exige chave. Sem RAG_API_KEY configurada as rotas de escrita ficam desligadas, nunca abertas."""
        if settings.api_key is None:
            raise HTTPException(503, detail={"error": "WRITE_DISABLED", "message": "configure RAG_API_KEY"})
        token = authorization.removeprefix("Bearer ").strip() if authorization else x_api_key
        if not token or not secrets.compare_digest(token.encode(), settings.api_key.get_secret_value().encode()):
            raise HTTPException(401, detail={"error": "UNAUTHORIZED", "message": "API key ausente ou inválida"})

    @app.exception_handler(RagError)
    async def rag_error(_: Request, error: RagError) -> JSONResponse:
        status = 404 if isinstance(error, DocumentNotFoundError) else 502 if isinstance(error, ProviderError) else 422
        return JSONResponse(status_code=status, content={"error": error.code, "message": str(error)})

    @app.middleware("http")
    async def security_headers(request: Request, call_next):  # type: ignore[no-untyped-def]
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Frame-Options", "DENY")
        return response

    Service = Annotated[RagService, Depends(rag)]  # noqa: N806 - alias de tipo do FastAPI

    @app.get("/health")
    def health(service: Service) -> dict[str, object]:
        return {
            "status": "ok",
            "version": __version__,
            **service.store.stats(),
            "embedder": service.embedder.name,
            "generator": service.generator.name,
        }

    @app.post("/api/ask")
    def ask(body: AskRequest, service: Service) -> dict[str, object]:
        answer = service.ask(body.question, top_k=body.top_k)
        return {
            "question": answer.question,
            "answer": answer.text,
            "grounded": answer.grounded,
            "generator": answer.generator,
            "citations": [asdict(c) for c in answer.citations],
            "retrieved": [
                {
                    "source": h.source,
                    "heading": h.heading,
                    "page": h.page,
                    "score": h.score,
                    "lexicalRank": h.lexical_rank,
                    "vectorRank": h.vector_rank,
                }
                for h in answer.hits
            ],
        }

    @app.get("/api/search")
    def search(
        service: Service,
        q: Annotated[str, Query(min_length=1, max_length=1000)],
        limit: Annotated[int, Query(ge=1, le=50)] = 10,
        mode: Literal["hybrid", "lexical", "vector"] = "hybrid",
    ) -> list[dict[str, object]]:
        return [asdict(hit) for hit in service.search(q, limit=limit, mode=mode)]

    @app.get("/api/documents")
    def documents(service: Service) -> list[dict[str, object]]:
        return [asdict(d) for d in service.documents()]

    @app.post("/api/documents", status_code=201, dependencies=[Depends(require_api_key)])
    async def upload(service: Service, file: Annotated[UploadFile, File()]) -> dict[str, object]:
        limit = settings.max_upload_mb * 1024 * 1024
        # Lê no máximo limit+1 bytes: arquivo grande é recusado sem carregar tudo na memória.
        data = await file.read(limit + 1)
        if len(data) > limit:
            raise HTTPException(
                413, detail={"error": "FILE_TOO_LARGE", "message": f"limite de {settings.max_upload_mb} MB"}
            )
        result = service.ingest_bytes(data, file.filename or "upload.txt")
        return asdict(result)

    @app.delete("/api/documents/{document_id}", status_code=204, dependencies=[Depends(require_api_key)])
    def delete(document_id: int, service: Service) -> None:
        service.delete(document_id)

    web = resources.files("rag_docs") / "web"
    app.mount("/", StaticFiles(directory=str(web), html=True), name="web")
    return app
