"""Chunking primitives and internal retrieval behavior."""

import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import select

from cortex_backend.auth.models import User
from cortex_backend.chunking.backfill import (
    BackfillProgress,
    _print_progress,
    run_backfill,
)
from cortex_backend.chunking.models import ContentChunk
from cortex_backend.chunking.service import ChunkSource, replace_source_chunks, search_chunks
from cortex_backend.chunking.text import chunk_text, html_to_chunk_text
from cortex_backend.config import Settings
from cortex_backend.files.models import File
from cortex_backend.memory.models import Note
from cortex_backend.storage import SQLiteStorage
from cortex_backend.tasks.models import Task


def migrate(database_path: Path, monkeypatch) -> None:
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


def test_html_chunk_text_preserves_semantic_blocks() -> None:
    value = html_to_chunk_text(
        "<h1>Heading</h1><p>First paragraph.</p><ul><li>One</li><li>Two</li></ul>"
    )

    assert value == "Heading\n\nFirst paragraph.\n\n- One\n\n- Two"


def test_chunk_text_is_bounded_overlapping_and_lossless_by_content() -> None:
    source = "\n\n".join(
        f"Paragraph {index}: " + " ".join(f"word{index}_{word}" for word in range(80))
        for index in range(30)
    )

    chunks = chunk_text(source)

    assert len(chunks) > 1
    assert all(0 < len(chunk) <= 1_200 for chunk in chunks)
    for paragraph in source.split("\n\n"):
        assert paragraph.split()[0] in "\n".join(chunks)
        assert paragraph.split()[-1] in "\n".join(chunks)
    assert chunks == chunk_text(source)


