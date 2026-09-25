"""REST and MCP behavior for the cross-domain recovery service."""

import hashlib
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import select, text

from cortex_backend.app import create_app
from cortex_backend.config import Settings
from cortex_backend.files.models import FILE_CONTEXT_VERSION, File, FileArtifact, FileContextJob


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
    settings = Settings(
        environment="test",
        database_path=database_path,
        file_storage_path=file_storage_path,
        file_processing_enabled=False,
        setup_secret=SecretStr("test-setup-secret"),
    )
    app = create_app(settings=settings)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as test_client:
        yield test_client, app
    await app.state.storage.close()


async def csrf_headers(client: AsyncClient) -> dict[str, str]:
    token = client.cookies.get("cortex_csrf")
    assert token is not None
    return {"Origin": "http://testserver", "X-CSRF-Token": token}


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


async def create_task(client: AsyncClient, title: str) -> str:
    response = await client.post(
        "/api/v1/tasks",
        headers=await csrf_headers(client),
        json={"title": title},
    )
    assert response.status_code == 201
    return response.json()["id"]


async def create_note(client: AsyncClient, title: str) -> str:
    response = await client.post(
        "/api/v1/notes",
        headers=await csrf_headers(client),
        json={"title": title, "body": "Recovery body"},
    )
    assert response.status_code == 201
    return response.json()["id"]


async def create_tag(client: AsyncClient, name: str) -> str:
    response = await client.post(
        "/api/v1/tags",
        headers=await csrf_headers(client),
        json={"name": name},
    )
    assert response.status_code == 201
    return response.json()["id"]


async def upload_file(client: AsyncClient, content: bytes = b"recovery file") -> str:
    response = await client.post(
        "/api/v1/files",
        headers=await csrf_headers(client),
        files={"file": ("recovery.txt", content, "text/plain")},
    )
    assert response.status_code == 201
    return response.json()["id"]


async def test_recovery_requires_auth_csrf_and_supports_cursor_pagination(client) -> None:
    test_client, _ = client
    unauthenticated = await test_client.get("/api/v1/recovery")
    assert unauthenticated.status_code == 401

    await setup_owner(test_client)
    note_ids = [await create_note(test_client, f"Deleted note {index}") for index in range(3)]
    headers = await csrf_headers(test_client)
    for note_id in note_ids:
        deleted = await test_client.delete(f"/api/v1/notes/{note_id}", headers=headers)
        assert deleted.status_code == 204

    first_page = await test_client.get("/api/v1/recovery", params={"limit": 2})
    assert first_page.status_code == 200
    first_items = first_page.json()["items"]
    assert len(first_items) == 2
    assert first_page.json()["next_cursor"]

    second_page = await test_client.get(
        "/api/v1/recovery",
        params={"limit": 2, "cursor": first_page.json()["next_cursor"]},
    )
    assert second_page.status_code == 200
    second_items = second_page.json()["items"]
    assert len(second_items) == 1
    assert {item["id"] for item in first_items}.isdisjoint({item["id"] for item in second_items})
    assert second_page.json()["next_cursor"] is None

    csrf_rejected = await test_client.post(
        "/api/v1/recovery/restore",
        json={"items": [{"type": "note", "id": note_ids[0]}]},
    )
    assert csrf_rejected.status_code == 403


