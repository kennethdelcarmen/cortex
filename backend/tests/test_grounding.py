"""Grounded question preparation and MCP behavior."""

from __future__ import annotations

import os
import subprocess
import sys
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import select

from cortex_backend.app import create_app
from cortex_backend.auth.models import User
from cortex_backend.chunking.context import assemble_context
from cortex_backend.chunking.service import (
    ChunkSearchRecord,
    ChunkSource,
    replace_source_chunks,
)
from cortex_backend.config import Settings
from cortex_backend.grounding.errors import InvalidQuestionError
from cortex_backend.grounding.service import (
    build_prompt,
    prepare_question,
    validate_context_package,
)
from cortex_backend.memory.models import Note
from cortex_backend.storage import SQLiteStorage


def _chunk(
    chunk_id: str,
    text: str,
    *,
    rank: int = 1,
    source_id: str = "source-1",
) -> ChunkSearchRecord:
    return ChunkSearchRecord(
        id=chunk_id,
        user_id="user-1",
        source_type="note",
        source_id=source_id,
        source_version="version-1",
        source_title="Example source",
        ordinal=rank - 1,
        text=text,
        rank=rank,
        score=1.0 / rank,
        file_ids=[],
        file_names=[],
    )


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


def test_prompt_builder_includes_grounding_rules_and_context() -> None:
    package = assemble_context(
        "What matters?",
        [_chunk("chunk-1", "The important detail is recorded here.")],
    )

    prompt = build_prompt(package)

    assert "What matters?" in prompt
    assert "[1] Example source" in prompt
    assert "The important detail is recorded here." in prompt
    assert "only information supported by the context" in prompt
    assert "Cite every factual claim" in prompt
    assert "<cortex_context>" in prompt


def test_prompt_builder_rejects_context_without_supporting_passages() -> None:
    package = assemble_context("What matters?", [])

    with pytest.raises(ValueError, match="supporting context"):
        build_prompt(package)


def test_context_validator_rejects_inconsistent_citation_labels() -> None:
    package = assemble_context(
        "What matters?",
        [_chunk("chunk-1", "First detail."), _chunk("chunk-2", "Second detail.", rank=2)],
    )
    invalid_passage = replace(package.passages[1], citation="[3]")
    invalid_package = replace(package, passages=(package.passages[0], invalid_passage))

    with pytest.raises(ValueError, match="citations must be sequential"):
        validate_context_package(invalid_package)


def test_context_validator_accepts_assembled_package() -> None:
    package = assemble_context(
        "What matters?",
        [_chunk("chunk-1", "First detail."), _chunk("chunk-2", "Second detail.", rank=2)],
    )

    validate_context_package(package)


@pytest.fixture
async def storage(tmp_path: Path, monkeypatch) -> SQLiteStorage:
    database_path = tmp_path / "grounding.db"
    migrate(database_path, monkeypatch)
    storage = SQLiteStorage(database_path)
    await storage.check_ready()
    now = datetime.now(UTC)
    user_id = "00000000-0000-0000-0000-000000000001"
    note_id = "00000000-0000-0000-0000-000000000002"

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
                    title="Grounding note",
                    body="<p>Alpha detail for the grounded answer.</p>",
                    journal_date=None,
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
                    title="Grounding note",
                    text="Alpha detail for the grounded answer.",
                ),
            )

    yield storage
    await storage.close()


@pytest.mark.asyncio
async def test_prepare_question_returns_prompt_and_citations(storage: SQLiteStorage) -> None:
    package = await prepare_question(
        storage,
        "00000000-0000-0000-0000-000000000001",
        "alpha detail",
    )

    assert package.has_context is True
    assert package.empty_reason is None
    assert package.message is None
    assert package.prompt is not None
    assert package.context_text in package.prompt
    assert [citation.citation for citation in package.citations] == ["[1]"]
    assert package.citations[0].source_name == "Grounding note"


@pytest.mark.asyncio
async def test_prepare_question_returns_safe_package_without_context(
    storage: SQLiteStorage,
) -> None:
    package = await prepare_question(
        storage,
        "00000000-0000-0000-0000-000000000001",
        "What is in the lunar archive?",
    )

    assert package.has_context is False
    assert package.prompt is None
    assert package.context_text == ""
    assert package.citations == ()
    assert package.empty_reason == "no_results"
    assert package.message == "I couldn’t find supporting information for that question."


@pytest.mark.asyncio
async def test_prepare_question_rejects_invalid_questions(storage: SQLiteStorage) -> None:
    with pytest.raises(InvalidQuestionError, match="valid searchable content"):
        await prepare_question(
            storage,
            "00000000-0000-0000-0000-000000000001",
            "  \n\t",
        )


@asynccontextmanager
async def mcp_client(tmp_path: Path, monkeypatch):
    database_path = tmp_path / "mcp-grounding.db"
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


async def initialize_mcp(client: AsyncClient) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {client.cookies.get('cortex_session')}",
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
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


async def _seed_mcp_note(client: AsyncClient) -> None:
    app = client._transport.app
    now = datetime.now(UTC)
    async with app.state.storage.session() as db:
        async with db.begin():
            user_id = (await db.execute(select(User.id))).scalar_one()
            note_id = "00000000-0000-0000-0000-000000000002"
            db.add(
                Note(
                    id=note_id,
                    user_id=user_id,
                    title="MCP grounding note",
                    body="<p>Agent context is stored here.</p>",
                    journal_date=None,
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
                    title="MCP grounding note",
                    text="Agent context is stored here.",
                ),
            )


async def test_mcp_prepare_question_returns_grounded_package(tmp_path, monkeypatch) -> None:
    async with mcp_client(tmp_path, monkeypatch) as client:
        await setup_owner(client)
        await _seed_mcp_note(client)
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
        assert "prepare_question" in tools.text

        prepared = await client.post(
            "/mcp/",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "prepare_question",
                    "arguments": {"question": "agent context"},
                },
            },
        )
        assert prepared.status_code == 200
        assert "MCP grounding note" in prepared.text
        assert '"citation":"[1]"' in prepared.text
        assert "<cortex_context>" in prepared.text


async def test_mcp_prepare_question_returns_safe_no_context_package(
    tmp_path,
    monkeypatch,
) -> None:
    async with mcp_client(tmp_path, monkeypatch) as client:
        await setup_owner(client)
        headers = await initialize_mcp(client)

        prepared = await client.post(
            "/mcp/",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "prepare_question",
                    "arguments": {"question": "What is not recorded?"},
                },
            },
        )
        assert prepared.status_code == 200
        assert '"has_context":false' in prepared.text
        assert '"prompt":null' in prepared.text
        assert "I couldn’t find supporting information for that question." in prepared.text


async def test_mcp_prepare_question_reports_invalid_question(tmp_path, monkeypatch) -> None:
    async with mcp_client(tmp_path, monkeypatch) as client:
        await setup_owner(client)
        headers = await initialize_mcp(client)

        prepared = await client.post(
            "/mcp/",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "prepare_question",
                    "arguments": {"question": "  \n\t"},
                },
            },
        )
        assert prepared.status_code == 200
        assert "invalid_question" in prepared.text
