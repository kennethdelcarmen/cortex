"""REST and MCP behavior for the activity-log transport adapters."""

import os
import subprocess
import sys
from contextlib import asynccontextmanager
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


async def csrf_headers(client: AsyncClient) -> dict[str, str]:
    token = client.cookies.get("cortex_csrf")
    assert token is not None
    return {"Origin": "http://testserver", "X-CSRF-Token": token}


async def mcp_headers(client: AsyncClient) -> dict[str, str]:
    session_token = client.cookies.get("cortex_session")
    assert session_token is not None
    return {
        "Authorization": f"Bearer {session_token}",
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


async def test_activity_log_list_requires_authentication(client: AsyncClient) -> None:
    response = await client.get("/api/v1/activity-logs")

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "unauthenticated"


async def test_activity_log_append_requires_csrf_proof(client: AsyncClient) -> None:
    await setup_owner(client)

    response = await client.post(
        "/api/v1/activity-logs",
        headers={"Origin": "http://testserver"},
        json={"event_type": "task.created"},
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "csrf_validation_failed"


async def test_rest_activity_logs_append_filters_and_cursor_pagination(
    client: AsyncClient,
) -> None:
    await setup_owner(client)
    records = [
        {
            "event_type": "task.created",
            "entity_type": "task",
            "entity_id": "task-1",
            "metadata": {"source": "rest"},
        },
        {
            "event_type": "task.updated",
            "entity_type": "task",
            "entity_id": "task-1",
            "metadata": {"status": "done"},
        },
        {
            "event_type": "note.created",
            "entity_type": "note",
            "entity_id": "note-1",
        },
    ]
    created_bodies = []
    for payload in records:
        response = await client.post(
            "/api/v1/activity-logs",
            headers=await csrf_headers(client),
            json=payload,
        )
        assert response.status_code == 201
        created_bodies.append(response.json())

    assert created_bodies[0]["user_id"] == created_bodies[1]["user_id"]
    assert created_bodies[0]["metadata"] == {"source": "rest"}

    first_page = await client.get("/api/v1/activity-logs", params={"limit": 2})
    assert first_page.status_code == 200
    first_body = first_page.json()
    assert len(first_body["items"]) == 2
    assert first_body["next_cursor"]

    second_page = await client.get(
        "/api/v1/activity-logs",
        params={"limit": 2, "cursor": first_body["next_cursor"]},
    )
    assert second_page.status_code == 200
    assert len(second_page.json()["items"]) == 2
    assert second_page.json()["next_cursor"] is None

    filtered = await client.get(
        "/api/v1/activity-logs",
        params={"event_type": "task.created", "entity_id": "task-1"},
    )
    assert [item["id"] for item in filtered.json()["items"]] == [created_bodies[0]["id"]]


async def test_rest_activity_log_query_errors_are_stable(client: AsyncClient) -> None:
    await setup_owner(client)

    invalid_cursor = await client.get(
        "/api/v1/activity-logs",
        params={"cursor": "not-a-cursor"},
    )
    assert invalid_cursor.status_code == 400
    assert invalid_cursor.json()["detail"]["code"] == "invalid_activity_log_cursor"

    invalid_limit = await client.get("/api/v1/activity-logs", params={"limit": 101})
    assert invalid_limit.status_code == 400
    assert invalid_limit.json()["detail"]["code"] == "invalid_activity_log_query"


async def test_mcp_activity_log_tools_share_rest_persistence(tmp_path, monkeypatch) -> None:
    async with mcp_client(tmp_path, monkeypatch) as client:
        await setup_owner(client)
        headers = await initialize_mcp(client)

        appended = await client.post(
            "/mcp/",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "append_activity_log",
                    "arguments": {
                        "payload": {
                            "event_type": "task.created",
                            "entity_type": "task",
                            "entity_id": "task-mcp",
                            "metadata": {"source": "mcp"},
                        }
                    },
                },
            },
        )
        assert appended.status_code == 200
        assert "task-mcp" in appended.text

        listed = await client.post(
            "/mcp/",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "list_activity_logs",
                    "arguments": {"event_type": "task.created"},
                },
            },
        )
        assert listed.status_code == 200
        assert "task-mcp" in listed.text

        rest_list = await client.get(
            "/api/v1/activity-logs",
            params={"event_type": "task.created"},
        )
        assert [item["entity_id"] for item in rest_list.json()["items"]] == ["task-mcp"]


async def test_mcp_activity_log_query_errors_are_stable(tmp_path, monkeypatch) -> None:
    async with mcp_client(tmp_path, monkeypatch) as client:
        await setup_owner(client)
        headers = await initialize_mcp(client)

        invalid_cursor = await client.post(
            "/mcp/",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "list_activity_logs",
                    "arguments": {"cursor": "not-a-cursor"},
                },
            },
        )

        assert invalid_cursor.status_code == 200
        assert "invalid_activity_log_cursor" in invalid_cursor.text
