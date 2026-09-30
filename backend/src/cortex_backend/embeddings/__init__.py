"""Local embedding generation and durable embedding indexing."""

from .models import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL_NAME,
    EMBEDDING_MODEL_VERSION,
    ContentChunkEmbedding,
)
from .provider import EmbeddingProvider, LocalEmbeddingProvider

__all__ = [
    "EMBEDDING_DIMENSIONS",
    "EMBEDDING_MODEL_NAME",
    "EMBEDDING_MODEL_VERSION",
    "ContentChunkEmbedding",
    "EmbeddingProvider",
    "LocalEmbeddingProvider",
]
