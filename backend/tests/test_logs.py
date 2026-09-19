"""Activity-log service behavior over a migrated temporary SQLite database."""

import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from cortex_backend.auth.models import User
from cortex_backend.logs.errors import (
    InvalidActivityLogCursorError,
    InvalidActivityLogQueryError,
)
from cortex_backend.logs.schemas import MAX_METADATA_BYTES, ActivityLogCreateRequest
from cortex_backend.logs.service import ActivityLogFilters, append_log, list_logs
from cortex_backend.storage import SQLiteStorage

USER_ID = "00000000-0000-0000-0000-000000000001"
OTHER_USER_ID = "00000000-0000-0000-0000-000000000002"


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


@pytest.fixture
async def storage(tmp_path, monkeypatch):
    database_path = tmp_path / "cortex.db"
    migrate(database_path, monkeypatch)
    database = SQLiteStorage(database_path)
    await database.check_ready()

    now = datetime.now(UTC)
    async with database.session() as session:
        async with session.begin():
            session.add_all(
                [
                    User(
                        id=USER_ID,
                        email="owner@example.com",
                        password_hash="not-used-in-service-test",
                        is_active=True,
                        is_owner=True,
                        created_at=now,
                        updated_at=now,
                        password_changed_at=now,
                    ),
                    User(
                        id=OTHER_USER_ID,
                        email="other@example.com",
                        password_hash="not-used-in-service-test",
                        is_active=True,
                        is_owner=False,
                        created_at=now,
                        updated_at=now,
                        password_changed_at=now,
                    ),
                ]
            )

    yield database
    await database.close()


def payload(
    event_type: str,
    *,
    entity_type: str | None = "task",
    entity_id: str | None = None,
    metadata: dict[str, object] | None = None,
) -> ActivityLogCreateRequest:
    return ActivityLogCreateRequest(
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id or str(uuid4()),
        metadata=metadata or {},
    )


async def test_append_and_list_return_owner_scoped_records(storage) -> None:
    first = await append_log(
        storage,
        USER_ID,
        payload("task.created", entity_id="task-1", metadata={"source": "test"}),
    )
    await append_log(storage, OTHER_USER_ID, payload("task.created", entity_id="other-task"))
    second = await append_log(
        storage,
        USER_ID,
        payload("task.updated", entity_id="task-1", metadata={"status": "done"}),
    )

    page = await list_logs(storage, USER_ID)

    assert {record.id for record in page.items} == {first.id, second.id}
    assert all(record.user_id == USER_ID for record in page.items)
    assert page.items == sorted(
        page.items,
        key=lambda record: (record.created_at, record.id),
        reverse=True,
    )


async def test_list_filters_and_cursor_pagination(storage) -> None:
    records = [
        await append_log(storage, USER_ID, payload("task.created", entity_id="task-1")),
        await append_log(storage, USER_ID, payload("task.updated", entity_id="task-1")),
        await append_log(storage, USER_ID, payload("note.created", entity_type="note")),
    ]

    filtered = await list_logs(
        storage,
        USER_ID,
        ActivityLogFilters(event_type="task.created"),
    )
    assert [record.id for record in filtered.items] == [records[0].id]

    first_page = await list_logs(storage, USER_ID, ActivityLogFilters(limit=2))
    assert first_page.next_cursor is not None
    second_page = await list_logs(
        storage,
        USER_ID,
        ActivityLogFilters(limit=2, cursor=first_page.next_cursor),
    )
    assert second_page.next_cursor is None
    assert {record.id for record in first_page.items + second_page.items} == {
        record.id for record in records
    }


async def test_invalid_cursors_and_limits_have_stable_errors(storage) -> None:
    with pytest.raises(InvalidActivityLogCursorError):
        await list_logs(storage, USER_ID, ActivityLogFilters(cursor="not-a-cursor"))

    with pytest.raises(InvalidActivityLogQueryError):
        await list_logs(storage, USER_ID, ActivityLogFilters(limit=101))


def test_activity_log_metadata_is_bounded_json() -> None:
    with pytest.raises(ValidationError):
        ActivityLogCreateRequest(event_type=" ")

    with pytest.raises(ValidationError):
        ActivityLogCreateRequest(event_type="test", metadata={"value": object()})

    with pytest.raises(ValidationError):
        ActivityLogCreateRequest(
            event_type="test",
            metadata={"value": "x" * MAX_METADATA_BYTES},
        )
