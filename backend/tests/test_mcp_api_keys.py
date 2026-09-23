"""MCP bearer-key lifecycle behavior over the authenticated HTTP transport."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import select

from cortex_backend.app import create_app
from cortex_backend.auth.models import McpApiKey
from cortex_backend.auth.security import hash_token
from cortex_backend.config import Settings
from cortex_backend.logs.models import ActivityLog

SETUP_SECRET = "test-setup-secret-0123456789abcdef"
SEPARATE_KEY = "mcp-key-0123456789-abcdefghijklmnop"
ROTATED_KEY = "mcp-key-rotated-0123456789-abcdefghi"


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
async def app_client(tmp_path, monkeypatch):
    database_path = tmp_path / "cortex.db"
    migrate(database_path, monkeypatch)
    app = create_app(
        settings=Settings(
            environment="test",
            database_path=database_path,
            setup_secret=SecretStr(SETUP_SECRET),
            cors_origins=["http://testserver"],
        )
    )
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield app, client
    await app.state.storage.close()


async def setup_owner(
    client: AsyncClient,
    *,
    separate_key: str | None = None,
    use_setup_secret: bool = False,
) -> None:
    response = await client.post(
        "/api/v1/auth/setup",
        headers={"X-Setup-Secret": SETUP_SECRET},
        json={
            "email": "owner@example.com",
            "password": "correct horse battery staple",
            "mcp_api_key": separate_key,
            "use_setup_secret_as_mcp_key": use_setup_secret,
        },
    )
    assert response.status_code == 201, response.text


async def csrf_headers(client: AsyncClient) -> dict[str, str]:
    token = client.cookies.get("cortex_csrf")
    assert token is not None
    return {"Origin": "http://testserver", "X-CSRF-Token": token}


async def initialize_mcp(client: AsyncClient, token: str) -> int:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    response = await client.post(
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
    return response.status_code


async def test_setup_can_store_setup_secret_as_mcp_key_and_only_hash_it(
    app_client,
) -> None:
    app, client = app_client
    await setup_owner(client, use_setup_secret=True)

    async with app.state.storage.session() as db:
        api_key = await db.scalar(select(McpApiKey))
        events = list((await db.scalars(select(ActivityLog))).all())

    assert api_key is not None
    assert api_key.key_hash == hash_token(SETUP_SECRET)
    assert SETUP_SECRET not in api_key.key_hash
    assert events[0].event_type == "auth.mcp_key_created"
    assert events[0].metadata_json == {"source": "setup_secret"}
    assert SETUP_SECRET not in json.dumps(events[0].metadata_json)

    client.cookies.clear()
    app.state.settings.setup_secret = None
    async with app.state.mcp_app.lifespan(app):
        assert await initialize_mcp(client, SETUP_SECRET) == 200


async def test_setup_requires_exactly_one_credential_source(app_client) -> None:
    _, client = app_client

    missing = await client.post(
        "/api/v1/auth/setup",
        headers={"X-Setup-Secret": SETUP_SECRET},
        json={"email": "owner@example.com", "password": "correct horse battery staple"},
    )
    assert missing.status_code == 422

    both = await client.post(
        "/api/v1/auth/setup",
        headers={"X-Setup-Secret": SETUP_SECRET},
        json={
            "email": "owner@example.com",
            "password": "correct horse battery staple",
            "mcp_api_key": SEPARATE_KEY,
            "use_setup_secret_as_mcp_key": True,
        },
    )
    assert both.status_code == 422

    short = await client.post(
        "/api/v1/auth/setup",
        headers={"X-Setup-Secret": SETUP_SECRET},
        json={
            "email": "owner@example.com",
            "password": "correct horse battery staple",
            "mcp_api_key": "too-short",
        },
    )
    assert short.status_code == 422

    equal_to_setup_secret = await client.post(
        "/api/v1/auth/setup",
        headers={"X-Setup-Secret": SETUP_SECRET},
        json={
            "email": "owner@example.com",
            "password": "correct horse battery staple",
            "mcp_api_key": SETUP_SECRET,
        },
    )
    assert equal_to_setup_secret.status_code == 422


async def test_mcp_key_rotation_preflight_allows_put(app_client) -> None:
    _, client = app_client
    response = await client.options(
        "/api/v1/auth/mcp-key",
        headers={
            "Origin": "http://testserver",
            "Access-Control-Request-Method": "PUT",
            "Access-Control-Request-Headers": "content-type,x-csrf-token",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://testserver"
    assert "PUT" in response.headers["access-control-allow-methods"]


async def test_static_mcp_key_rotates_revokes_and_does_not_authenticate_rest(app_client) -> None:
    app, client = app_client
    await setup_owner(client, separate_key=SEPARATE_KEY)

    status = await client.get("/api/v1/auth/mcp-key")
    assert status.status_code == 200
    assert status.json()["configured"] is True
    assert status.json()["revoked"] is False
    assert SEPARATE_KEY not in status.text

    client.cookies.clear()
    async with app.state.mcp_app.lifespan(app):
        assert await initialize_mcp(client, SEPARATE_KEY) == 200
    rest = await client.get(
        "/api/v1/tasks",
        headers={"Authorization": f"Bearer {SEPARATE_KEY}"},
    )
    assert rest.status_code == 401

    await client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "correct horse battery staple"},
    )
    rotated = await client.put(
        "/api/v1/auth/mcp-key",
        headers=await csrf_headers(client),
        json={"key": ROTATED_KEY},
    )
    assert rotated.status_code == 200
    client.cookies.clear()
    async with app.state.mcp_app.lifespan(app):
        assert await initialize_mcp(client, SEPARATE_KEY) == 401
        assert await initialize_mcp(client, ROTATED_KEY) == 200

    await client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "correct horse battery staple"},
    )
    revoked = await client.delete(
        "/api/v1/auth/mcp-key",
        headers=await csrf_headers(client),
    )
    assert revoked.status_code == 204
    client.cookies.clear()
    async with app.state.mcp_app.lifespan(app):
        assert await initialize_mcp(client, ROTATED_KEY) == 401

    async with app.state.storage.session() as db:
        events = list(
            (
                await db.scalars(
                    select(ActivityLog).order_by(ActivityLog.created_at, ActivityLog.id)
                )
            ).all()
        )
    assert [event.event_type for event in events] == [
        "auth.mcp_key_created",
        "auth.mcp_key_rotated",
        "auth.mcp_key_revoked",
    ]
    assert all(
        SEPARATE_KEY not in json.dumps(event.metadata_json)
        and ROTATED_KEY not in json.dumps(event.metadata_json)
        for event in events
    )


async def test_password_change_does_not_revoke_static_mcp_key(app_client) -> None:
    app, client = app_client
    await setup_owner(client, separate_key=SEPARATE_KEY)
    changed = await client.post(
        "/api/v1/auth/password",
        headers=await csrf_headers(client),
        json={
            "current_password": "correct horse battery staple",
            "new_password": "new correct horse battery staple",
        },
    )
    assert changed.status_code == 200
    client.cookies.clear()
    async with app.state.mcp_app.lifespan(app):
        assert await initialize_mcp(client, SEPARATE_KEY) == 200
