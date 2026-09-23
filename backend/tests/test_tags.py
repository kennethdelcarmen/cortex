"""REST behavior for the shared owner-scoped tag catalog."""

import os
import subprocess
import sys
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from cortex_backend.app import create_app
from cortex_backend.config import Settings


def migrate(database_path: Path, monkeypatch) -> None:
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
    app = create_app(
        settings=Settings(
            environment="test",
            database_path=database_path,
            setup_secret=SecretStr("test-setup-secret"),
        )
    )
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as test_client:
        yield test_client
    await app.state.storage.close()


@asynccontextmanager
async def mcp_client(tmp_path, monkeypatch):
    database_path = tmp_path / "mcp-cortex.db"
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
            yield test_client


async def csrf_headers(client: AsyncClient) -> dict[str, str]:
    token = client.cookies.get("cortex_csrf")
    assert token is not None
    return {"Origin": "http://testserver", "X-CSRF-Token": token}


async def mcp_headers(client: AsyncClient) -> dict[str, str]:
    token = client.cookies.get("cortex_session")
    assert token is not None
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }


async def initialize_mcp(client: AsyncClient) -> dict[str, str]:
    headers = await mcp_headers(client)
    initialized = await client.post(
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
    notification = await client.post(
        "/mcp/",
        headers=headers,
        json={"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
    )
    assert notification.status_code in {200, 202}
    return headers


async def setup_owner(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/setup",
        headers={"X-Setup-Secret": "test-setup-secret"},
        json={
            "email": "owner@example.com",
            "password": "correct horse battery staple",
            "use_setup_secret_as_mcp_key": True,
        },
    )
    assert response.status_code == 201


async def test_mcp_lists_and_applies_existing_tags_only(tmp_path, monkeypatch) -> None:
    async with mcp_client(tmp_path, monkeypatch) as client:
        await setup_owner(client)
        created = await client.post(
            "/api/v1/tags",
            headers=await csrf_headers(client),
            json={"name": "work", "color": "sea-glass"},
        )
        assert created.status_code == 201
        headers = await initialize_mcp(client)

        listed = await client.post(
            "/mcp/",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "list_tags", "arguments": {}},
            },
        )
        assert listed.status_code == 200
        assert '"name":"work"' in listed.text.replace(" ", "")
        assert '"color":"sea-glass"' in listed.text.replace(" ", "")

        created_task = await client.post(
            "/mcp/",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "create_task",
                    "arguments": {"payload": {"title": "Tagged MCP task", "tags": ["work"]}},
                },
            },
        )
        assert created_task.status_code == 200
        assert "Tagged MCP task" in created_task.text

        tools = await client.post(
            "/mcp/",
            headers=headers,
            json={"jsonrpc": "2.0", "id": 4, "method": "tools/list", "params": {}},
        )
        assert tools.status_code == 200
        assert "list_tags" in tools.text
        assert "create_tag" not in tools.text
        assert "permanently_delete_tag" not in tools.text


