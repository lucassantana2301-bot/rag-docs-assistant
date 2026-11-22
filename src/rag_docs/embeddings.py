"""Provedores de embedding. O padrão (hashing) roda offline e sem custo; OpenAI e Ollama são opcionais."""

from __future__ import annotations

import hashlib
import time
from typing import Any, Protocol, cast

import httpx
import numpy as np
from numpy.typing import NDArray

from .models import ProviderError
from .text import fold, tokenize

Vector = NDArray[np.float32]


class Embedder(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def dim(self) -> int: ...

    def embed(self, texts: list[str]) -> Vector:
        """Matriz (len(texts), dim) com linhas normalizadas (norma L2 = 1)."""
        ...


def _l2_normalize(matrix: Vector) -> Vector:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (matrix / norms).astype(np.float32)


class HashingEmbedder:
    """
    Embedding léxico por feature hashing de palavras e n-gramas de caracteres.

    Não entende sinônimo como um modelo neural, mas captura variações de forma ("reembolso",
    "reembolsos", "reembolsável") que o BM25 por palavra inteira perde. É determinístico, não precisa
    de rede nem GPU, e serve de base reprodutível para os testes e para a avaliação no CI.
    """

    def __init__(self, dim: int = 768, ngram_range: tuple[int, int] = (3, 5)) -> None:
        if dim < 64:
            raise ValueError("dim deve ser >= 64")
        self._dim = dim
        self._ngrams = ngram_range

    @property
    def name(self) -> str:
        return f"hashing-{self._dim}-{self._ngrams[0]}{self._ngrams[1]}"

    @property
    def dim(self) -> int:
        return self._dim

    def _features(self, text: str) -> list[str]:
        words = tokenize(text)
        features = [f"w:{w}" for w in words]
        low, high = self._ngrams
        for word in words:
            padded = f"<{fold(word)}>"
            for n in range(low, high + 1):
                features.extend(f"c:{padded[i : i + n]}" for i in range(max(0, len(padded) - n + 1)))
        return features

    def embed(self, texts: list[str]) -> Vector:
        matrix = np.zeros((len(texts), self._dim), dtype=np.float32)
        for row, text in enumerate(texts):
            for feature in self._features(text):
                digest = hashlib.blake2b(feature.encode(), digest_size=8).digest()
                value = int.from_bytes(digest, "little")
                index = value % self._dim
                # Sinal pelo bit alto: colisões se cancelam em média em vez de se somarem.
                sign = 1.0 if (value >> 63) & 1 else -1.0
                weight = 1.0 if feature.startswith("w:") else 0.5
                matrix[row, index] += sign * weight
        return _l2_normalize(matrix)


class _HttpEmbedder:
    def __init__(self, client: httpx.Client, batch_size: int, retries: int = 3) -> None:
        self._client = client
        self._batch_size = batch_size
        self._retries = retries

    def _post(self, url: str, payload: dict[str, object], headers: dict[str, str]) -> dict[str, object]:
        for attempt in range(self._retries + 1):
            try:
                response = self._client.post(url, json=payload, headers=headers)
            except httpx.TransportError as error:
                if attempt == self._retries:
                    raise ProviderError(f"falha de rede no provedor de embeddings: {error}") from error
                time.sleep(min(2**attempt, 8))
                continue
            if response.status_code in (429, 500, 502, 503, 504) and attempt < self._retries:
                retry_after = response.headers.get("retry-after", "")
                time.sleep(float(retry_after) if retry_after.isdigit() else min(2**attempt, 8))
                continue
            if response.is_error:
                # O corpo pode ecoar parte da requisição; a chave nunca está nele, mas o texto do usuário pode.
                raise ProviderError(f"provedor de embeddings respondeu HTTP {response.status_code}")
            data: dict[str, object] = response.json()
            return data
        raise ProviderError("provedor de embeddings indisponível")


class OpenAIEmbedder(_HttpEmbedder):
    def __init__(
        self,
        api_key: str,
        model: str = "text-embedding-3-small",
        dim: int = 1536,
        base_url: str = "https://api.openai.com/v1",
        client: httpx.Client | None = None,
    ) -> None:
        super().__init__(client or httpx.Client(timeout=60), batch_size=128)
        self._api_key = api_key
        self._model = model
        self._dim = dim
        self._url = f"{base_url.rstrip('/')}/embeddings"

    @property
    def name(self) -> str:
        return f"openai-{self._model}-{self._dim}"

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, texts: list[str]) -> Vector:
        rows: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            batch = texts[start : start + self._batch_size]
            data = self._post(
                self._url,
                {"model": self._model, "input": batch, "dimensions": self._dim},
                {"authorization": f"Bearer {self._api_key}"},
            )
            items = cast(list[dict[str, Any]], data["data"])
            rows.extend(item["embedding"] for item in sorted(items, key=lambda item: int(item["index"])))
        return _l2_normalize(np.asarray(rows, dtype=np.float32).reshape(len(texts), self._dim))


class OllamaEmbedder(_HttpEmbedder):
    def __init__(
        self,
        model: str = "nomic-embed-text",
        dim: int = 768,
        base_url: str = "http://localhost:11434",
        client: httpx.Client | None = None,
    ) -> None:
        super().__init__(client or httpx.Client(timeout=120), batch_size=32)
        self._model = model
        self._dim = dim
        self._url = f"{base_url.rstrip('/')}/api/embed"

    @property
    def name(self) -> str:
        return f"ollama-{self._model}-{self._dim}"

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, texts: list[str]) -> Vector:
        rows: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            data = self._post(self._url, {"model": self._model, "input": texts[start : start + self._batch_size]}, {})
            rows.extend(cast(list[list[float]], data["embeddings"]))
        matrix = np.asarray(rows, dtype=np.float32)
        if matrix.shape != (len(texts), self._dim):
            raise ProviderError(f"Ollama devolveu embeddings {matrix.shape}, esperado ({len(texts)}, {self._dim})")
        return _l2_normalize(matrix)
