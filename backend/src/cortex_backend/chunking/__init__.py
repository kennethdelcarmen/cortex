"""Shared source chunking and retrieval primitives."""

from .context import (
    DEFAULT_CONTEXT_MAX_CHARACTERS,
    ContextPackage,
    ContextPassage,
    EmptyContextReason,
    assemble_context,
)
from .service import (
    ChunkSearchRecord,
    ChunkSource,
    ChunkSourceType,
    delete_source_chunks,
    replace_source_chunks,
    search_chunks,
)

__all__ = [
    "DEFAULT_CONTEXT_MAX_CHARACTERS",
    "ChunkSearchRecord",
    "ChunkSource",
    "ChunkSourceType",
    "ContextPackage",
    "ContextPassage",
    "EmptyContextReason",
    "assemble_context",
    "delete_source_chunks",
    "replace_source_chunks",
    "search_chunks",
]
