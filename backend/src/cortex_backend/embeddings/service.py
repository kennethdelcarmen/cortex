"""Durable local embedding jobs and sqlite-vec retrieval."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import and_, delete, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..chunking.models import ContentChunk
from ..config import Settings
from ..storage import DatabaseStorage, SQLiteStorage
from .models import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL_NAME,
    EMBEDDING_MODEL_VERSION,
    ContentChunkEmbedding,
)
from .provider import EmbeddingProvider

logger = logging.getLogger(__name__)

VECTOR_TABLE = "content_chunk_vectors"
EmbeddingWorkerState = Literal["disabled", "starting", "healthy", "degraded", "stopped"]


class EmbeddingUnavailableError(RuntimeError):
    """The optional vector index cannot be initialized on this runtime."""


@dataclass
class EmbeddingHealth:
    """Mutable lifecycle health snapshot for the optional embedding worker."""

    enabled: bool
    state: EmbeddingWorkerState = "starting"
    last_error: str | None = None
    worker_ready: bool = False

    def __post_init__(self) -> None:
        if not self.enabled:
            self.state = "disabled"
            self.worker_ready = True

    def mark_started(self) -> None:
        if self.enabled:
            self.state = "starting"
            self.worker_ready = False

    def mark_success(self) -> None:
        if self.enabled:
            self.state = "healthy"
            self.last_error = None
            self.worker_ready = True

    def mark_failure(self, error: BaseException) -> None:
        if self.enabled:
            self.state = "degraded"
            self.last_error = type(error).__name__
            self.worker_ready = False

    def mark_stopped(self) -> None:
        if self.enabled:
            self.state = "stopped"
            self.worker_ready = False


@dataclass(frozen=True)
class ClaimedEmbedding:
    chunk_id: str
    user_id: str
    attempts: int


@dataclass(frozen=True)
class VectorSearchRecord:
    """One owner-scoped vector hit before hybrid rank fusion."""

    chunk_id: str
    distance: float


def _utc_now() -> datetime:
    return datetime.now(UTC)


async def ensure_vector_index(storage: DatabaseStorage) -> bool:
    """Create the derived vec0 index when the configured SQLite extension is ready."""

    if not isinstance(storage, SQLiteStorage) or not await storage.vector_extension_ready():
        return False
    statement = (
        f"CREATE VIRTUAL TABLE IF NOT EXISTS {VECTOR_TABLE} USING vec0("
        "chunk_id TEXT PRIMARY KEY, "
        "user_id TEXT PARTITION KEY, "
        f"embedding FLOAT[{EMBEDDING_DIMENSIONS}] distance_metric=cosine"
        ")"
    )
    try:
        async with storage.session() as db:
            async with db.begin():
                await db.execute(text(statement))
        return True
    except Exception:
        logger.exception("SQLite vector index initialization failed")
        return False


async def enqueue_chunk_embeddings(
    db: AsyncSession,
    chunks: Sequence[ContentChunk],
    *,
    now: datetime,
) -> None:
    """Create pending embedding records for newly materialized chunks."""

    db.add_all(
        [
            ContentChunkEmbedding(
                chunk_id=chunk.id,
                user_id=chunk.user_id,
                source_version=chunk.source_version,
                model_name=EMBEDDING_MODEL_NAME,
                model_version=EMBEDDING_MODEL_VERSION,
                dimensions=EMBEDDING_DIMENSIONS,
                status="pending",
                attempts=0,
                available_at=now,
                lease_expires_at=None,
                last_error=None,
                created_at=now,
                updated_at=now,
            )
            for chunk in chunks
        ]
    )


async def _claim_batch(
    storage: DatabaseStorage,
    batch_size: int,
    lease_seconds: int,
) -> list[ClaimedEmbedding]:
    now = _utc_now()
    async with storage.session() as db:
        async with db.begin():
            jobs = list(
                (
                    await db.scalars(
                        select(ContentChunkEmbedding)
                        .where(
                            or_(
                                and_(
                                    ContentChunkEmbedding.status == "pending",
                                    ContentChunkEmbedding.available_at <= now,
                                ),
                                and_(
                                    ContentChunkEmbedding.status == "processing",
                                    ContentChunkEmbedding.lease_expires_at.is_not(None),
                                    ContentChunkEmbedding.lease_expires_at < now,
                                ),
                            )
                        )
                        .order_by(
                            ContentChunkEmbedding.available_at.asc(),
                            ContentChunkEmbedding.created_at.asc(),
                            ContentChunkEmbedding.chunk_id.asc(),
                        )
                        .limit(batch_size)
                    )
                ).all()
            )
            for job in jobs:
                job.status = "processing"
                job.attempts += 1
                job.lease_expires_at = now + timedelta(seconds=lease_seconds)
                job.updated_at = now
            await db.flush()
            return [ClaimedEmbedding(job.chunk_id, job.user_id, job.attempts) for job in jobs]


async def _mark_failed(
    storage: DatabaseStorage,
    jobs: Sequence[ClaimedEmbedding],
    error_code: str,
    max_attempts: int,
) -> None:
    now = _utc_now()
    async with storage.session() as db:
        async with db.begin():
            stored = list(
                (
                    await db.scalars(
                        select(ContentChunkEmbedding).where(
                            ContentChunkEmbedding.chunk_id.in_([job.chunk_id for job in jobs])
                        )
                    )
                ).all()
            )
            for job in stored:
                job.lease_expires_at = None
                job.last_error = error_code[:255]
                if job.attempts < max_attempts:
                    job.status = "pending"
                    job.available_at = now + timedelta(seconds=min(60, 2**job.attempts))
                else:
                    job.status = "failed"
                    job.available_at = now
                job.updated_at = now


async def _write_vectors(
    storage: DatabaseStorage,
    jobs: Sequence[ClaimedEmbedding],
    vectors: Sequence[bytes],
) -> int:
    if len(jobs) != len(vectors):
        raise ValueError("embedding provider returned the wrong number of vectors")
    now = _utc_now()
    written = 0
    async with storage.session() as db:
        async with db.begin():
            records = {
                record.chunk_id: record
                for record in (
                    await db.scalars(
                        select(ContentChunkEmbedding).where(
                            ContentChunkEmbedding.chunk_id.in_([job.chunk_id for job in jobs]),
                            ContentChunkEmbedding.status == "processing",
                        )
                    )
                ).all()
            }
            chunks = {
                chunk.id: chunk
                for chunk in (
                    await db.scalars(
                        select(ContentChunk).where(
                            ContentChunk.id.in_([job.chunk_id for job in jobs])
                        )
                    )
                ).all()
            }
            for job, vector in zip(jobs, vectors, strict=True):
                record = records.get(job.chunk_id)
                chunk = chunks.get(job.chunk_id)
                if record is None or chunk is None or record.source_version != chunk.source_version:
                    if record is not None:
                        await db.execute(
                            text(f"DELETE FROM {VECTOR_TABLE} WHERE chunk_id = :chunk_id"),
                            {"chunk_id": job.chunk_id},
                        )
                        await db.delete(record)
                    continue
                await db.execute(
                    text(f"DELETE FROM {VECTOR_TABLE} WHERE chunk_id = :chunk_id"),
                    {"chunk_id": job.chunk_id},
                )
                await db.execute(
                    text(
                        f"INSERT INTO {VECTOR_TABLE} (chunk_id, user_id, embedding) "
                        "VALUES (:chunk_id, :user_id, :embedding)"
                    ),
                    {
                        "chunk_id": job.chunk_id,
                        "user_id": job.user_id,
                        "embedding": vector,
                    },
                )
                record.status = "ready"
                record.lease_expires_at = None
                record.last_error = None
                record.updated_at = now
                written += 1
            await db.flush()
    return written


async def cleanup_orphaned_vectors(storage: DatabaseStorage, *, limit: int = 100) -> int:
    """Remove derived vectors whose durable embedding record was deleted."""

    if not isinstance(storage, SQLiteStorage) or not await storage.vector_extension_ready():
        return 0
    async with storage.session() as db:
        async with db.begin():
            result = await db.execute(
                text(
                    f"SELECT v.chunk_id FROM {VECTOR_TABLE} AS v "
                    "LEFT JOIN content_chunk_embeddings AS e ON e.chunk_id = v.chunk_id "
                    "WHERE e.chunk_id IS NULL LIMIT :limit"
                ),
                {"limit": limit},
            )
            chunk_ids = [row[0] for row in result.all()]
            if chunk_ids:
                await db.execute(
                    text(
                        f"DELETE FROM {VECTOR_TABLE} "
                        "WHERE chunk_id IN ("
                        + ", ".join(f":chunk_id_{index}" for index in range(len(chunk_ids)))
                        + ")"
                    ),
                    {f"chunk_id_{index}": chunk_id for index, chunk_id in enumerate(chunk_ids)},
                )
            return len(chunk_ids)


async def process_embeddings_once(
    storage: DatabaseStorage,
    provider: EmbeddingProvider,
    settings: Settings,
) -> int:
    """Process one leased embedding batch."""

    if not await ensure_vector_index(storage):
        raise EmbeddingUnavailableError("sqlite-vec is unavailable")
    jobs = await _claim_batch(
        storage,
        settings.embedding_batch_size,
        settings.embedding_lease_seconds,
    )
    if not jobs:
        await cleanup_orphaned_vectors(storage)
        return 0
    async with storage.session() as db:
        chunks = {
            chunk.id: chunk
            for chunk in (
                await db.scalars(
                    select(ContentChunk).where(ContentChunk.id.in_([job.chunk_id for job in jobs]))
                )
            ).all()
        }
    valid_jobs = [job for job in jobs if job.chunk_id in chunks]
    if not valid_jobs:
        async with storage.session() as db:
            async with db.begin():
                await db.execute(
                    delete(ContentChunkEmbedding).where(
                        ContentChunkEmbedding.chunk_id.in_([job.chunk_id for job in jobs])
                    )
                )
        return 0
    try:
        vectors = await provider.embed_documents([chunks[job.chunk_id].text for job in valid_jobs])
        written = await _write_vectors(storage, valid_jobs, vectors)
    except Exception:
        logger.exception("Embedding batch failed")
        await _mark_failed(
            storage,
            valid_jobs,
            "embedding_failed",
            settings.embedding_max_attempts,
        )
        raise
    await cleanup_orphaned_vectors(storage)
    return written


async def run_embedding_loop(
    storage: DatabaseStorage,
    provider: EmbeddingProvider,
    settings: Settings,
    health: EmbeddingHealth | None = None,
) -> None:
    """Run the optional restart-safe embedding worker until shutdown."""

    if health is not None:
        health.mark_started()
    logger.info("Embedding worker started")
    try:
        while True:
            try:
                processed = await process_embeddings_once(storage, provider, settings)
                if health is not None and (health.state != "degraded" or processed):
                    health.mark_success()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if health is not None:
                    health.mark_failure(exc)
                logger.exception("Embedding worker poll failed; retrying")
                await asyncio.sleep(settings.embedding_poll_seconds)
                continue
            if not processed:
                await asyncio.sleep(settings.embedding_poll_seconds)
    except asyncio.CancelledError:
        if health is not None:
            health.mark_stopped()
        logger.info("Embedding worker stopped")
        raise


async def search_vectors(
    storage: DatabaseStorage,
    user_id: str,
    query_vector: bytes,
    *,
    source_types: Sequence[str] = (),
    limit: int = 50,
) -> list[VectorSearchRecord]:
    """Return active owner-scoped vector hits ordered by cosine distance."""

    if not isinstance(storage, SQLiteStorage) or not await storage.vector_extension_ready():
        return []
    if not 1 <= limit <= 100:
        raise ValueError("invalid vector search limit")
    unique_types = tuple(dict.fromkeys(source_types))
    invalid = set(unique_types).difference({"note", "task", "file"})
    if invalid:
        raise ValueError("invalid vector source type")
    source_clause = ""
    params: dict[str, object] = {
        "user_id": user_id,
        "query_vector": query_vector,
        "limit": limit,
    }
    if unique_types:
        placeholders = ", ".join(f":vector_source_type_{i}" for i in range(len(unique_types)))
        source_clause = f" AND c.source_type IN ({placeholders})"
        params.update({f"vector_source_type_{i}": value for i, value in enumerate(unique_types)})
    statement = text(
        "WITH vector_hits AS ("
        f"SELECT v.chunk_id, v.distance FROM {VECTOR_TABLE} AS v "
        "WHERE v.embedding MATCH :query_vector "
        "AND v.user_id = :user_id "
        "AND k = :limit"
        ") "
        "SELECT vh.chunk_id, vh.distance "
        "FROM vector_hits AS vh "
        "JOIN content_chunks AS c ON c.id = vh.chunk_id "
        "JOIN content_chunk_embeddings AS e ON e.chunk_id = c.id "
        "WHERE c.user_id = :user_id AND e.status = 'ready' "
        "AND ((c.source_type = 'note' AND EXISTS ("
        "SELECT 1 FROM notes WHERE notes.id = c.source_id "
        "AND notes.user_id = c.user_id AND notes.deleted_at IS NULL)) "
        "OR (c.source_type = 'task' AND EXISTS ("
        "SELECT 1 FROM tasks WHERE tasks.id = c.source_id "
        "AND tasks.user_id = c.user_id AND tasks.deleted_at IS NULL)) "
        "OR (c.source_type = 'file' AND EXISTS ("
        "SELECT 1 FROM files WHERE files.sha256 = c.source_id "
        "AND files.user_id = c.user_id AND files.deleted_at IS NULL)))"
        f"{source_clause}"
    )
    try:
        async with storage.session() as db:
            result = await db.execute(statement, params)
            hits = [
                VectorSearchRecord(chunk_id=row[0], distance=float(row[1])) for row in result.all()
            ]
            return sorted(hits, key=lambda hit: (hit.distance, hit.chunk_id))
    except Exception as exc:
        logger.warning(
            "SQLite vector search unavailable; using FTS5 fallback",
            extra={"error_code": type(exc).__name__},
        )
        return []
