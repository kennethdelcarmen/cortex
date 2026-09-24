"""REST, filesystem, and MCP behavior for the file storage domain."""

import hashlib
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
from cortex_backend.storage import InMemoryStorage


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
    file_storage_path = tmp_path / "files"
    migrate(database_path, monkeypatch)
    app = create_app(
        settings=Settings(
            environment="test",
            database_path=database_path,
            file_storage_path=file_storage_path,
            file_max_size_bytes=1024,
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
    file_storage_path = tmp_path / "mcp-files"
    migrate(database_path, monkeypatch)
    app = create_app(
        settings=Settings(
            environment="test",
            database_path=database_path,
            file_storage_path=file_storage_path,
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


async def upload(client: AsyncClient, content: bytes, filename: str = "example.txt"):
    return await client.post(
        "/api/v1/files",
        headers=await csrf_headers(client),
        files={"file": (filename, content, "text/plain")},
    )


async def test_files_require_authentication(client: AsyncClient) -> None:
    response = await client.get("/api/v1/files")

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "unauthenticated"


async def test_file_upload_download_rename_duplicate_and_lifecycle(
    client: AsyncClient,
    tmp_path: Path,
) -> None:
    await setup_owner(client)
    content = b"hello Cortex files"

    created = await upload(client, content, "../../hello.txt")

    assert created.status_code == 201
    body = created.json()
    assert body["name"] == "hello.txt"
    assert body["media_type"] == "text/plain"
    assert body["size_bytes"] == len(content)
    assert body["sha256"] == hashlib.sha256(content).hexdigest()
    file_id = body["id"]

    stored_objects = list((tmp_path / "files").glob("*.blob"))
    assert len(stored_objects) == 1
    assert stored_objects[0].name != "hello.txt"

    downloaded = await client.get(f"/api/v1/files/{file_id}/content")
    assert downloaded.status_code == 200
    assert downloaded.content == content
    assert downloaded.headers["content-disposition"].startswith("attachment;")
    assert downloaded.headers["x-content-type-options"] == "nosniff"

    renamed = await client.patch(
        f"/api/v1/files/{file_id}",
        headers=await csrf_headers(client),
        json={"name": "renamed.txt"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "renamed.txt"
    assert (await client.get(f"/api/v1/files/{file_id}/content")).content == content

    duplicate = await upload(client, content, "copy.txt")
    assert duplicate.status_code == 201
    assert duplicate.json()["id"] != file_id
    assert len(list((tmp_path / "files").glob("*.blob"))) == 2

    deleted = await client.delete(
        f"/api/v1/files/{file_id}",
        headers=await csrf_headers(client),
    )
    assert deleted.status_code == 204
    assert (await client.get(f"/api/v1/files/{file_id}")).status_code == 404
    assert (await client.get(f"/api/v1/files/{file_id}/content")).status_code == 404

    visible = await client.get("/api/v1/files")
    assert [item["id"] for item in visible.json()["items"]] == [duplicate.json()["id"]]
    deleted_list = await client.get("/api/v1/files", params={"include_deleted": True})
    assert {item["id"] for item in deleted_list.json()["items"]} == {
        file_id,
        duplicate.json()["id"],
    }

    restored = await client.post(
        f"/api/v1/files/{file_id}/restore",
        headers=await csrf_headers(client),
    )
    assert restored.status_code == 200
    assert restored.json()["deleted_at"] is None
    assert (await client.get(f"/api/v1/files/{file_id}/content")).content == content


async def test_file_listing_uses_cursor_pagination_and_rejects_changed_filters(
    client: AsyncClient,
) -> None:
    await setup_owner(client)
    first = await upload(client, b"one", "one.txt")
    second = await upload(client, b"two", "two.txt")

    first_page = await client.get("/api/v1/files", params={"limit": 1})
    assert first_page.status_code == 200
    assert first_page.json()["items"][0]["id"] == second.json()["id"]
    cursor = first_page.json()["next_cursor"]
    assert cursor

    second_page = await client.get("/api/v1/files", params={"limit": 1, "cursor": cursor})
    assert second_page.status_code == 200
    assert [item["id"] for item in second_page.json()["items"]] == [first.json()["id"]]

    changed = await client.get(
        "/api/v1/files",
        params={"limit": 1, "cursor": cursor, "include_deleted": True},
    )
    assert changed.status_code == 400
    assert changed.json()["detail"]["code"] == "invalid_file_cursor"


async def test_file_limit_and_mime_fallback_leave_no_partial_object(
    client: AsyncClient,
    tmp_path: Path,
) -> None:
    await setup_owner(client)
    too_large = await upload(client, b"x" * 1025, "large.bin")

    assert too_large.status_code == 413
    assert too_large.json()["detail"]["code"] == "file_too_large"
    assert not list((tmp_path / "files").glob("*.blob"))
    assert (await client.get("/api/v1/files")).json()["items"] == []

    fallback = await client.post(
        "/api/v1/files",
        headers=await csrf_headers(client),
        files={"file": ("unknown.bin", b"ok", "not a mime")},
    )
    assert fallback.status_code == 201
    assert fallback.json()["media_type"] == "application/octet-stream"


async def test_missing_file_content_returns_stable_error(
    client: AsyncClient,
    tmp_path: Path,
) -> None:
    await setup_owner(client)
    created = await upload(client, b"will disappear", "missing.txt")
    object_path = next((tmp_path / "files").glob("*.blob"))
    object_path.unlink()

    response = await client.get(f"/api/v1/files/{created.json()['id']}/content")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "file_content_missing"


async def test_readiness_checks_file_storage() -> None:
    class UnreadyFileStorage:
        async def check_ready(self) -> None:
            raise RuntimeError("file store unavailable")

    app = create_app(storage=InMemoryStorage(), file_storage=UnreadyFileStorage())
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as test_client:
        response = await test_client.get("/readyz")

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "storage_unavailable"


async def test_mcp_file_metadata_tools_share_rest_persistence(tmp_path, monkeypatch) -> None:
    async with mcp_client(tmp_path, monkeypatch) as client:
        await setup_owner(client)
        created = await upload(client, b"agent bytes", "agent.txt")
        file_id = created.json()["id"]
        headers = await initialize_mcp(client)

        listed = await client.post(
            "/mcp/",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "list_files", "arguments": {}},
            },
        )
        assert listed.status_code == 200
        assert file_id in listed.text

        renamed = await client.post(
            "/mcp/",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "rename_file",
                    "arguments": {"file_id": file_id, "payload": {"name": "agent-renamed.txt"}},
                },
            },
        )
        assert renamed.status_code == 200
        assert "agent-renamed.txt" in renamed.text
        assert (await client.get(f"/api/v1/files/{file_id}")).json()["name"] == "agent-renamed.txt"

        deleted = await client.post(
            "/mcp/",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {"name": "delete_file", "arguments": {"file_id": file_id}},
            },
        )
        assert deleted.status_code == 200
        assert (await client.get(f"/api/v1/files/{file_id}")).status_code == 404

        restored = await client.post(
            "/mcp/",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {"name": "restore_file", "arguments": {"file_id": file_id}},
            },
        )
        assert restored.status_code == 200
        assert (await client.get(f"/api/v1/files/{file_id}")).status_code == 200
