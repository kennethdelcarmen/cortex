"""REST, filesystem, and MCP behavior for the file storage domain."""

import asyncio
import hashlib
import io
import os
import sqlite3
import stat
import subprocess
import sys
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zipfile import ZipFile

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from pypdf import PdfWriter
from sqlalchemy import func, select

from cortex_backend.app import create_app
from cortex_backend.config import Settings
from cortex_backend.files import processing
from cortex_backend.files.models import FileArtifact, FileContextJob
from cortex_backend.files.processing import process_file_context_once
from cortex_backend.storage import InMemoryStorage


def migrate(database_path: Path, monkeypatch, revision: str = "head") -> None:
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
            revision,
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


@pytest.fixture
async def processing_context(tmp_path, monkeypatch):
    """Yield an HTTP client and app state for deterministic worker tests."""

    database_path = tmp_path / "processing-cortex.db"
    file_storage_path = tmp_path / "processing-files"
    migrate(database_path, monkeypatch)
    app = create_app(
        settings=Settings(
            environment="test",
            database_path=database_path,
            file_storage_path=file_storage_path,
            file_processing_enabled=False,
            setup_secret=SecretStr("test-setup-secret"),
        )
    )
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as test_client:
        yield test_client, app
    await app.state.storage.close()


@pytest.fixture
async def automatic_processing_context(tmp_path, monkeypatch):
    """Yield an app that can run the supervised worker through its lifespan."""

    database_path = tmp_path / "automatic-processing-cortex.db"
    file_storage_path = tmp_path / "automatic-processing-files"
    migrate(database_path, monkeypatch)
    app = create_app(
        settings=Settings(
            environment="test",
            database_path=database_path,
            file_storage_path=file_storage_path,
            file_processing_poll_seconds=0.01,
            setup_secret=SecretStr("test-setup-secret"),
        )
    )
    yield app
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
            file_processing_enabled=False,
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


def docx_fixture(text: str) -> bytes:
    """Build the minimal OOXML members used by the fallback extractor."""

    document = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body>"
        "</w:document>"
    )
    output = io.BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr("word/document.xml", document)
    return output.getvalue()