async def test_tag_crud_supports_named_colors_and_archiving(client: AsyncClient) -> None:
    await setup_owner(client)

    created = await client.post(
        "/api/v1/tags",
        headers=await csrf_headers(client),
        json={"name": " Work ", "color": "sea-glass"},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["name"] == "work"
    assert body["color"] == "sea-glass"
    assert body["active"] is True
    tag_id = body["id"]

    updated = await client.patch(
        f"/api/v1/tags/{tag_id}",
        headers=await csrf_headers(client),
        json={"name": "Projects", "color": "violet"},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "projects"
    assert updated.json()["color"] == "violet"

    archived = await client.delete(
        f"/api/v1/tags/{tag_id}",
        headers=await csrf_headers(client),
    )
    assert archived.status_code == 200
    assert archived.json()["active"] is False
    assert (await client.get("/api/v1/tags")).json()["items"] == []
    assert (await client.get("/api/v1/tags", params={"include_inactive": True})).json()["items"][0][
        "archived_at"
    ]

    restored = await client.post(
        f"/api/v1/tags/{tag_id}/restore",
        headers=await csrf_headers(client),
    )
    assert restored.status_code == 200
    assert restored.json()["active"] is True


async def test_unknown_tags_are_rejected_with_active_catalog(client: AsyncClient) -> None:
    await setup_owner(client)
    created = await client.post(
        "/api/v1/tags",
        headers=await csrf_headers(client),
        json={"name": "work"},
    )
    assert created.status_code == 201

    response = await client.post(
        "/api/v1/tasks",
        headers=await csrf_headers(client),
        json={"title": "Known and unknown", "tags": ["work", "invented"]},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == {
        "code": "unknown_tag",
        "message": "Some tags are not in the active tag catalog.",
        "unknown_tags": ["invented"],
        "allowed_tags": ["work"],
    }
    assert (await client.get("/api/v1/tasks")).json()["items"] == []


async def test_shared_tag_rename_preserves_note_and_task_grouping(client: AsyncClient) -> None:
    await setup_owner(client)
    created = await client.post(
        "/api/v1/tags",
        headers=await csrf_headers(client),
        json={"name": "work"},
    )
    assert created.status_code == 201
    tag_id = created.json()["id"]

    note = await client.post(
        "/api/v1/notes",
        headers=await csrf_headers(client),
        json={"body": "A planning note", "tags": ["work"]},
    )
    assert note.status_code == 201
    task = await client.post(
        "/api/v1/tasks",
        headers=await csrf_headers(client),
        json={"title": "Plan work", "tags": ["work"]},
    )
    assert task.status_code == 201

    renamed = await client.patch(
        f"/api/v1/tags/{tag_id}",
        headers=await csrf_headers(client),
        json={"name": "projects"},
    )
    assert renamed.status_code == 200
    assert (await client.get(f"/api/v1/notes/{note.json()['id']}")).json()["tags"] == ["projects"]
    assert (await client.get(f"/api/v1/tasks/{task.json()['id']}")).json()["tags"] == ["projects"]
    searched = await client.get("/api/v1/notes", params={"search": "projects"})
    assert [item["id"] for item in searched.json()["items"]] == [note.json()["id"]]


async def test_active_tags_cannot_be_permanently_deleted(client: AsyncClient) -> None:
    await setup_owner(client)
    created = await client.post(
        "/api/v1/tags",
        headers=await csrf_headers(client),
        json={"name": "work"},
    )
    assert created.status_code == 201
    tag_id = created.json()["id"]

    without_csrf = await client.delete(f"/api/v1/tags/{tag_id}/permanent")
    assert without_csrf.status_code == 403

    active = await client.delete(
        f"/api/v1/tags/{tag_id}/permanent",
        headers=await csrf_headers(client),
    )
    assert active.status_code == 409
    assert active.json()["detail"]["code"] == "tag_must_be_archived"
    assert (await client.get("/api/v1/tags")).json()["items"][0]["id"] == tag_id

    missing = await client.delete(
        "/api/v1/tags/not-this-owner/permanent",
        headers=await csrf_headers(client),
    )
    assert missing.status_code == 404


async def test_archived_tag_can_be_permanently_deleted_with_all_memberships(
    client: AsyncClient,
    monkeypatch,
) -> None:
    await setup_owner(client)
    created = await client.post(
        "/api/v1/tags",
        headers=await csrf_headers(client),
        json={"name": "work"},
    )
    assert created.status_code == 201
    tag_id = created.json()["id"]

    note = await client.post(
        "/api/v1/notes",
        headers=await csrf_headers(client),
        json={"body": "A planning entry", "tags": ["work"]},
    )
    assert note.status_code == 201
    task = await client.post(
        "/api/v1/tasks",
        headers=await csrf_headers(client),
        json={"title": "Plan work", "tags": ["work"]},
    )
    assert task.status_code == 201

    now = datetime(2027, 1, 1, 9, 0, tzinfo=UTC)
    monkeypatch.setattr("cortex_backend.tasks.service._utc_now", lambda: now)
    series_task = await client.post(
        "/api/v1/tasks",
        headers=await csrf_headers(client),
        json={
            "title": "Daily review",
            "due_at": now.isoformat(),
            "tags": ["work"],
            "recurrence": {"timezone": "UTC", "frequency": "daily", "interval": 1},
        },
    )
    assert series_task.status_code == 201
    series_id = series_task.json()["series_id"]
    assert series_id

    archived = await client.delete(
        f"/api/v1/tags/{tag_id}",
        headers=await csrf_headers(client),
    )
    assert archived.status_code == 200

    deleted = await client.delete(
        f"/api/v1/tags/{tag_id}/permanent",
        headers=await csrf_headers(client),
    )
    assert deleted.status_code == 204
    assert deleted.content == b""
    remaining_tags = (await client.get("/api/v1/tags", params={"include_inactive": True})).json()[
        "items"
    ]
    assert not any(item["id"] == tag_id for item in remaining_tags)
    assert (await client.get(f"/api/v1/notes/{note.json()['id']}")).json()["tags"] == []
    assert (await client.get(f"/api/v1/tasks/{task.json()['id']}")).json()["tags"] == []
    assert (await client.get(f"/api/v1/task-series/{series_id}")).json()["tags"] == []
    searched = await client.get("/api/v1/notes", params={"search": "work"})
    assert not any(item["id"] == note.json()["id"] for item in searched.json()["items"])
