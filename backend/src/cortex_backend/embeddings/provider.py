"""Embedding provider contracts and the local FastEmbed implementation."""

from __future__ import annotations

import asyncio
import math
import struct
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol

from .models import EMBEDDING_DIMENSIONS, EMBEDDING_MODEL_NAME


class EmbeddingProvider(Protocol):
    """Minimal synchronous-inference contract used by indexing and retrieval."""

    model_name: str
    dimensions: int

    async def embed_documents(self, texts: Sequence[str]) -> list[bytes]:
        """Return normalized float32 vectors for document texts."""

    async def embed_query(self, text: str) -> bytes:
        """Return one normalized float32 vector for a search query."""


def serialize_embedding(values: Sequence[float], *, dimensions: int) -> bytes:
    """Validate, L2-normalize, and serialize one float32 vector."""

    if len(values) != dimensions:
        raise ValueError(f"embedding has {len(values)} dimensions; expected {dimensions}")
    vector = [float(value) for value in values]
    norm = math.sqrt(sum(value * value for value in vector))
    if not math.isfinite(norm) or norm <= 0:
        raise ValueError("embedding must have a finite, non-zero norm")
    normalized = [value / norm for value in vector]
    if not all(math.isfinite(value) for value in normalized):
        raise ValueError("embedding contains a non-finite value")
    return struct.pack(f"{dimensions}f", *normalized)


class LocalEmbeddingProvider:
    """Lazy CPU-friendly FastEmbed provider for the fixed v1 model."""

    model_name = EMBEDDING_MODEL_NAME
    dimensions = EMBEDDING_DIMENSIONS

    def __init__(self, cache_path: Path) -> None:
        self._cache_path = cache_path
        self._model: Any = None
        self._model_lock = asyncio.Lock()
        self._inference_lock = asyncio.Lock()

    async def _get_model(self) -> Any:
        async with self._model_lock:
            if self._model is None:
                self._model = await asyncio.to_thread(self._load_model)
            return self._model

    def _load_model(self) -> Any:
        from fastembed import TextEmbedding

        self._cache_path.mkdir(parents=True, exist_ok=True)
        return TextEmbedding(
            model_name=self.model_name,
            cache_dir=str(self._cache_path),
        )

    async def embed_documents(self, texts: Sequence[str]) -> list[bytes]:
        if not texts:
            return []
        model = await self._get_model()
        async with self._inference_lock:
            values = await asyncio.to_thread(lambda: list(model.embed(list(texts))))
        return [serialize_embedding(value, dimensions=self.dimensions) for value in values]

    async def embed_query(self, text: str) -> bytes:
        model = await self._get_model()
        async with self._inference_lock:
            values = await asyncio.to_thread(lambda: list(model.embed([text])))
        if len(values) != 1:
            raise ValueError("embedding provider returned an invalid query result")
        return serialize_embedding(values[0], dimensions=self.dimensions)