def executable_script(path: Path, body: str) -> Path:
    """Create one deterministic executable used by processing tests."""

    path.write_text(f"#!{sys.executable}\n{body}\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


async def test_files_require_authentication(client: AsyncClient) -> None:
    response = await client.get("/api/v1/files")

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "unauthenticated"


async def test_file_upload_download_immutable_duplicate_and_lifecycle(
    client: AsyncClient,
    tmp_path: Path,
) -> None:
    await setup_owner(client)
    content = b"hello Cortex files"

    created = await upload(client, content, "../../hello.txt")

    assert created.status_code == 201
    body = created.json()
    assert body["name"] == "hello.txt"
    assert body["context_status"] == "pending"
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

    raw_with_inline_query = await client.get(
        f"/api/v1/files/{file_id}/content", params={"inline": "true"}
    )
    assert raw_with_inline_query.status_code == 200
    assert raw_with_inline_query.headers["content-disposition"].startswith("attachment;")
    assert raw_with_inline_query.headers["content-type"].startswith("application/octet-stream")

    renamed = await client.patch(
        f"/api/v1/files/{file_id}",
        headers=await csrf_headers(client),
        json={"name": "renamed.txt"},
    )
    assert renamed.status_code == 405
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


async def test_text_processing_is_shared_by_duplicate_sources(processing_context) -> None:
    client, app = processing_context
    await setup_owner(client)
    content = b"Cortex should remember this source.\r\nSecond line."
    first = await upload(client, content, "first.txt")
    second = await upload(client, content, "copy.txt")
    assert first.status_code == 201
    assert second.status_code == 201

    assert await process_file_context_once(
        app.state.storage,
        app.state.file_storage,
        app.state.settings,
    )

    first_context = await client.get(f"/api/v1/files/{first.json()['id']}/preview")
    second_context = await client.get(f"/api/v1/files/{second.json()['id']}/preview")
    assert first_context.status_code == 200
    assert second_context.status_code == 200
    assert first_context.json()["status"] == "ready"
    assert first_context.json()["text"] == "Cortex should remember this source.\nSecond line."
    assert second_context.json()["status"] == "ready"

    preview = await client.get(f"/api/v1/files/{first.json()['id']}/preview/content")
    assert preview.status_code == 200
    assert preview.text == "Cortex should remember this source.\nSecond line."
    assert preview.headers["content-type"].startswith("text/plain")

    async with app.state.storage.session() as db:
        assert await db.scalar(select(func.count(FileContextJob.id))) == 1
        assert await db.scalar(select(func.count(FileArtifact.id))) == 1


async def test_lifespan_worker_processes_uploaded_text(automatic_processing_context) -> None:
    app = automatic_processing_context
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            await setup_owner(client)
            created = await upload(client, b"processed by the supervised worker", "worker.txt")
            assert created.status_code == 201

            preview = None
            for _ in range(100):
                preview = await client.get(f"/api/v1/files/{created.json()['id']}/preview")
                if preview.json()["status"] == "ready":
                    break
                await asyncio.sleep(0.01)

            assert preview is not None
            assert preview.status_code == 200
            assert preview.json()["status"] == "ready"
            assert preview.json()["text"] == "processed by the supervised worker"
            assert app.state.file_processing_health.ready


async def test_migrated_existing_text_file_is_processed(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "migrated-processing-cortex.db"
    file_storage_path = tmp_path / "migrated-processing-files"
    migrate(database_path, monkeypatch, "0010_files_foundation")

    user_id = "00000000-0000-0000-0000-000000000001"
    content = b"legacy source content"
    source_hash = hashlib.sha256(content).hexdigest()
    storage_key = "0" * 32 + ".blob"
    timestamp = "2027-01-01T00:00:00+00:00"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "INSERT INTO users "
            "(id, email, password_hash, is_active, is_owner, created_at, updated_at, "
            "password_changed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                user_id,
                "owner@example.com",
                "not-used",
                1,
                1,
                timestamp,
                timestamp,
                timestamp,
            ),
        )
        connection.execute(
            "INSERT INTO files "
            "(id, user_id, original_name, storage_key, media_type, size_bytes, sha256, "
            "created_at, updated_at, deleted_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "00000000-0000-0000-0000-000000000010",
                user_id,
                "legacy.txt",
                storage_key,
                "text/plain",
                len(content),
                source_hash,
                timestamp,
                timestamp,
                None,
            ),
        )
        connection.commit()
    file_storage_path.mkdir(parents=True)
    (file_storage_path / storage_key).write_bytes(content)
    migrate(database_path, monkeypatch)

    app = create_app(
        settings=Settings(
            environment="test",
            database_path=database_path,
            file_storage_path=file_storage_path,
            file_processing_enabled=False,
            setup_secret=SecretStr("test-setup-secret"),
        )
    )
    try:
        assert await process_file_context_once(
            app.state.storage,
            app.state.file_storage,
            app.state.settings,
        )
        async with app.state.storage.session() as db:
            job = await db.scalar(select(FileContextJob))
            artifact = await db.scalar(select(FileArtifact))
            assert job is not None
            assert job.status == "ready"
            assert artifact is not None
            assert artifact.artifact_kind == "text"
    finally:
        await app.state.storage.close()


async def test_expired_processing_lease_is_reclaimed(processing_context) -> None:
    client, app = processing_context
    await setup_owner(client)
    created = await upload(client, b"lease recovery", "lease.txt")

    async with app.state.storage.session() as db:
        async with db.begin():
            job = await db.scalar(select(FileContextJob))
            assert job is not None
            job.status = "processing"
            job.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)

    assert await process_file_context_once(
        app.state.storage,
        app.state.file_storage,
        app.state.settings,
    )
    context = await client.get(f"/api/v1/files/{created.json()['id']}/preview")
    assert context.json()["status"] == "ready"


