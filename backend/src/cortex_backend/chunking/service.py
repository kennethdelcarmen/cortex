"""Transactional chunk persistence and internal owner-scoped retrieval."""

from __future__ import annotations

import hashlib
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..embeddings.provider import EmbeddingProvider
from ..embeddings.service import enqueue_chunk_embeddings, search_vectors
from ..storage import DatabaseStorage
from .models import ContentChunk
from .text import chunk_text, normalize_source_text

ChunkSourceType = Literal["note", "task", "file"]
RetrievalMode = Literal["lexical", "vector", "hybrid"]
MAX_CHUNK_SEARCH_LENGTH = 200
DEFAULT_CHUNK_SEARCH_LIMIT = 20
MAX_CHUNK_SEARCH_LIMIT = 100
RRF_K = 60

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChunkSource:
    """Canonical source input used to replace one source's chunks."""

    user_id: str
    source_type: ChunkSourceType
    source_id: str
    text: str
    title: str | None = None
    version_salt: str = "v1"


@dataclass(frozen=True)
class ChunkSearchRecord:
    """One ranked chunk returned by the internal retrieval contract.

    ``score`` is the final retrieval score. It is ``-bm25`` for lexical-only
    retrieval and reciprocal-rank fusion for hybrid retrieval. The channel
    scores are retained for internal diagnostics and evaluation.
    """

    id: str
    user_id: str
    source_type: ChunkSourceType
    source_id: str
    source_version: str
    source_title: str | None
    ordinal: int
    text: str
    rank: int
    score: float
    file_ids: list[str]
    file_names: list[str]
    lexical_score: float | None = None
    vector_distance: float | None = None