async def test_recovery_feed_restores_all_supported_types(client) -> None:
    test_client, _ = client
    await setup_owner(test_client)
    task_id = await create_task(test_client, "Deleted task")
    note_id = await create_note(test_client, "Deleted note")
    file_id = await upload_file(test_client)
    tag_id = await create_tag(test_client, "archived")
    headers = await csrf_headers(test_client)

    for path in (
        f"/api/v1/tasks/{task_id}",
        f"/api/v1/notes/{note_id}",
        f"/api/v1/files/{file_id}",
    ):
        response = await test_client.delete(path, headers=headers)
        assert response.status_code == 204
    archived = await test_client.delete(f"/api/v1/tags/{tag_id}", headers=headers)
    assert archived.status_code == 200

    feed = await test_client.get("/api/v1/recovery")
    assert feed.status_code == 200
    items = feed.json()["items"]
    assert {(item["type"], item["id"]) for item in items} == {
        ("task", task_id),
        ("note", note_id),
        ("file", file_id),
        ("tag", tag_id),
    }
    assert all(
        datetime.fromisoformat(left["removed_at"].replace("Z", "+00:00"))
        >= datetime.fromisoformat(right["removed_at"].replace("Z", "+00:00"))
        for left, right in zip(items, items[1:], strict=False)
    )

    restored = await test_client.post(
        "/api/v1/recovery/restore",
        headers=headers,
        json={"items": [{"type": item["type"], "id": item["id"]} for item in items]},
    )
    assert restored.status_code == 200
    assert {result["status"] for result in restored.json()["results"]} == {"restored"}
    assert (await test_client.get("/api/v1/recovery")).json() == {
        "items": [],
        "next_cursor": None,
    }
    assert (await test_client.get(f"/api/v1/tasks/{task_id}")).status_code == 200
    assert (await test_client.get(f"/api/v1/notes/{note_id}")).status_code == 200
    assert (await test_client.get(f"/api/v1/files/{file_id}")).status_code == 200
    assert any(
        tag["id"] == tag_id for tag in (await test_client.get("/api/v1/tags")).json()["items"]
    )


async def test_recovery_purge_is_independent_and_removes_note_search_entry(client) -> None:
    test_client, app = client
    await setup_owner(test_client)
    deleted_note = await create_note(test_client, "Purge note")
    active_task = await create_task(test_client, "Still active")
    headers = await csrf_headers(test_client)
    deleted = await test_client.delete(f"/api/v1/notes/{deleted_note}", headers=headers)
    assert deleted.status_code == 204

    purged = await test_client.post(
        "/api/v1/recovery/permanent-delete",
        headers=headers,
        json={
            "items": [
                {"type": "note", "id": deleted_note},
                {"type": "task", "id": active_task},
                {"type": "note", "id": deleted_note},
            ]
        },
    )
    assert purged.status_code == 200
    results = purged.json()["results"]
    assert [result["status"] for result in results] == [
        "permanently_deleted",
        "failed",
        "permanently_deleted",
    ]
    assert results[1]["error"]["code"] == "task_must_be_deleted"

    assert (await test_client.get(f"/api/v1/notes/{deleted_note}")).status_code == 404
    async with app.state.storage.session() as db:
        assert (
            await db.scalar(
                text("SELECT COUNT(*) FROM notes_fts WHERE note_id = :note_id"),
                {"note_id": deleted_note},
            )
            == 0
        )


async def test_recovery_purge_removes_task_occurrence_and_tag_memberships(client) -> None:
    test_client, _ = client
    await setup_owner(test_client)
    tag_id = await create_tag(test_client, "purge-me")
    task_response = await test_client.post(
        "/api/v1/tasks",
        headers=await csrf_headers(test_client),
        json={"title": "Recurring recovery task", "tags": ["purge-me"]},
    )
    assert task_response.status_code == 201
    task_id = task_response.json()["id"]
    headers = await csrf_headers(test_client)
    assert (
        await test_client.delete(f"/api/v1/tasks/{task_id}", headers=headers)
    ).status_code == 204
    assert (await test_client.delete(f"/api/v1/tags/{tag_id}", headers=headers)).status_code == 200

    purged = await test_client.post(
        "/api/v1/recovery/permanent-delete",
        headers=headers,
        json={
            "items": [
                {"type": "task", "id": task_id},
                {"type": "tag", "id": tag_id},
            ]
        },
    )
    assert [result["status"] for result in purged.json()["results"]] == [
        "permanently_deleted",
        "permanently_deleted",
    ]
    assert (await test_client.get(f"/api/v1/tasks/{task_id}")).status_code == 404
    tags = (await test_client.get("/api/v1/tags", params={"include_inactive": True})).json()[
        "items"
    ]
    assert not any(tag["id"] == tag_id for tag in tags)


