"""REST, service, and MCP behavior for the memory note domain."""

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
from cortex_backend.auth.models import User
from cortex_backend.config import Settings
from cortex_backend.memory.schemas import NoteCreateRequest
from cortex_backend.memory.service import create_note as create_note_service
from cortex_backend.memory.service import list_notes
from cortex_backend.storage import SQLiteStorage


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
        json={"email": "owner@example.com", "password": "correct horse battery staple"},
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


async def create_note(client: AsyncClient, payload: dict[str, object]):
    return await client.post(
        "/api/v1/notes",
        headers=await csrf_headers(client),
        json=payload,
    )


async def test_notes_require_authentication(client: AsyncClient) -> None:
    response = await client.get("/api/v1/notes")

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "unauthenticated"


async def test_note_crud_tags_soft_delete_and_restore(client: AsyncClient) -> None:
    await setup_owner(client)
    created = await create_note(
        client,
        {
            "title": "  Morning pages  ",
            "body": "# Start\n\nWrite the next useful thing.",
            "journal_date": "2027-01-15",
            "tags": [" Journal ", "JOURNAL", "Personal"],
        },
    )

    assert created.status_code == 201
    body = created.json()
    assert body["title"] == "Morning pages"
    assert body["body"].startswith("# Start")
    assert body["journal_date"] == "2027-01-15"
    assert body["tags"] == ["journal", "personal"]
    note_id = body["id"]

    fetched = await client.get(f"/api/v1/notes/{note_id}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == note_id

    updated = await client.patch(
        f"/api/v1/notes/{note_id}",
        headers=await csrf_headers(client),
        json={
            "title": None,
            "body": "Updated **Markdown**.",
            "journal_date": None,
            "tags": [],
        },
    )
    assert updated.status_code == 200
    assert updated.json()["title"] is None
    assert updated.json()["journal_date"] is None
    assert updated.json()["tags"] == []

    deleted = await client.delete(
        f"/api/v1/notes/{note_id}",
        headers=await csrf_headers(client),
    )
    assert deleted.status_code == 204
    assert (await client.get(f"/api/v1/notes/{note_id}")).status_code == 404
    assert (await client.get("/api/v1/notes")).json()["items"] == []

    deleted_list = await client.get("/api/v1/notes", params={"include_deleted": True})
    assert [item["id"] for item in deleted_list.json()["items"]] == [note_id]
    assert deleted_list.json()["items"][0]["deleted_at"] is not None

    restored = await client.post(
        f"/api/v1/notes/{note_id}/restore",
        headers=await csrf_headers(client),
    )
    assert restored.status_code == 200
    assert restored.json()["deleted_at"] is None
    assert (await client.get(f"/api/v1/notes/{note_id}")).status_code == 200


async def test_note_listing_filters_search_and_cursor(client: AsyncClient) -> None:
    await setup_owner(client)
    payloads = [
        {
            "title": "Project reflection",
            "body": "The calm work is shipping well.",
            "journal_date": "2027-01-03",
            "tags": ["work", "reflection"],
        },
        {
            "title": "Reading list",
            "body": "Remember the quiet chapter.",
            "journal_date": "2027-01-02",
            "tags": ["personal"],
        },
        {
            "title": "Weekly review",
            "body": "A calm review of the week.",
            "journal_date": "2027-01-01",
            "tags": ["reflection"],
        },
    ]
    created_ids: list[str] = []
    for payload in payloads:
        response = await create_note(client, payload)
        assert response.status_code == 201
        created_ids.append(response.json()["id"])

    search = await client.get("/api/v1/notes", params={"search": "calm work"})
    assert [item["title"] for item in search.json()["items"]] == ["Project reflection"]

    tag_search = await client.get("/api/v1/notes", params={"search": "reflection"})
    assert {item["title"] for item in tag_search.json()["items"]} == {
        "Project reflection",
        "Weekly review",
    }

    filtered = await client.get(
        "/api/v1/notes",
        params=[("tag", "reflection"), ("journal_date_from", "2027-01-02")],
    )
    assert [item["title"] for item in filtered.json()["items"]] == ["Project reflection"]

    first_page = await client.get("/api/v1/notes", params={"limit": 2})
    assert first_page.status_code == 200
    cursor = first_page.json()["next_cursor"]
    assert cursor
    second_page = await client.get(
        "/api/v1/notes",
        params={"limit": 2, "cursor": cursor},
    )
    assert second_page.status_code == 200
    assert {item["id"] for item in first_page.json()["items"] + second_page.json()["items"]} == set(
        created_ids
    )

    changed_filter = await client.get(
        "/api/v1/notes",
        params={"limit": 2, "cursor": cursor, "search": "calm"},
    )
    assert changed_filter.status_code == 400
    assert changed_filter.json()["detail"]["code"] == "invalid_note_cursor"


async def test_note_mutations_require_csrf_proof(client: AsyncClient) -> None:
    await setup_owner(client)
    response = await client.post(
        "/api/v1/notes",
        headers={"Origin": "http://testserver"},
        json={"body": "No CSRF."},
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "csrf_validation_failed"


async def test_note_service_is_owner_scoped(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "service-cortex.db"
    migrate(database_path, monkeypatch)
    storage = SQLiteStorage(database_path)
    await storage.check_ready()
    now = datetime.now(UTC)
    async with storage.session() as session:
        async with session.begin():
            session.add_all(
                [
                    User(
                        id="00000000-0000-0000-0000-000000000001",
                        email="owner@example.com",
                        password_hash="not-used",
                        is_active=True,
                        is_owner=True,
                        created_at=now,
                        updated_at=now,
                        password_changed_at=now,
                    ),
                    User(
                        id="00000000-0000-0000-0000-000000000002",
                        email="other@example.com",
                        password_hash="not-used",
                        is_active=True,
                        is_owner=False,
                        created_at=now,
                        updated_at=now,
                        password_changed_at=now,
                    ),
                ]
            )

    record = await create_note_service(
        storage,
        "00000000-0000-0000-0000-000000000001",
        NoteCreateRequest(body="Private owner note"),
    )
    other_page = await list_notes(storage, "00000000-0000-0000-0000-000000000002")
    assert other_page.items == []
    assert record.user_id == "00000000-0000-0000-0000-000000000001"
    await storage.close()


async def test_mcp_note_tools_share_rest_persistence(tmp_path, monkeypatch) -> None:
    async with mcp_client(tmp_path, monkeypatch) as client:
        await setup_owner(client)
        headers = await initialize_mcp(client)

        created = await client.post(
            "/mcp/",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "create_note",
                    "arguments": {
                        "payload": {
                            "title": "MCP note",
                            "body": "Stored through the agent boundary.",
                            "tags": ["agent"],
                        }
                    },
                },
            },
        )
        assert created.status_code == 200
        assert "MCP note" in created.text

        rest_list = await client.get("/api/v1/notes", params={"search": "agent"})
        assert [item["title"] for item in rest_list.json()["items"]] == ["MCP note"]
        note_id = rest_list.json()["items"][0]["id"]

        updated = await client.post(
            "/mcp/",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "update_note",
                    "arguments": {
                        "note_id": note_id,
                        "payload": {"body": "Updated through MCP."},
                    },
                },
            },
        )
        assert updated.status_code == 200
        assert "Updated through MCP." in updated.text


async def test_mcp_note_query_errors_are_stable(tmp_path, monkeypatch) -> None:
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
                    "name": "list_notes",
                    "arguments": {"cursor": "not-a-cursor"},
                },
            },
        )

        assert invalid_cursor.status_code == 200
        assert "invalid_note_cursor" in invalid_cursor.text
