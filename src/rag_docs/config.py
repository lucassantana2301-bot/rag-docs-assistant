from __future__ import annotations

from pathlib import Path
from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuração por variável de ambiente com prefixo RAG_ (ou arquivo .env)."""

    model_config = SettingsConfigDict(env_prefix="RAG_", env_file=".env", extra="ignore")

    db_path: Path = Path("data/index.db")
    corpus_dir: Path | None = None

    embedding_provider: Literal["hashing", "openai", "ollama"] = "hashing"
    embedding_model: str | None = None
    embedding_dim: int | None = Field(default=None, ge=64, le=4096)

    llm_provider: Literal["extractive", "openai", "anthropic", "ollama"] = "extractive"
    llm_model: str | None = None

    openai_api_key: SecretStr | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    anthropic_api_key: SecretStr | None = None
    ollama_base_url: str = "http://localhost:11434"

    chunk_size: int = Field(default=1000, ge=200, le=8000)
    chunk_overlap: int = Field(default=150, ge=0, le=2000)
    top_k: int = Field(default=5, ge=1, le=20)
    max_per_document: int = Field(default=3, ge=1, le=20)

    api_key: SecretStr | None = None
    max_upload_mb: int = Field(default=20, ge=1, le=500)
    max_question_chars: int = Field(default=1000, ge=10, le=10_000)
    cors_origins: list[str] = []

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.chunk_overlap >= self.chunk_size // 2:
            raise ValueError("RAG_CHUNK_OVERLAP deve ser menor que metade de RAG_CHUNK_SIZE")
        needs_openai = self.embedding_provider == "openai" or self.llm_provider == "openai"
        if needs_openai and self.openai_api_key is None:
            raise ValueError("RAG_OPENAI_API_KEY é obrigatória com o provedor openai")
        if self.llm_provider == "anthropic" and self.anthropic_api_key is None:
            raise ValueError("RAG_ANTHROPIC_API_KEY é obrigatória com o provedor anthropic")
        if self.llm_provider in {"openai", "anthropic", "ollama"} and not self.llm_model:
            raise ValueError("defina RAG_LLM_MODEL para usar um LLM")
        if self.api_key is not None and len(self.api_key.get_secret_value()) < 32:
            raise ValueError("RAG_API_KEY precisa de 32+ caracteres")
        return self