async def test_unsupported_sources_remain_downloadable(processing_context) -> None:
    client, app = processing_context
    await setup_owner(client)
    created = await upload(client, b"not really video", "clip.mp4")

    assert await process_file_context_once(
        app.state.storage,
        app.state.file_storage,
        app.state.settings,
    )

    context = await client.get(f"/api/v1/files/{created.json()['id']}/preview")
    assert context.status_code == 200
    assert context.json()["status"] == "unsupported"
    assert context.json()["text"] is None

    preview = await client.get(f"/api/v1/files/{created.json()['id']}/preview/content")
    assert preview.status_code == 409
    assert preview.json()["detail"]["code"] == "file_context_not_ready"
    raw = await client.get(f"/api/v1/files/{created.json()['id']}/content")
    assert raw.status_code == 200
    assert raw.content == b"not really video"
    assert raw.headers["content-disposition"].startswith("attachment;")


async def test_failed_processing_can_be_retried_without_deleting_source(processing_context) -> None:
    client, app = processing_context
    app.state.settings.file_ocr_command = "cortex-command-that-does-not-exist"
    app.state.settings.file_processing_max_attempts = 1
    await setup_owner(client)
    created = await upload(client, b"not really an image", "scan.png")
    file_id = created.json()["id"]

    assert await process_file_context_once(
        app.state.storage,
        app.state.file_storage,
        app.state.settings,
    )
    failed = await client.get(f"/api/v1/files/{file_id}/preview")
    assert failed.json()["status"] == "failed"
    assert failed.json()["error"] == "ocr_unavailable"
    assert failed.json()["preview_kind"] == "image"

    image_preview = await client.get(f"/api/v1/files/{file_id}/preview/content")
    assert image_preview.status_code == 200
    assert image_preview.content == b"not really an image"
    assert image_preview.headers["content-type"].startswith("image/png")

    retry = await client.post(
        f"/api/v1/files/{file_id}/processing/retry",
        headers=await csrf_headers(client),
    )
    assert retry.status_code == 200
    assert retry.json()["context_status"] == "pending"
    assert (await client.get(f"/api/v1/files/{file_id}/content")).content == b"not really an image"


async def test_docx_retains_context_without_exposing_text_as_preview(processing_context) -> None:
    client, app = processing_context
    app.state.settings.file_converter_command = "cortex-command-that-does-not-exist"
    await setup_owner(client)
    created = await upload(client, docx_fixture("Fallback document text"), "fallback.docx")

    assert await process_file_context_once(
        app.state.storage,
        app.state.file_storage,
        app.state.settings,
    )

    context = await client.get(f"/api/v1/files/{created.json()['id']}/preview")
    assert context.status_code == 200
    assert context.json()["status"] == "ready"
    assert context.json()["preview_kind"] is None
    assert context.json()["text"] == "Fallback document text"

    preview = await client.get(f"/api/v1/files/{created.json()['id']}/preview/content")
    assert preview.status_code == 409
    assert preview.json()["detail"]["code"] == "file_preview_unavailable"

    async with app.state.storage.session() as db:
        artifacts = (
            await db.scalars(
                select(FileArtifact).where(
                    FileArtifact.source_sha256 == created.json()["sha256"],
                )
            )
        ).all()
    assert {artifact.artifact_kind for artifact in artifacts} == {"text"}


async def test_successful_office_conversion_is_served_as_pdf_preview(
    processing_context,
    monkeypatch,
    tmp_path: Path,
) -> None:
    client, app = processing_context
    await setup_owner(client)
    converted_pdf = tmp_path / "converted.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with converted_pdf.open("wb") as handle:
        writer.write(handle)

    async def fake_convert_office_to_pdf(*args, **kwargs) -> Path:
        return converted_pdf

    monkeypatch.setattr(processing, "_convert_office_to_pdf", fake_convert_office_to_pdf)
    created = await upload(client, docx_fixture("Converted document"), "converted.docx")

    assert await process_file_context_once(
        app.state.storage,
        app.state.file_storage,
        app.state.settings,
    )

    context = await client.get(f"/api/v1/files/{created.json()['id']}/preview")
    assert context.status_code == 200
    assert context.json()["status"] == "ready"
    assert context.json()["preview_kind"] == "pdf"

    preview = await client.get(f"/api/v1/files/{created.json()['id']}/preview/content")
    assert preview.status_code == 200
    assert preview.content.startswith(b"%PDF-")
    assert preview.headers["content-type"] == "application/pdf"

    async with app.state.storage.session() as db:
        artifacts = (
            await db.scalars(
                select(FileArtifact).where(
                    FileArtifact.source_sha256 == created.json()["sha256"],
                )
            )
        ).all()
    assert {artifact.artifact_kind for artifact in artifacts} == {"text", "pdf"}


