"""Evaluation fixture coverage for the internal FTS retrieval contract."""

import json
import math
import os
import subprocess
import sys
from pathlib import Path

import pytest

from cortex_backend.chunking.evaluation import (
    evaluate_query,
    fixture_owner_id,
    load_fixture,
    seed_fixture,
)
from cortex_backend.chunking.service import search_chunks
from cortex_backend.storage import SQLiteStorage

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "retrieval" / "fts_baseline.json"


def migrate(database_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Apply the checked-in migrations to a temporary database."""

    monkeypatch.setenv("CORTEX_DATABASE_PATH", str(database_path))
    backend_path = Path(__file__).parents[1]
    subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            str(backend_path / "alembic.ini"),
            "upgrade",
            "head",
        ],
        cwd=backend_path,
        env=os.environ.copy(),
        check=True,
    )


def test_fixture_is_readable_and_versioned() -> None:
    fixture = load_fixture(FIXTURE_PATH)

    assert fixture.version == 1
    assert len(fixture.sources) == 6
    assert len(fixture.queries) == 8
    assert json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))["version"] == fixture.version


@pytest.mark.asyncio
async def test_fixture_queries_cover_quality_and_privacy_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "retrieval-evaluation.db"
    migrate(database_path, monkeypatch)
    fixture = load_fixture(FIXTURE_PATH)
    storage = SQLiteStorage(database_path)
    await storage.check_ready()

    try:
        await seed_fixture(storage, fixture)
        for query in fixture.queries:
            first = await search_chunks(
                storage,
                fixture_owner_id(query.owner),
                query.query,
                source_types=query.source_types,
                limit=query.limit,
            )
            second = await search_chunks(
                storage,
                fixture_owner_id(query.owner),
                query.query,
                source_types=query.source_types,
                limit=query.limit,
            )

            assert [hit.rank for hit in first] == list(range(1, len(first) + 1))
            assert all(math.isfinite(hit.score) for hit in first)
            assert all(
                first[index].score >= first[index + 1].score for index in range(len(first) - 1)
            )
            assert [(hit.source_type, hit.source_id, hit.ordinal, hit.rank) for hit in first] == [
                (hit.source_type, hit.source_id, hit.ordinal, hit.rank) for hit in second
            ]

            evaluation = evaluate_query(query, first)
            if query.expected:
                assert evaluation.recall == 1.0, query.id
                assert evaluation.reciprocal_rank is not None
            else:
                assert evaluation.zero_results, query.id
    finally:
        await storage.close()


@pytest.mark.asyncio
async def test_search_contract_handles_empty_queries_and_rejects_invalid_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "retrieval-contract.db"
    migrate(database_path, monkeypatch)
    fixture = load_fixture(FIXTURE_PATH)
    storage = SQLiteStorage(database_path)
    await storage.check_ready()

    try:
        await seed_fixture(storage, fixture)
        user_id = fixture_owner_id("owner-a")
        assert await search_chunks(storage, user_id, "   ") == []
        assert await search_chunks(storage, user_id, "!!!") == []
        assert await search_chunks(storage, user_id, "quarterly bananas") == []

        with pytest.raises(ValueError, match="too long"):
            await search_chunks(storage, user_id, "x" * 201)
        with pytest.raises(ValueError, match="invalid chunk search limit"):
            await search_chunks(storage, user_id, "tax", limit=0)
        with pytest.raises(ValueError, match="invalid chunk source type"):
            await search_chunks(storage, user_id, "tax", source_types=["calendar"])  # type: ignore[list-item]
    finally:
        await storage.close()