def source_version(source: ChunkSource, normalized_text: str | None = None) -> str:
    """Return a deterministic version for one canonical source envelope."""

    canonical_text = (
        normalized_text if normalized_text is not None else normalize_source_text(source.text)
    )
    canonical_title = normalize_source_text(source.title or "")
    payload = "\0".join(
        (
            "cortex-content-chunks-v1",
            source.version_salt,
            source.source_type,
            source.source_id,
            canonical_title,
            canonical_text,
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def _delete_source_rows(
    db: AsyncSession,
    *,
    user_id: str,
    source_type: ChunkSourceType,
    source_id: str,
) -> None:
    await db.execute(
        text(
            "DELETE FROM content_chunks_fts "
            "WHERE chunk_id IN ("
            "SELECT id FROM content_chunks "
            "WHERE user_id = :user_id AND source_type = :source_type AND source_id = :source_id"
            ")"
        ),
        {"user_id": user_id, "source_type": source_type, "source_id": source_id},
    )
    await db.execute(
        delete(ContentChunk).where(
            ContentChunk.user_id == user_id,
            ContentChunk.source_type == source_type,
            ContentChunk.source_id == source_id,
        )
    )


async def delete_source_chunks(
    db: AsyncSession,
    source_type: ChunkSourceType,
    source_id: str,
    *,
    user_id: str,
) -> None:
    """Remove all chunks for one source inside the caller's transaction."""

    await _delete_source_rows(
        db,
        user_id=user_id,
        source_type=source_type,
        source_id=source_id,
    )


async def replace_source_chunks(
    db: AsyncSession,
    source: ChunkSource,
    *,
    now: datetime | None = None,
) -> str:
    """Atomically replace one source's chunks and its FTS rows."""

    normalized_text = normalize_source_text(source.text)
    version = source_version(source, normalized_text)
    await _delete_source_rows(
        db,
        user_id=source.user_id,
        source_type=source.source_type,
        source_id=source.source_id,
    )
    chunks = chunk_text(normalized_text)
    if not chunks:
        return version

    timestamp = now or datetime.now(UTC)
    rows = [
        ContentChunk(
            id=str(uuid4()),
            user_id=source.user_id,
            source_type=source.source_type,
            source_id=source.source_id,
            source_version=version,
            source_title=source.title,
            ordinal=ordinal,
            text=chunk,
            created_at=timestamp,
            updated_at=timestamp,
        )
        for ordinal, chunk in enumerate(chunks)
    ]
    db.add_all(rows)
    await db.flush()
    await enqueue_chunk_embeddings(db, rows, now=timestamp)
    await db.execute(
        text("INSERT INTO content_chunks_fts (chunk_id, content) VALUES (:chunk_id, :content)"),
        [{"chunk_id": row.id, "content": row.text} for row in rows],
    )
    return version


def _fts_query(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.strip().casefold().split())
    if not normalized:
        return None
    if len(normalized) > MAX_CHUNK_SEARCH_LENGTH:
        raise ValueError("chunk search query is too long")
    tokens = re.findall(r"\w+", normalized, flags=re.UNICODE)
    if not tokens:
        return None
    return " AND ".join(f'"{token.replace(chr(34), chr(34) * 2)}"' for token in tokens)


def _source_filter(source_types: Sequence[ChunkSourceType]) -> tuple[str, dict[str, object]]:
    unique_types = tuple(dict.fromkeys(source_types))
    invalid = set(unique_types).difference({"note", "task", "file"})
    if invalid:
        raise ValueError("invalid chunk source type")
    if not unique_types:
        return "", {}
    placeholders = ", ".join(f":source_type_{index}" for index in range(len(unique_types)))
    return f" AND c.source_type IN ({placeholders})", {
        f"source_type_{index}": value for index, value in enumerate(unique_types)
    }


async def search_chunks(
    storage: DatabaseStorage,
    user_id: str,
    query: str | None,
    *,
    source_types: Sequence[ChunkSourceType] = (),
    limit: int = DEFAULT_CHUNK_SEARCH_LIMIT,
    embedding_provider: EmbeddingProvider | None = None,
    retrieval_mode: RetrievalMode = "hybrid",
) -> list[ChunkSearchRecord]:
    """Search active owner-scoped chunks with optional hybrid retrieval.

    The query is trimmed, case-folded, and split into Unicode word tokens.
    Every token must match. Empty or punctuation-only queries return no hits;
    queries longer than :data:`MAX_CHUNK_SEARCH_LENGTH` raise ``ValueError``.
    FTS5 remains the exact-term channel and fallback. When an embedding
    provider and ready vector index are available, lexical and vector ranks
    are combined with reciprocal-rank fusion using ``k=60``.
    """

    if not 1 <= limit <= MAX_CHUNK_SEARCH_LIMIT:
        raise ValueError("invalid chunk search limit")
    if retrieval_mode not in {"lexical", "vector", "hybrid"}:
        raise ValueError("invalid chunk retrieval mode")
    fts_query = _fts_query(query)
    if fts_query is None:
        return []
    source_clause, source_params = _source_filter(source_types)
    candidate_limit = min(MAX_CHUNK_SEARCH_LIMIT, max(limit * 3, 50))
    params: dict[str, object] = {
        "user_id": user_id,
        "fts_query": fts_query,
        "limit": candidate_limit,
        **source_params,
    }
    statement = text(
        "SELECT c.id, c.user_id, c.source_type, c.source_id, c.source_version, "
        "c.source_title, c.ordinal, c.text, "
        "-bm25(content_chunks_fts) AS score "
        "FROM content_chunks AS c "
        "JOIN content_chunks_fts AS f ON f.chunk_id = c.id "
        "WHERE c.user_id = :user_id "
        "AND content_chunks_fts MATCH :fts_query "
        "AND ("
        "(c.source_type = 'note' AND EXISTS ("
        "SELECT 1 FROM notes WHERE notes.id = c.source_id "
        "AND notes.user_id = c.user_id AND notes.deleted_at IS NULL)) "
        "OR (c.source_type = 'task' AND EXISTS ("
        "SELECT 1 FROM tasks WHERE tasks.id = c.source_id "
        "AND tasks.user_id = c.user_id AND tasks.deleted_at IS NULL)) "
        "OR (c.source_type = 'file' AND EXISTS ("
        "SELECT 1 FROM files WHERE files.sha256 = c.source_id "
        "AND files.user_id = c.user_id AND files.deleted_at IS NULL))"
        ")"
        f"{source_clause} "
        "ORDER BY bm25(content_chunks_fts), c.source_type, c.source_id, c.ordinal "
        "LIMIT :limit"
    )

    async with storage.session() as db:
        lexical_rows: Sequence[Any]
        if retrieval_mode != "vector":
            result = await db.execute(statement, params)
            lexical_rows = result.all()
        else:
            lexical_rows = ()
        lexical_scores = {row[0]: float(row[8]) for row in lexical_rows}
        vector_hits = []
        if retrieval_mode != "lexical" and embedding_provider is not None:
            try:
                query_vector = await embedding_provider.embed_query(query or "")
                vector_hits = await search_vectors(
                    storage,
                    user_id,
                    query_vector,
                    source_types=source_types,
                    limit=candidate_limit,
                )
            except Exception as exc:
                logger.warning(
                    "Semantic chunk retrieval unavailable; using FTS5 fallback",
                    extra={"error_code": type(exc).__name__},
                )

        vector_distances = {hit.chunk_id: hit.distance for hit in vector_hits}
        rows_by_id = {row[0]: row for row in lexical_rows}
        missing_vector_ids = [
            chunk_id for chunk_id in vector_distances if chunk_id not in rows_by_id
        ]
        if missing_vector_ids:
            placeholders = ", ".join(
                f":vector_chunk_{index}" for index in range(len(missing_vector_ids))
            )
            vector_params: dict[str, object] = {
                "user_id": user_id,
                **{
                    f"vector_chunk_{index}": chunk_id
                    for index, chunk_id in enumerate(missing_vector_ids)
                },
                **source_params,
            }
            vector_result = await db.execute(
                text(
                    "SELECT c.id, c.user_id, c.source_type, c.source_id, c.source_version, "
                    "c.source_title, c.ordinal, c.text, NULL AS score "
                    "FROM content_chunks AS c "
                    f"WHERE c.user_id = :user_id AND c.id IN ({placeholders}) "
                    "AND ("
                    "(c.source_type = 'note' AND EXISTS ("
                    "SELECT 1 FROM notes WHERE notes.id = c.source_id "
                    "AND notes.user_id = c.user_id AND notes.deleted_at IS NULL)) "
                    "OR (c.source_type = 'task' AND EXISTS ("
                    "SELECT 1 FROM tasks WHERE tasks.id = c.source_id "
                    "AND tasks.user_id = c.user_id AND tasks.deleted_at IS NULL)) "
                    "OR (c.source_type = 'file' AND EXISTS ("
                    "SELECT 1 FROM files WHERE files.sha256 = c.source_id "
                    "AND files.user_id = c.user_id AND files.deleted_at IS NULL))"
                    ")"
                    f"{source_clause}"
                ),
                vector_params,
            )
            for row in vector_result.all():
                rows_by_id[row[0]] = row

        vector_rank = {hit.chunk_id: rank for rank, hit in enumerate(vector_hits, start=1)}
        lexical_rank = {row[0]: rank for rank, row in enumerate(lexical_rows, start=1)}
        semantic_active = bool(vector_rank)
        if semantic_active:
            candidate_ids = set(lexical_rank) | set(vector_rank)
            fused_scores = {
                chunk_id: (1 / (RRF_K + lexical_rank[chunk_id]) if chunk_id in lexical_rank else 0)
                + (1 / (RRF_K + vector_rank[chunk_id]) if chunk_id in vector_rank else 0)
                for chunk_id in candidate_ids
                if chunk_id in rows_by_id
            }
            ordered_ids = sorted(
                fused_scores,
                key=lambda chunk_id: (
                    -fused_scores[chunk_id],
                    rows_by_id[chunk_id][2],
                    rows_by_id[chunk_id][3],
                    rows_by_id[chunk_id][6],
                ),
            )[:limit]
        else:
            ordered_ids = [row[0] for row in lexical_rows[:limit]]
            fused_scores = {}

        file_ids_by_hash: dict[str, list[str]] = {}
        file_names_by_hash: dict[str, list[str]] = {}
        selected_rows = [rows_by_id[chunk_id] for chunk_id in ordered_ids]
        file_hashes = {str(row[3]) for row in selected_rows if row[2] == "file"}
        if file_hashes:
            file_placeholders = ", ".join(
                f":file_hash_{index}" for index in range(len(file_hashes))
            )
            file_params: dict[str, object] = {
                "user_id": user_id,
                **{f"file_hash_{index}": value for index, value in enumerate(sorted(file_hashes))},
            }
            file_result = await db.execute(
                text(
                    "SELECT sha256, id, original_name FROM files "
                    "WHERE user_id = :user_id AND deleted_at IS NULL "
                    f"AND sha256 IN ({file_placeholders}) "
                    "ORDER BY created_at ASC, id ASC"
                ),
                file_params,
            )
            for source_id, file_id, file_name in file_result.all():
                source_hash = str(source_id)
                file_ids_by_hash.setdefault(source_hash, []).append(str(file_id))
                file_names_by_hash.setdefault(source_hash, []).append(str(file_name))

        records: list[ChunkSearchRecord] = []
        for rank, chunk_id in enumerate(ordered_ids, start=1):
            row = rows_by_id[chunk_id]
            records.append(
                ChunkSearchRecord(
                    id=row[0],
                    user_id=row[1],
                    source_type=row[2],
                    source_id=row[3],
                    source_version=row[4],
                    source_title=row[5],
                    ordinal=row[6],
                    text=row[7],
                    rank=rank,
                    score=(
                        float(fused_scores[chunk_id])
                        if semantic_active
                        else lexical_scores[chunk_id]
                    ),
                    file_ids=file_ids_by_hash.get(row[3], []),
                    file_names=file_names_by_hash.get(row[3], []),
                    lexical_score=lexical_scores.get(chunk_id),
                    vector_distance=vector_distances.get(chunk_id),
                )
            )
        return records
