"""Casos de uso: indexar documentos, buscar e responder."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from .chunking import chunk_sections
from .config import Settings
from .embeddings import Embedder, HashingEmbedder, OllamaEmbedder, OpenAIEmbedder
from .generation import (
    NOT_FOUND,
    AnthropicGenerator,
    ExtractiveGenerator,
    Generator,
    OllamaGenerator,
    OpenAIGenerator,
    finalize,
)
from .loaders import SUPPORTED_EXTENSIONS, load_bytes
from .models import Answer, DocumentInfo, IngestResult, IngestStatus, RagError, SearchHit
from .retrieval import Retriever, SearchMode
from .store import Store

logger = logging.getLogger("rag_docs")


def build_embedder(settings: Settings) -> Embedder:
    if settings.embedding_provider == "openai":
        assert settings.openai_api_key is not None  # garantido pela validação do Settings  # noqa: S101
        return OpenAIEmbedder(
            settings.openai_api_key.get_secret_value(),
            model=settings.embedding_model or "text-embedding-3-small",
            dim=settings.embedding_dim or 1536,
            base_url=settings.openai_base_url,
        )
    if settings.embedding_provider == "ollama":
        return OllamaEmbedder(
            model=settings.embedding_model or "nomic-embed-text",
            dim=settings.embedding_dim or 768,
            base_url=settings.ollama_base_url,
        )
    return HashingEmbedder(dim=settings.embedding_dim or 768)


def build_generator(settings: Settings, embedder: Embedder | None = None) -> Generator:
    model = settings.llm_model or ""
    if settings.llm_provider == "openai":
        assert settings.openai_api_key is not None  # noqa: S101
        return OpenAIGenerator(settings.openai_api_key.get_secret_value(), model, settings.openai_base_url)
    if settings.llm_provider == "anthropic":
        assert settings.anthropic_api_key is not None  # noqa: S101
        return AnthropicGenerator(settings.anthropic_api_key.get_secret_value(), model)
    if settings.llm_provider == "ollama":
        return OllamaGenerator(model, settings.ollama_base_url)
    return ExtractiveGenerator(embedder=embedder)


class RagService:
    def __init__(
        self, settings: Settings, *, embedder: Embedder | None = None, generator: Generator | None = None
    ) -> None:
        self.settings = settings
        self.embedder = embedder or build_embedder(settings)
        self.generator = generator or build_generator(settings, self.embedder)
        self.store = Store(settings.db_path)
        try:
            self.store.bind_embedder(self.embedder.name, self.embedder.dim)
        except Exception:
            self.store.close()
            raise
        self.retriever = Retriever(self.store, self.embedder, max_per_document=settings.max_per_document)

    def close(self) -> None:
        self.store.close()

    def ingest_bytes(self, data: bytes, filename: str) -> IngestResult:
        """
        Idempotente por nome de arquivo + conteúdo: o mesmo arquivo não é reprocessado (nem reenviado ao
        provedor de embeddings, que cobra por token); arquivo alterado substitui todos os chunks antigos.
        """
        document = load_bytes(data, filename)
        digest = hashlib.sha256(data).hexdigest()
        existing = self.store.find_by_source(document.source)
        if existing and existing.sha256 == digest:
            return IngestResult(document.source, "unchanged", existing.id, existing.chunk_count)

        chunks = chunk_sections(
            document.sections, max_chars=self.settings.chunk_size, overlap=self.settings.chunk_overlap
        )
        # O título vai junto no texto embedado: "prazo" num chunk sem contexto fica ambíguo.
        vectors = self.embedder.embed([f"{document.title}. {c.heading}. {c.text}" for c in chunks])
        document_id = self.store.replace_document(
            source=document.source,
            title=document.title,
            media_type=document.media_type,
            sha256=digest,
            chunks=chunks,
            embeddings=vectors,
        )
        status: IngestStatus = "updated" if existing else "created"
        logger.info("documento indexado", extra={"source": document.source, "status": status, "chunks": len(chunks)})
        return IngestResult(document.source, status, document_id, len(chunks))

    def ingest_directory(self, directory: Path) -> tuple[list[IngestResult], list[tuple[str, str]]]:
        results: list[IngestResult] = []
        errors: list[tuple[str, str]] = []
        files = sorted(p for p in directory.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS)
        for path in files:
            try:
                results.append(self.ingest_bytes(path.read_bytes(), path.name))
            except RagError as error:
                # Um PDF ruim não pode impedir a indexação do resto da pasta.
                errors.append((path.name, str(error)))
        return results, errors

    def search(self, query: str, *, limit: int | None = None, mode: SearchMode = "hybrid") -> list[SearchHit]:
        return self.retriever.search(query, limit=limit or self.settings.top_k, mode=mode)

    def ask(self, question: str, *, top_k: int | None = None) -> Answer:
        question = question.strip()
        if not question:
            raise RagError("pergunta vazia")
        if len(question) > self.settings.max_question_chars:
            raise RagError(f"pergunta com mais de {self.settings.max_question_chars} caracteres")
        hits = self.search(question, limit=top_k)
        if not hits:
            return finalize(question, NOT_FOUND, [], self.generator.name)
        text = self.generator.generate(question, hits)
        return finalize(question, text, hits, self.generator.name)

    def documents(self) -> list[DocumentInfo]:
        return self.store.list_documents()

    def delete(self, document_id: int) -> None:
        self.store.delete_document(document_id)