async def test_ocr_command_receives_configured_language(
    processing_context,
    tmp_path: Path,
) -> None:
    client, app = processing_context
    ocr = executable_script(
        tmp_path / "fake-tesseract",
        "import sys\nassert sys.argv[-2:] == ['-l', 'eng+deu']\nprint('recognized text')",
    )
    app.state.settings.file_ocr_command = str(ocr)
    app.state.settings.file_ocr_language = "eng+deu"
    await setup_owner(client)
    created = await upload(client, b"image bytes", "scan.png")

    assert await process_file_context_once(
        app.state.storage,
        app.state.file_storage,
        app.state.settings,
    )
    context = await client.get(f"/api/v1/files/{created.json()['id']}/preview")
    assert context.json()["status"] == "ready"
    assert context.json()["text"] == "recognized text\n"


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


async def test_file_limit_leaves_no_partial_object(
    client: AsyncClient,
    tmp_path: Path,
) -> None:
    await setup_owner(client)
    too_large = await upload(client, b"x" * 1025, "large.bin")

    assert too_large.status_code == 413
    assert too_large.json()["detail"]["code"] == "file_too_large"
    assert not list((tmp_path / "files").glob("*.blob"))
    assert (await client.get("/api/v1/files")).json()["items"] == []

    accepted = await client.post(
        "/api/v1/files",
        headers=await csrf_headers(client),
        files={"file": ("unknown.bin", b"ok", "not a mime")},
    )
    assert accepted.status_code == 201
    assert accepted.json()["context_status"] == "pending"


async def test_raw_content_is_always_an_attachment(client: AsyncClient) -> None:
    await setup_owner(client)
    html = await client.post(
        "/api/v1/files",
        headers=await csrf_headers(client),
        files={"file": ("unsafe.html", b"<script>alert(1)</script>", "text/html")},
    )
    svg = await client.post(
        "/api/v1/files",
        headers=await csrf_headers(client),
        files={"file": ("unsafe.svg", b"<svg></svg>", "image/svg+xml")},
    )

    assert html.status_code == 201
    assert svg.status_code == 201

    html_response = await client.get(f"/api/v1/files/{html.json()['id']}/content")
    svg_response = await client.get(f"/api/v1/files/{svg.json()['id']}/content")

    assert html_response.headers["content-disposition"].startswith("attachment;")
    assert svg_response.headers["content-disposition"].startswith("attachment;")


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

        tools = await client.post(
            "/mcp/",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
                "params": {},
            },
        )
        assert tools.status_code == 200
        assert "get_file_context" in tools.text
        assert "rename_file" not in tools.text

        listed = await client.post(
            "/mcp/",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "list_files", "arguments": {}},
            },
        )
        assert listed.status_code == 200
        assert file_id in listed.text

        context = await client.post(
            "/mcp/",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {"name": "get_file_context", "arguments": {"file_id": file_id}},
            },
        )
        assert context.status_code == 200
        assert '"status":"pending"' in context.text

        deleted = await client.post(
            "/mcp/",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 5,
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
                "id": 6,
                "method": "tools/call",
                "params": {"name": "restore_file", "arguments": {"file_id": file_id}},
            },
        )
        assert restored.status_code == 200
        assert (await client.get(f"/api/v1/files/{file_id}")).status_code == 200
