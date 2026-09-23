"""Authentication behavior tests over a migrated temporary SQLite database."""

import asyncio
import os
import sqlite3
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import update

from cortex_backend.app import create_app
from cortex_backend.auth.models import AuthSession
from cortex_backend.auth.security import utc_now
from cortex_backend.auth.throttling import LoginThrottle
from cortex_backend.config import Settings
from cortex_backend.storage import SQLiteStorage


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


async def csrf_headers(client: AsyncClient) -> dict[str, str]:
    token = client.cookies.get("cortex_csrf")
    assert token is not None
    return {"Origin": "http://testserver", "X-CSRF-Token": token}


async def setup_owner(client: AsyncClient) -> dict[str, object]:
    response = await client.post(
        "/api/v1/auth/setup",
        headers={"X-Setup-Secret": "test-setup-secret"},
        json={
            "email": "Owner@Example.com",
            "password": "correct horse battery staple",
            "use_setup_secret_as_mcp_key": True,
        },
    )
    assert response.status_code == 201
    return response.json()


async def test_setup_creates_owner_session_and_is_one_time(client: AsyncClient) -> None:
    body = await setup_owner(client)

    assert body["email"] == "owner@example.com"
    assert client.cookies.get("cortex_session")
    assert client.cookies.get("cortex_csrf")
    assert (await client.get("/api/v1/auth/me")).status_code == 200

    second = await client.post(
        "/api/v1/auth/setup",
        headers={"X-Setup-Secret": "test-setup-secret"},
        json={
            "email": "other@example.com",
            "password": "correct horse battery staple",
            "use_setup_secret_as_mcp_key": True,
        },
    )
    assert second.status_code == 409
    assert second.json() == {
        "detail": {
            "code": "auth_already_initialized",
            "message": "Owner setup has already been completed.",
        }
    }


async def test_setup_fails_closed_without_or_with_wrong_secret(client: AsyncClient) -> None:
    client._transport.app.state.settings.setup_secret = None
    missing = await client.post(
        "/api/v1/auth/setup",
        json={
            "email": "owner@example.com",
            "password": "correct horse battery staple",
            "use_setup_secret_as_mcp_key": True,
        },
    )
    assert missing.status_code == 503

    client._transport.app.state.settings.setup_secret = SecretStr("test-setup-secret")
    invalid = await client.post(
        "/api/v1/auth/setup",
        headers={"X-Setup-Secret": "wrong"},
        json={
            "email": "owner@example.com",
            "password": "correct horse battery staple",
            "use_setup_secret_as_mcp_key": True,
        },
    )
    assert invalid.status_code == 403


async def test_setup_secret_verification_is_side_effect_free(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/setup/verify",
        headers={"X-Setup-Secret": "test-setup-secret"},
    )

    assert response.status_code == 204
    assert response.content == b""
    assert client.cookies.get("cortex_session") is None
    assert client.cookies.get("cortex_csrf") is None

    created = await setup_owner(client)
    assert created["email"] == "owner@example.com"


async def test_setup_secret_verification_fails_closed(client: AsyncClient) -> None:
    invalid = await client.post(
        "/api/v1/auth/setup/verify",
        headers={"X-Setup-Secret": "wrong"},
    )
    assert invalid.status_code == 403
    assert invalid.json() == {
        "detail": {
            "code": "invalid_setup_secret",
            "message": "The setup secret is invalid.",
        }
    }

    client._transport.app.state.settings.setup_secret = None
    missing = await client.post("/api/v1/auth/setup/verify")
    assert missing.status_code == 503
    assert missing.json() == {
        "detail": {
            "code": "setup_not_configured",
            "message": "Owner setup is not configured.",
        }
    }


async def test_setup_rejects_cross_origin_requests(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/setup",
        headers={
            "Origin": "https://attacker.example",
            "X-Setup-Secret": "test-setup-secret",
        },
        json={
            "email": "owner@example.com",
            "password": "correct horse battery staple",
            "use_setup_secret_as_mcp_key": True,
        },
    )

    assert response.status_code == 403

    verify_response = await client.post(
        "/api/v1/auth/setup/verify",
        headers={
            "Origin": "https://attacker.example",
            "X-Setup-Secret": "test-setup-secret",
        },
    )
    assert verify_response.status_code == 403


