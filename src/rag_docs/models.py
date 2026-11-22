from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


class RagError(Exception):
    """Erro esperado (entrada inválida, formato não suportado). A API traduz para 4xx."""

    code = "RAG_ERROR"


class UnsupportedFormatError(RagError):
    code = "UNSUPPORTED_FORMAT"


class EmptyDocumentError(RagError):
    code = "EMPTY_DOCUMENT"


class DocumentNotFoundError(RagError):
    code = "DOCUMENT_NOT_FOUND"


class IndexMismatchError(RagError):
    code = "INDEX_MISMATCH"


class ProviderError(RagError):
    """Falha do provedor externo (LLM ou embeddings). A API traduz para 502."""

    code = "PROVIDER_ERROR"


@dataclass(frozen=True, slots=True)
class Section:
    """Trecho contínuo de um documento com o contexto de onde ele está."""

    text: str
    heading_path: tuple[str, ...] = ()
    page: int | None = None


@dataclass(frozen=True, slots=True)
class LoadedDocument:
    source: str
    title: str
    media_type: str
    sections: list[Section]


@dataclass(frozen=True, slots=True)
class Chunk:
    ordinal: int
    text: str
    heading_path: tuple[str, ...]
    page: int | None

    @property
    def heading(self) -> str:
        return " › ".join(self.heading_path)


@dataclass(frozen=True, slots=True)
class DocumentInfo:
    id: int
    source: str
    title: str
    media_type: str
    sha256: str
    chunk_count: int
    indexed_at: str


@dataclass(frozen=True, slots=True)
class SearchHit:
    chunk_id: int
    document_id: int
    source: str
    title: str
    heading: str
    page: int | None
    text: str
    score: float
    lexical_rank: int | None = None
    vector_rank: int | None = None


@dataclass(frozen=True, slots=True)
class Citation:
    """Fonte numerada como aparece na resposta: [1], [2]..."""

    number: int
    source: str
    title: str
    heading: str
    page: int | None
    excerpt: str


@dataclass(frozen=True, slots=True)
class Answer:
    question: str
    text: str
    citations: list[Citation]
    grounded: bool
    generator: str
    hits: list[SearchHit] = field(default_factory=list)


IngestStatus = Literal["created", "updated", "unchanged"]


@dataclass(frozen=True, slots=True)
class IngestResult:
    source: str
    status: IngestStatus
    document_id: int
    chunks: int
