"""Task API behavior over a migrated temporary SQLite database."""

import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from cortex_backend.app import create_app
from cortex_backend.config import Settings


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
async def client(tmp_path, monkeypatch):
    database_path = tmp_path / "cortex.db"
    migrate(database_path, monkeypatch)
    settings = Settings(
        environment="test",
        database_path=database_path,
        setup_secret=SecretStr("test-setup-secret"),
    )
    app = create_app(settings=settings)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as test_client:
        yield test_client
    await app.state.storage.close()


async def setup_owner(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/setup",
        headers={"X-Setup-Secret": "test-setup-secret"},
        json={"email": "owner@example.com", "password": "correct horse battery staple"},
    )
    assert response.status_code == 201


async def csrf_headers(client: AsyncClient) -> dict[str, str]:
    token = client.cookies.get("cortex_csrf")
    assert token is not None
    return {"Origin": "http://testserver", "X-CSRF-Token": token}


async def create_task(client: AsyncClient, payload: dict[str, object]):
    return await client.post(
        "/api/v1/tasks",
        headers=await csrf_headers(client),
        json=payload,
    )


async def test_tasks_require_authentication(client: AsyncClient) -> None:
    response = await client.get("/api/v1/tasks")

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "unauthenticated"


async def test_task_crud_normalizes_tags_and_soft_deletes(client: AsyncClient) -> None:
    await setup_owner(client)
    created = await create_task(
        client,
        {
            "title": "  Plan the week  ",
            "description": "Capture the important work.",
            "status": "todo",
            "priority": "high",
            "start_at": "2027-01-01T09:00:00+08:00",
            "due_at": "2027-01-02T17:00:00+08:00",
            "tags": [" Work ", "WORK", "Focus"],
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["title"] == "Plan the week"
    assert body["status"] == "todo"
    assert body["priority"] == "high"
    assert body["tags"] == ["focus", "work"]

    task_id = body["id"]
    fetched = await client.get(f"/api/v1/tasks/{task_id}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == task_id

    updated = await client.patch(
        f"/api/v1/tasks/{task_id}",
        headers=await csrf_headers(client),
        json={"description": None, "start_at": None, "tags": ["Home", "home"]},
    )
    assert updated.status_code == 200
    updated_body = updated.json()
    assert updated_body["description"] is None
    assert updated_body["start_at"] is None
    assert updated_body["due_at"] == "2027-01-02T09:00:00Z"
    assert updated_body["tags"] == ["home"]

    deleted = await client.delete(
        f"/api/v1/tasks/{task_id}",
        headers=await csrf_headers(client),
    )
    assert deleted.status_code == 204
    assert (await client.get(f"/api/v1/tasks/{task_id}")).status_code == 404
    assert (await client.get("/api/v1/tasks")).json() == {
        "items": [],
        "next_cursor": None,
    }


async def test_task_list_filters_and_cursor_pagination(client: AsyncClient) -> None:
    await setup_owner(client)
    tasks = [
        {
            "title": "Later focused work",
            "status": "todo",
            "priority": "high",
            "due_at": "2027-01-03T09:00:00Z",
            "tags": ["work", "focus"],
        },
        {
            "title": "Soon work",
            "description": "Review the focus plan.",
            "status": "backlog",
            "priority": "low",
            "due_at": "2027-01-01T09:00:00Z",
            "tags": ["work"],
        },
        {
            "title": "Undated focused work",
            "status": "done",
            "priority": "none",
            "tags": ["work", "focus"],
        },
    ]
    for payload in tasks:
        response = await create_task(client, payload)
        assert response.status_code == 201

    first_page = await client.get("/api/v1/tasks", params={"limit": 2})
    assert first_page.status_code == 200
    first_body = first_page.json()
    assert [item["title"] for item in first_body["items"]] == [
        "Soon work",
        "Later focused work",
    ]
    assert first_body["next_cursor"]

    second_page = await client.get(
        "/api/v1/tasks",
        params={"limit": 2, "cursor": first_body["next_cursor"]},
    )
    assert second_page.status_code == 200
    assert [item["title"] for item in second_page.json()["items"]] == ["Undated focused work"]
    assert second_page.json()["next_cursor"] is None

    filtered = await client.get(
        "/api/v1/tasks",
        params=[("tag", "work"), ("tag", "focus"), ("status", "todo")],
    )
    assert [item["title"] for item in filtered.json()["items"]] == ["Later focused work"]

    invalid_cursor = await client.get("/api/v1/tasks", params={"cursor": "not-a-cursor"})
    assert invalid_cursor.status_code == 400
    assert invalid_cursor.json()["detail"]["code"] == "invalid_task_cursor"

    title_search = await client.get("/api/v1/tasks", params={"search": "later focused"})
    assert [item["title"] for item in title_search.json()["items"]] == ["Later focused work"]

    tag_search = await client.get("/api/v1/tasks", params={"search": "focus"})
    assert [item["title"] for item in tag_search.json()["items"]] == [
        "Soon work",
        "Later focused work",
        "Undated focused work",
    ]

    description_search = await client.get("/api/v1/tasks", params={"search": "review"})
    assert [item["title"] for item in description_search.json()["items"]] == ["Soon work"]

    search_cursor = await client.get(
        "/api/v1/tasks",
        params={"limit": 1},
    )
    search_cursor_value = search_cursor.json()["next_cursor"]
    assert search_cursor_value
    changed_filter_cursor = await client.get(
        "/api/v1/tasks",
        params={"limit": 1, "cursor": search_cursor_value, "search": "work"},
    )
    assert changed_filter_cursor.status_code == 400
    assert changed_filter_cursor.json()["detail"]["code"] == "invalid_task_cursor"


async def test_task_list_scheduled_range_includes_overlapping_windows(client: AsyncClient) -> None:
    await setup_owner(client)
    payloads = [
        {
            "title": "Spans into range",
            "start_at": "2027-01-31T09:00:00Z",
            "due_at": "2027-02-02T17:00:00Z",
        },
        {
            "title": "Starts in range",
            "start_at": "2027-02-05T09:00:00Z",
        },
        {
            "title": "Due in range",
            "due_at": "2027-02-06T17:00:00Z",
        },
        {
            "title": "Ends at range start",
            "start_at": "2027-01-30T09:00:00Z",
            "due_at": "2027-02-01T00:00:00Z",
        },
        {
            "title": "Starts at range end",
            "start_at": "2027-02-10T00:00:00Z",
        },
        {"title": "Outside range", "due_at": "2027-01-20T17:00:00Z"},
        {"title": "Undated"},
    ]
    for payload in payloads:
        response = await create_task(client, payload)
        assert response.status_code == 201

    params = {
        "scheduled_from": "2027-02-01T00:00:00Z",
        "scheduled_to": "2027-02-10T00:00:00Z",
    }
    filtered = await client.get("/api/v1/tasks", params=params)
    assert filtered.status_code == 200
    assert {item["title"] for item in filtered.json()["items"]} == {
        "Spans into range",
        "Starts in range",
        "Due in range",
        "Ends at range start",
    }

    first_page = await client.get(
        "/api/v1/tasks",
        params={**params, "limit": 2},
    )
    cursor = first_page.json()["next_cursor"]
    assert cursor
    changed_range = await client.get(
        "/api/v1/tasks",
        params={
            **params,
            "scheduled_from": "2027-02-02T00:00:00Z",
            "limit": 2,
            "cursor": cursor,
        },
    )
    assert changed_range.status_code == 400
    assert changed_range.json()["detail"]["code"] == "invalid_task_cursor"


async def test_task_summary_counts_views_and_tags(client: AsyncClient, monkeypatch) -> None:
    await setup_owner(client)
    now = datetime(2027, 1, 15, 9, 0, tzinfo=UTC)
    monkeypatch.setattr("cortex_backend.tasks.service._utc_now", lambda: now)
    today_at_noon = now.replace(hour=12, minute=0, second=0, microsecond=0)
    tomorrow_at_noon = (now + timedelta(days=1)).replace(
        hour=12,
        minute=0,
        second=0,
        microsecond=0,
    )
    payloads = [
        {
            "title": "Today high priority",
            "status": "todo",
            "priority": "high",
            "due_at": today_at_noon.isoformat(),
            "tags": ["work"],
        },
        {
            "title": "Tomorrow work",
            "status": "backlog",
            "due_at": tomorrow_at_noon.isoformat(),
            "tags": ["work"],
        },
        {
            "title": "Yesterday personal",
            "status": "in_progress",
            "priority": "high",
            "due_at": (now - timedelta(days=1)).isoformat(),
            "tags": ["personal"],
        },
        {
            "title": "Done today admin",
            "status": "done",
            "priority": "high",
            "due_at": today_at_noon.isoformat(),
            "tags": ["admin"],
        },
        {
            "title": "Canceled tomorrow",
            "status": "canceled",
            "due_at": tomorrow_at_noon.isoformat(),
            "tags": ["admin"],
        },
        {
            "title": "Done overdue",
            "status": "done",
            "due_at": (now - timedelta(days=1)).isoformat(),
            "tags": ["admin"],
        },
        {
            "title": "Canceled overdue",
            "status": "canceled",
            "due_at": (now - timedelta(days=2)).isoformat(),
            "tags": ["admin"],
        },
    ]
    created_ids: list[str] = []
    for payload in payloads:
        response = await create_task(client, payload)
        assert response.status_code == 201
        created_ids.append(response.json()["id"])

    deleted = await client.delete(
        f"/api/v1/tasks/{created_ids[-1]}",
        headers=await csrf_headers(client),
    )
    assert deleted.status_code == 204

    summary = await client.get("/api/v1/tasks/summary", params={"timezone": "UTC"})
    assert summary.status_code == 200
    assert summary.json() == {
        "all": 6,
        "today": 1,
        "upcoming": 1,
        "overdue": 1,
        "high_priority": 2,
        "tags": [
            {"name": "admin", "count": 3},
            {"name": "personal", "count": 1},
            {"name": "work", "count": 2},
        ],
    }

    invalid_timezone = await client.get(
        "/api/v1/tasks/summary",
        params={"timezone": "Not/A_Timezone"},
    )
    assert invalid_timezone.status_code == 422
    assert invalid_timezone.json()["detail"]["code"] == "invalid_task_summary_timezone"


async def test_task_date_validation_has_stable_error(client: AsyncClient) -> None:
    await setup_owner(client)
    response = await create_task(
        client,
        {
            "title": "Invalid window",
            "start_at": "2027-01-02T10:00:00Z",
            "due_at": "2027-01-02T09:00:00Z",
        },
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": {
            "code": "invalid_task_dates",
            "message": "The task start time must be before or equal to its due time.",
        }
    }


async def test_mcp_task_tool_uses_the_shared_service(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "cortex.db"
    migrate(database_path, monkeypatch)
    app = create_app(
        settings=Settings(
            environment="test",
            database_path=database_path,
            setup_secret=SecretStr("test-setup-secret"),
        )
    )

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as test_client:
            await setup_owner(test_client)
            session_token = test_client.cookies.get("cortex_session")
            assert session_token is not None
            headers = {
                "Authorization": f"Bearer {session_token}",
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
            }
            initialized = await test_client.post(
                "/mcp/",
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {},
                        "clientInfo": {"name": "test", "version": "1.0"},
                    },
                },
            )
            assert initialized.status_code == 200
            session_id = initialized.headers.get("mcp-session-id")
            if session_id:
                headers["Mcp-Session-Id"] = session_id

            await test_client.post(
                "/mcp/",
                headers=headers,
                json={"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
            )
            created = await test_client.post(
                "/mcp/",
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "create_task",
                        "arguments": {"payload": {"title": "Captured by MCP"}},
                    },
                },
            )
            assert created.status_code == 200
            assert "Captured by MCP" in created.text

            scheduled = await create_task(
                test_client,
                {
                    "title": "Scheduled task",
                    "start_at": "2027-02-05T09:00:00Z",
                    "due_at": "2027-02-05T17:00:00Z",
                },
            )
            assert scheduled.status_code == 201

            rest_list = await test_client.get("/api/v1/tasks")
            assert {item["title"] for item in rest_list.json()["items"]} == {
                "Captured by MCP",
                "Scheduled task",
            }

            searched = await test_client.post(
                "/mcp/",
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "list_tasks",
                        "arguments": {"search": "captured"},
                    },
                },
            )
            assert searched.status_code == 200
            assert "Captured by MCP" in searched.text

            scheduled_list = await test_client.post(
                "/mcp/",
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "tools/call",
                    "params": {
                        "name": "list_tasks",
                        "arguments": {
                            "scheduled_from": "2027-02-01T00:00:00Z",
                            "scheduled_to": "2027-02-10T00:00:00Z",
                        },
                    },
                },
            )
            assert scheduled_list.status_code == 200
            assert "Scheduled task" in scheduled_list.text
            assert "Captured by MCP" not in scheduled_list.text

            summary = await test_client.post(
                "/mcp/",
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 5,
                    "method": "tools/call",
                    "params": {
                        "name": "get_task_summary",
                        "arguments": {"timezone": "UTC"},
                    },
                },
            )
            assert summary.status_code == 200
            assert '"all":2' in summary.text.replace(" ", "")
