"""Transactional chunk persistence and internal owner-scoped retrieval."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..storage import DatabaseStorage
from .models import ContentChunk
from .text import chunk_text, normalize_source_text

ChunkSourceType = Literal["note", "task", "file"]
MAX_CHUNK_SEARCH_LENGTH = 200
DEFAULT_CHUNK_SEARCH_LIMIT = 20
MAX_CHUNK_SEARCH_LIMIT = 100


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
    """One ranked chunk returned by the internal FTS retrieval contract.

    ``score`` is ``-bm25`` so larger values indicate a stronger SQLite FTS5
    match. Scores are useful for diagnostics and evaluation within one query;
    callers should use ``rank`` as the stable ordering signal.
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
) -> list[ChunkSearchRecord]:
    """Search active owner-scoped chunks using plain-keyword AND semantics.

    The query is trimmed, case-folded, and split into Unicode word tokens.
    Every token must match. Empty or punctuation-only queries return no hits;
    queries longer than :data:`MAX_CHUNK_SEARCH_LENGTH` raise ``ValueError``.
    Results are ordered by SQLite FTS5 relevance with deterministic source and
    chunk tie-breakers, and ranks are one-based.
    """

    if not 1 <= limit <= MAX_CHUNK_SEARCH_LIMIT:
        raise ValueError("invalid chunk search limit")
    fts_query = _fts_query(query)
    if fts_query is None:
        return []
    source_clause, source_params = _source_filter(source_types)
    params: dict[str, object] = {
        "user_id": user_id,
        "fts_query": fts_query,
        "limit": limit,
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
        result = await db.execute(statement, params)
        rows = result.all()
        file_ids_by_hash: dict[str, list[str]] = {}
        file_names_by_hash: dict[str, list[str]] = {}
        file_hashes = {row[3] for row in rows if row[2] == "file"}
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
                file_ids_by_hash.setdefault(source_id, []).append(file_id)
                file_names_by_hash.setdefault(source_id, []).append(file_name)

        return [
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
                score=float(row[8]),
                file_ids=file_ids_by_hash.get(row[3], []),
                file_names=file_names_by_hash.get(row[3], []),
            )
            for rank, row in enumerate(rows, start=1)
        ]