async def test_file_purge_preserves_shared_artifacts_until_last_reference(client) -> None:
    test_client, app = client
    await setup_owner(test_client)
    content = b"shared source bytes"
    first_id = await upload_file(test_client, content)
    second_id = await upload_file(test_client, content)
    headers = await csrf_headers(test_client)
    await test_client.delete(f"/api/v1/files/{first_id}", headers=headers)
    await test_client.delete(f"/api/v1/files/{second_id}", headers=headers)

    digest = hashlib.sha256(content).hexdigest()
    artifact_key = f"artifacts/{digest}/text-{FILE_CONTEXT_VERSION}.artifact"
    (app.state.file_storage.root / artifact_key).parent.mkdir(parents=True, exist_ok=True)
    (app.state.file_storage.root / artifact_key).write_bytes(b"derived")
    now = datetime.now(UTC)
    owner_id = (await test_client.get("/api/v1/auth/me")).json()["id"]
    async with app.state.storage.session() as db:
        async with db.begin():
            job = await db.scalar(
                select(FileContextJob).where(
                    FileContextJob.user_id == owner_id,
                    FileContextJob.source_sha256 == digest,
                )
            )
            assert job is not None
            db.add(
                FileArtifact(
                    id="00000000-0000-0000-0000-000000000901",
                    user_id=job.user_id,
                    source_sha256=digest,
                    artifact_kind="text",
                    storage_key=artifact_key,
                    size_bytes=7,
                    sha256=hashlib.sha256(b"derived").hexdigest(),
                    extractor_version=FILE_CONTEXT_VERSION,
                    created_at=now,
                )
            )
            files = list(
                (await db.scalars(select(File).where(File.id.in_([first_id, second_id])))).all()
            )
            first_key = next(file.storage_key for file in files if file.id == first_id)
            second_key = next(file.storage_key for file in files if file.id == second_id)

    first_purge = await test_client.post(
        "/api/v1/recovery/permanent-delete",
        headers=headers,
        json={"items": [{"type": "file", "id": first_id}]},
    )
    assert first_purge.json()["results"][0]["status"] == "permanently_deleted"
    assert not (app.state.file_storage.root / first_key).exists()
    assert (app.state.file_storage.root / second_key).exists()
    assert (app.state.file_storage.root / artifact_key).exists()

    second_purge = await test_client.post(
        "/api/v1/recovery/permanent-delete",
        headers=headers,
        json={"items": [{"type": "file", "id": second_id}]},
    )
    assert second_purge.json()["results"][0]["status"] == "permanently_deleted"
    assert not (app.state.file_storage.root / second_key).exists()
    assert not (app.state.file_storage.root / artifact_key).exists()


async def test_recovery_mcp_tools_share_rest_persistence(client) -> None:
    test_client, app = client
    await setup_owner(test_client)
    note_id = await create_note(test_client, "MCP recovery")
    deleted = await test_client.delete(
        f"/api/v1/notes/{note_id}",
        headers=await csrf_headers(test_client),
    )
    assert deleted.status_code == 204

    session_token = test_client.cookies.get("cortex_session")
    assert session_token is not None
    headers = {
        "Authorization": f"Bearer {session_token}",
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    async with app.router.lifespan_context(app):
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

        listed = await test_client.post(
            "/mcp/",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "list_recovery_items", "arguments": {}},
            },
        )
        assert listed.status_code == 200
        assert note_id in listed.text

        restored = await test_client.post(
            "/mcp/",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "restore_recovery_items",
                    "arguments": {"payload": {"items": [{"type": "note", "id": note_id}]}},
                },
            },
        )
        assert restored.status_code == 200
        assert "restored" in restored.text
