"""Fixture loading, seeding, and quality calculations for retrieval evaluation."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.models import User
from ..files.models import File
from ..memory.models import Note
from ..storage import DatabaseStorage
from ..tasks.models import Task
from .service import ChunkSearchRecord, ChunkSource, ChunkSourceType, replace_source_chunks

FIXTURE_VERSION = 1
DEFAULT_RECALL_K = 5


@dataclass(frozen=True)
class EvaluationSource:
    """One fixture source that can be indexed as a note, task, or file."""

    owner: str
    source_type: ChunkSourceType
    source_id: str
    title: str | None
    text: str
    active: bool


@dataclass(frozen=True)
class ExpectedHit:
    """A stable source-coordinate reference to one expected chunk."""

    source_type: ChunkSourceType
    source_id: str
    ordinal: int


@dataclass(frozen=True)
class EvaluationQuery:
    """One query and its expected chunk coordinates."""

    id: str
    owner: str
    query: str
    semantic_query: str | None
    source_types: tuple[ChunkSourceType, ...]
    limit: int
    expected: tuple[ExpectedHit, ...]


@dataclass(frozen=True)
class EvaluationFixture:
    """Validated retrieval evaluation data loaded from JSON."""

    version: int
    sources: tuple[EvaluationSource, ...]
    queries: tuple[EvaluationQuery, ...]


@dataclass(frozen=True)
class QueryEvaluation:
    """Quality measurements for one evaluated query."""

    query_id: str
    expected_count: int
    matched_count: int
    recall: float | None
    reciprocal_rank: float | None
    returned_count: int
    zero_results: bool


def fixture_owner_id(owner: str) -> str:
    """Return a stable database user ID for one fixture owner label."""

    return str(uuid5(NAMESPACE_URL, f"cortex-fixture-owner:{owner}"))


def _mapping(value: object, context: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{context} must be an object")
    return {str(key): item for key, item in value.items()}


def _string(value: object, context: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{context} must be a string")
    return value


def _optional_string(value: object, context: str) -> str | None:
    if value is None:
        return None
    return _string(value, context)


def _boolean(value: object, context: str, *, default: bool | None = None) -> bool:
    if value is None and default is not None:
        return default
    if not isinstance(value, bool):
        raise ValueError(f"{context} must be a boolean")
    return value


def _integer(value: object, context: str, *, default: int | None = None) -> int:
    if value is None and default is not None:
        return default
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{context} must be an integer")
    return value


def _list(value: object, context: str, *, default: list[object] | None = None) -> list[object]:
    if value is None and default is not None:
        return default
    if not isinstance(value, list):
        raise ValueError(f"{context} must be an array")
    return value


def _source_type(value: object, context: str) -> ChunkSourceType:
    source_type = _string(value, context)
    if source_type not in {"note", "task", "file"}:
        raise ValueError(f"{context} must be note, task, or file")
    return cast(ChunkSourceType, source_type)


def load_fixture(path: Path) -> EvaluationFixture:
    """Load and validate one checked-in retrieval fixture."""

    root = _mapping(json.loads(path.read_text(encoding="utf-8")), "fixture")
    version = _integer(root.get("version"), "fixture.version")
    if version != FIXTURE_VERSION:
        raise ValueError(f"unsupported fixture version: {version}")

    sources: list[EvaluationSource] = []
    source_keys: set[tuple[str, str, str]] = set()
    database_keys: set[tuple[str, str]] = set()
    for index, raw_source in enumerate(_list(root.get("sources"), "fixture.sources")):
        source = _mapping(raw_source, f"fixture.sources[{index}]")
        owner = _string(source.get("owner"), f"fixture.sources[{index}].owner")
        source_type = _source_type(
            source.get("source_type"),
            f"fixture.sources[{index}].source_type",
        )
        source_id = _string(source.get("source_id"), f"fixture.sources[{index}].source_id")
        title = _optional_string(source.get("title"), f"fixture.sources[{index}].title")
        source_text = _string(source.get("text"), f"fixture.sources[{index}].text")
        if not source_text.strip():
            raise ValueError(f"fixture.sources[{index}].text must contain content")
        source_key = (owner, source_type, source_id)
        if source_key in source_keys:
            raise ValueError(f"duplicate fixture source: {source_key}")
        database_key = (source_type, source_id)
        if database_key in database_keys:
            raise ValueError(f"source IDs must be globally unique in fixture: {database_key}")
        source_keys.add(source_key)
        database_keys.add(database_key)
        sources.append(
            EvaluationSource(
                owner=owner,
                source_type=source_type,
                source_id=source_id,
                title=title,
                text=source_text,
                active=_boolean(
                    source.get("active"),
                    f"fixture.sources[{index}].active",
                    default=True,
                ),
            )
        )

    queries: list[EvaluationQuery] = []
    query_ids: set[str] = set()
    for index, raw_query in enumerate(_list(root.get("queries"), "fixture.queries")):
        query = _mapping(raw_query, f"fixture.queries[{index}]")
        query_id = _string(query.get("id"), f"fixture.queries[{index}].id")
        if query_id in query_ids:
            raise ValueError(f"duplicate fixture query: {query_id}")
        query_ids.add(query_id)
        owner = _string(query.get("owner"), f"fixture.queries[{index}].owner")
        query_text = _string(query.get("query"), f"fixture.queries[{index}].query")
        semantic_query = _optional_string(
            query.get("semantic_query"),
            f"fixture.queries[{index}].semantic_query",
        )
        source_types = tuple(
            _source_type(value, f"fixture.queries[{index}].source_types[]")
            for value in _list(
                query.get("source_types"),
                f"fixture.queries[{index}].source_types",
                default=[],
            )
        )
        if len(set(source_types)) != len(source_types):
            raise ValueError(f"fixture.queries[{index}].source_types contains duplicates")
        limit = _integer(query.get("limit"), f"fixture.queries[{index}].limit", default=5)
        if not 1 <= limit <= 100:
            raise ValueError(f"fixture.queries[{index}].limit must be between 1 and 100")

        expected: list[ExpectedHit] = []
        expected_keys: set[tuple[str, str, int]] = set()
        for expected_index, raw_expected in enumerate(
            _list(
                query.get("expected"),
                f"fixture.queries[{index}].expected",
                default=[],
            )
        ):
            expected_value = _mapping(
                raw_expected,
                f"fixture.queries[{index}].expected[{expected_index}]",
            )
            expected_source_type = _source_type(
                expected_value.get("source_type"),
                f"fixture.queries[{index}].expected[{expected_index}].source_type",
            )
            expected_source_id = _string(
                expected_value.get("source_id"),
                f"fixture.queries[{index}].expected[{expected_index}].source_id",
            )
            ordinal = _integer(
                expected_value.get("ordinal"),
                f"fixture.queries[{index}].expected[{expected_index}].ordinal",
            )
            if ordinal < 0:
                raise ValueError("expected chunk ordinal cannot be negative")
            expected_key = (expected_source_type, expected_source_id, ordinal)
            if expected_key in expected_keys:
                raise ValueError(f"duplicate expected hit: {expected_key}")
            if (owner, expected_source_type, expected_source_id) not in source_keys:
                raise ValueError(f"expected hit is not owned by query owner: {expected_key}")
            expected_keys.add(expected_key)
            expected.append(ExpectedHit(*expected_key))

        queries.append(
            EvaluationQuery(
                id=query_id,
                owner=owner,
                query=query_text,
                semantic_query=semantic_query,
                source_types=source_types,
                limit=limit,
                expected=tuple(expected),
            )
        )

    return EvaluationFixture(version=version, sources=tuple(sources), queries=tuple(queries))


def _fixture_file_id(source: EvaluationSource) -> str:
    return str(uuid5(NAMESPACE_URL, f"cortex-fixture-file:{source.owner}:{source.source_id}"))


def _fixture_storage_key(source: EvaluationSource) -> str:
    storage_id = uuid5(
        NAMESPACE_URL,
        f"cortex-fixture-storage:{source.owner}:{source.source_id}",
    )
    return f"{storage_id.hex}.blob"


async def _add_source_rows(
    db: AsyncSession,
    fixture: EvaluationFixture,
    now: datetime,
) -> None:
    owners = sorted({source.owner for source in fixture.sources})
    for index, owner in enumerate(owners):
        db.add(
            User(
                id=fixture_owner_id(owner),
                email=f"{owner}@fixture.invalid",
                password_hash="fixture-only-password-hash",
                is_active=True,
                is_owner=index == 0,
                created_at=now,
                updated_at=now,
                password_changed_at=now,
            )
        )
    await db.flush()

    for source in fixture.sources:
        user_id = fixture_owner_id(source.owner)
        deleted_at = None if source.active else now
        if source.source_type == "note":
            db.add(
                Note(
                    id=source.source_id,
                    user_id=user_id,
                    title=source.title,
                    body="<p>Fixture source</p>",
                    journal_date=None,
                    created_at=now,
                    updated_at=now,
                    deleted_at=deleted_at,
                )
            )
        elif source.source_type == "task":
            db.add(
                Task(
                    id=source.source_id,
                    user_id=user_id,
                    title=source.title or "Fixture task",
                    description="Fixture source",
                    status="todo",
                    priority="none",
                    position=0,
                    start_at=None,
                    due_at=None,
                    created_at=now,
                    updated_at=now,
                    deleted_at=deleted_at,
                    series_id=None,
                    occurrence_key=None,
                    series_exception=False,
                    skipped_at=None,
                )
            )
        else:
            db.add(
                File(
                    id=_fixture_file_id(source),
                    user_id=user_id,
                    original_name=source.title or "fixture.txt",
                    storage_key=_fixture_storage_key(source),
                    size_bytes=len(source.text.encode("utf-8")),
                    sha256=source.source_id,
                    created_at=now,
                    updated_at=now,
                    deleted_at=deleted_at,
                )
            )
    await db.flush()


async def seed_fixture(storage: DatabaseStorage, fixture: EvaluationFixture) -> None:
    """Create fixture domain rows and index their canonical chunk sources."""

    now = datetime(2026, 1, 1, tzinfo=UTC)
    async with storage.session() as db:
        async with db.begin():
            await _add_source_rows(db, fixture, now)
            for source in fixture.sources:
                await replace_source_chunks(
                    db,
                    ChunkSource(
                        user_id=fixture_owner_id(source.owner),
                        source_type=source.source_type,
                        source_id=source.source_id,
                        title=source.title,
                        text=source.text,
                    ),
                    now=now,
                )


def _hit_key(hit: ChunkSearchRecord) -> tuple[ChunkSourceType, str, int]:
    return hit.source_type, hit.source_id, hit.ordinal


def evaluate_query(
    query: EvaluationQuery,
    hits: Iterable[ChunkSearchRecord],
    *,
    recall_k: int = DEFAULT_RECALL_K,
) -> QueryEvaluation:
    """Calculate recall, reciprocal rank, and empty-result status for a query."""

    if recall_k < 1:
        raise ValueError("recall_k must be positive")
    hit_list = list(hits)
    expected_keys = {_expected_key for _expected_key in query.expected}
    expected_coordinates = {
        (expected.source_type, expected.source_id, expected.ordinal) for expected in expected_keys
    }
    top_keys = {_hit_key(hit) for hit in hit_list[:recall_k]}
    matched_count = len(expected_coordinates.intersection(top_keys))
    recall = matched_count / len(expected_coordinates) if expected_coordinates else None
    reciprocal_rank: float | None = None
    if expected_coordinates:
        for hit in hit_list:
            if _hit_key(hit) in expected_coordinates:
                reciprocal_rank = 1 / hit.rank
                break
        if reciprocal_rank is None:
            reciprocal_rank = 0.0
    return QueryEvaluation(
        query_id=query.id,
        expected_count=len(expected_coordinates),
        matched_count=matched_count,
        recall=recall,
        reciprocal_rank=reciprocal_rank,
        returned_count=len(hit_list),
        zero_results=not hit_list,
    )