async def test_login_has_generic_invalid_credentials_and_supports_casefolded_email(
    client: AsyncClient,
) -> None:
    await setup_owner(client)
    client.cookies.clear()

    invalid = await client.post(
        "/api/v1/auth/login",
        json={"email": "unknown@example.com", "password": "wrong password"},
    )
    assert invalid.status_code == 401
    assert invalid.json() == {
        "detail": {"code": "invalid_credentials", "message": "Invalid email or password."}
    }

    valid = await client.post(
        "/api/v1/auth/login",
        json={"email": "OWNER@EXAMPLE.COM", "password": "correct horse battery staple"},
    )
    assert valid.status_code == 200
    assert valid.json()["email"] == "owner@example.com"


async def test_csrf_logout_and_password_rotation(client: AsyncClient) -> None:
    await setup_owner(client)
    old_session = client.cookies.get("cortex_session")

    rejected = await client.post(
        "/api/v1/auth/password",
        json={
            "current_password": "correct horse battery staple",
            "new_password": "new correct horse battery staple",
        },
    )
    assert rejected.status_code == 403

    changed = await client.post(
        "/api/v1/auth/password",
        headers=await csrf_headers(client),
        json={
            "current_password": "correct horse battery staple",
            "new_password": "new correct horse battery staple",
        },
    )
    assert changed.status_code == 200
    assert client.cookies.get("cortex_session") != old_session

    old_client = AsyncClient(
        transport=client._transport,
        base_url="http://testserver",
        cookies={"cortex_session": old_session},
    )
    try:
        assert (await old_client.get("/api/v1/auth/me")).status_code == 401
    finally:
        await old_client.aclose()

    logged_out = await client.post(
        "/api/v1/auth/logout",
        headers=await csrf_headers(client),
    )
    assert logged_out.status_code == 204
    assert (await client.get("/api/v1/auth/me")).status_code == 401


async def test_expired_session_is_rejected(client: AsyncClient) -> None:
    await setup_owner(client)
    session_token = client.cookies.get("cortex_session")
    assert session_token is not None
    storage: SQLiteStorage = client._transport.app.state.storage
    async with storage.session() as db:
        async with db.begin():
            await db.execute(
                update(AuthSession).values(idle_expires_at=utc_now() - timedelta(seconds=1))
            )

    assert (await client.get("/api/v1/auth/me")).status_code == 401


async def test_concurrent_setup_preserves_single_owner(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "cortex.db"
    migrate(database_path, monkeypatch)
    settings = Settings(
        environment="test",
        database_path=database_path,
        setup_secret=SecretStr("test-setup-secret"),
    )
    app = create_app(settings=settings)
    try:

        async def submit(email: str) -> int:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://testserver",
            ) as test_client:
                response = await test_client.post(
                    "/api/v1/auth/setup",
                    headers={"X-Setup-Secret": "test-setup-secret"},
                    json={
                        "email": email,
                        "password": "correct horse battery staple",
                        "use_setup_secret_as_mcp_key": True,
                    },
                )
                return response.status_code

        statuses = await asyncio.gather(
            submit("one@example.com"),
            submit("two@example.com"),
        )
        assert sorted(statuses) == [201, 409]
        with sqlite3.connect(database_path) as connection:
            assert connection.execute("SELECT COUNT(*) FROM users").fetchone() == (1,)
    finally:
        await app.state.storage.close()


def test_login_throttle_locks_out_and_cleans_up() -> None:
    from datetime import datetime

    throttle = LoginThrottle(max_entries=1, failure_window=timedelta(minutes=15))
    now = datetime(2026, 1, 1)
    throttle.record_failure("owner\x00127.0.0.1", now)
    throttle.record_failure("owner\x00127.0.0.1", now)
    throttle.record_failure("owner\x00127.0.0.1", now)
    throttle.record_failure("owner\x00127.0.0.1", now)
    throttle.record_failure("owner\x00127.0.0.1", now)
    assert throttle.is_blocked("owner\x00127.0.0.1", now)
    assert not throttle.is_blocked("other\x00127.0.0.2", now)
    assert not throttle.is_blocked("owner\x00127.0.0.1", now + timedelta(minutes=16))