def test_backfill_progress_prints_source_and_aggregate_percentages(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _print_progress(
        BackfillProgress(
            source="tasks",
            source_processed=2,
            source_total=4,
            processed_total=7,
            total=10,
            notes_processed=5,
            notes_total=5,
            tasks_processed=2,
            tasks_total=4,
            files_processed=0,
            files_total=1,
        )
    )

    assert capsys.readouterr().out == (
        "backfill notes 5/5 (100.0%) | tasks 2/4 (50.0%) | "
        "files 0/1 (0.0%) | overall 7/10 (70.0%)\n"
    )


@pytest.mark.asyncio
async def test_chunk_search_filters_deleted_sources_and_resolves_duplicate_files(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "cortex.db"
    migrate(database_path, monkeypatch)
    storage = SQLiteStorage(database_path)
    await storage.check_ready()
    now = datetime.now(UTC)
    user_id = "00000000-0000-0000-0000-000000000001"
    note_id = "00000000-0000-0000-0000-000000000002"
    task_id = "00000000-0000-0000-0000-000000000003"
    first_file_id = "00000000-0000-0000-0000-000000000004"
    second_file_id = "00000000-0000-0000-0000-000000000005"
    source_hash = "a" * 64

    try:
        async with storage.session() as db:
            async with db.begin():
                db.add(
                    User(
                        id=user_id,
                        email="owner@example.com",
                        password_hash="hash",
                        is_active=True,
                        is_owner=True,
                        created_at=now,
                        updated_at=now,
                        password_changed_at=now,
                    )
                )
                db.add(
                    Note(
                        id=note_id,
                        user_id=user_id,
                        title="Alpha note",
                        body="<p>Beta body</p>",
                        journal_date=None,
                        created_at=now,
                        updated_at=now,
                        deleted_at=None,
                    )
                )
                db.add(
                    Task(
                        id=task_id,
                        user_id=user_id,
                        title="Task title",
                        description="Gamma description",
                        status="todo",
                        priority="none",
                        position=0,
                        start_at=None,
                        due_at=None,
                        created_at=now,
                        updated_at=now,
                        deleted_at=None,
                        series_id=None,
                        occurrence_key=None,
                        series_exception=False,
                        skipped_at=None,
                    )
                )
                for file_id, filename in (
                    (first_file_id, "first.txt"),
                    (second_file_id, "second.txt"),
                ):
                    db.add(
                        File(
                            id=file_id,
                            user_id=user_id,
                            original_name=filename,
                            storage_key=("1" if file_id == first_file_id else "2") * 32 + ".blob",
                            size_bytes=20,
                            sha256=source_hash,
                            created_at=now,
                            updated_at=now,
                            deleted_at=None,
                        )
                    )
                await db.flush()
                await replace_source_chunks(
                    db,
                    ChunkSource(
                        user_id=user_id,
                        source_type="note",
                        source_id=note_id,
                        title="Alpha note",
                        text="Alpha note\n\nBeta body",
                    ),
                )
                await replace_source_chunks(
                    db,
                    ChunkSource(
                        user_id=user_id,
                        source_type="task",
                        source_id=task_id,
                        title="Task title",
                        text="Task title\n\nGamma description",
                    ),
                )
                await replace_source_chunks(
                    db,
                    ChunkSource(
                        user_id=user_id,
                        source_type="file",
                        source_id=source_hash,
                        text="Shared source text",
                    ),
                )

        note_results = await search_chunks(storage, user_id, "alpha beta")
        assert [result.source_id for result in note_results] == [note_id]

        file_results = await search_chunks(storage, user_id, "shared source")
        assert len(file_results) == 1
        assert file_results[0].file_ids == [first_file_id, second_file_id]
        assert file_results[0].file_names == ["first.txt", "second.txt"]

        async with storage.session() as db:
            async with db.begin():
                note = await db.get(Note, note_id)
                assert note is not None
                note.deleted_at = now

        assert await search_chunks(storage, user_id, "alpha beta") == []
    finally:
        await storage.close()


@pytest.mark.asyncio
async def test_chunk_backfill_is_resumable_and_idempotent(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "backfill.db"
    migrate(database_path, monkeypatch)
    storage = SQLiteStorage(database_path)
    await storage.check_ready()
    now = datetime.now(UTC)
    user_id = "00000000-0000-0000-0000-000000000011"
    note_id = "00000000-0000-0000-0000-000000000012"
    task_id = "00000000-0000-0000-0000-000000000013"

    try:
        async with storage.session() as db:
            async with db.begin():
                db.add(
                    User(
                        id=user_id,
                        email="backfill@example.com",
                        password_hash="hash",
                        is_active=True,
                        is_owner=True,
                        created_at=now,
                        updated_at=now,
                        password_changed_at=now,
                    )
                )
                db.add(
                    Note(
                        id=note_id,
                        user_id=user_id,
                        title="Backfill note",
                        body="<p>Note body</p>",
                        journal_date=None,
                        created_at=now,
                        updated_at=now,
                        deleted_at=None,
                    )
                )
                db.add(
                    Task(
                        id=task_id,
                        user_id=user_id,
                        title="Backfill task",
                        description="Task description",
                        status="todo",
                        priority="none",
                        position=0,
                        start_at=None,
                        due_at=None,
                        created_at=now,
                        updated_at=now,
                        deleted_at=None,
                        series_id=None,
                        occurrence_key=None,
                        series_exception=False,
                        skipped_at=None,
                    )
                )

        settings = Settings(
            environment="test",
            database_path=database_path,
            file_storage_path=tmp_path / "files",
        )
        first_progress: list[BackfillProgress] = []
        assert await run_backfill(settings, batch_size=1, on_progress=first_progress.append) == (
            1,
            1,
            0,
        )
        assert first_progress[0].percentage == 0
        assert first_progress[-1].percentage == 100
        assert first_progress[-1].processed_total == first_progress[-1].total == 2
        assert first_progress[-1].notes_processed == first_progress[-1].notes_total == 1
        assert first_progress[-1].tasks_processed == first_progress[-1].tasks_total == 1
        assert first_progress[-1].files_processed == first_progress[-1].files_total == 0

        second_progress: list[BackfillProgress] = []
        assert await run_backfill(settings, batch_size=1, on_progress=second_progress.append) == (
            1,
            1,
            0,
        )
        assert second_progress[-1].percentage == 100

        async with storage.session() as db:
            rows = list((await db.scalars(select(ContentChunk))).all())
        assert len(rows) == 2
        assert {row.source_id for row in rows} == {note_id, task_id}
    finally:
        await storage.close()
