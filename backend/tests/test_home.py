"""Home dashboard aggregation and profile behavior."""

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


async def csrf_headers(client: AsyncClient) -> dict[str, str]:
    token = client.cookies.get("cortex_csrf")
    assert token is not None
    return {"Origin": "http://testserver", "X-CSRF-Token": token}


async def setup_owner(client: AsyncClient, display_name: str | None = None) -> dict[str, object]:
    response = await client.post(
        "/api/v1/auth/setup",
        headers={"X-Setup-Secret": "test-setup-secret"},
        json={
            "email": "owner@example.com",
            "display_name": display_name,
            "password": "correct horse battery staple",
            "use_setup_secret_as_mcp_key": True,
        },
    )
    assert response.status_code == 201
    return response.json()


async def test_home_summary_requires_authentication(client: AsyncClient) -> None:
    response = await client.get("/api/v1/home/summary", params={"period": "2026-09"})

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "unauthenticated"


async def test_profile_display_name_round_trip_and_null_fallback(client: AsyncClient) -> None:
    created = await setup_owner(client, "  Kenneth   Cortex  ")
    assert created["display_name"] == "Kenneth Cortex"
    logout = await client.post("/api/v1/auth/logout", headers=await csrf_headers(client))
    assert logout.status_code == 204

    logged_in = await client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "correct horse battery staple"},
    )
    assert logged_in.status_code == 200
    assert logged_in.json()["display_name"] == "Kenneth Cortex"

    updated = await client.patch(
        "/api/v1/auth/me",
        headers=await csrf_headers(client),
        json={"display_name": "   "},
    )
    assert updated.status_code == 200
    assert updated.json()["display_name"] is None
    assert (await client.get("/api/v1/auth/me")).json()["display_name"] is None


async def test_home_summary_empty_shape_and_query_validation(client: AsyncClient) -> None:
    await setup_owner(client)

    response = await client.get(
        "/api/v1/home/summary",
        params={"timezone": "Asia/Manila", "period": "2026-09", "currency_code": "PHP"},
    )

    assert response.status_code == 200
    assert response.json()["tasks"] == {
        "counts": {"today": 0, "upcoming": 0, "overdue": 0, "high_priority": 0},
        "items": [],
    }
    assert response.json()["notes"] == {"count": 0, "items": []}
    assert response.json()["money"]["spending_amount"] == "0.00"
    assert response.json()["money"]["movements"] == []
    assert response.json()["activity"]

    invalid_timezone = await client.get(
        "/api/v1/home/summary",
        params={"timezone": "Not/AZone", "period": "2026-09"},
    )
    assert invalid_timezone.status_code == 422
    assert invalid_timezone.json()["detail"]["code"] == "invalid_home_query"


async def test_home_summary_includes_active_records_and_excludes_deleted(
    client: AsyncClient,
) -> None:
    await setup_owner(client)
    now = datetime.now(UTC)
    task_response = await client.post(
        "/api/v1/tasks",
        headers=await csrf_headers(client),
        json={
            "title": "Review the Home dashboard",
            "status": "todo",
            "priority": "high",
            "start_at": now.isoformat(),
            "due_at": (now + timedelta(hours=2)).isoformat(),
            "tags": [],
        },
    )
    assert task_response.status_code == 201
    note_response = await client.post(
        "/api/v1/notes",
        headers=await csrf_headers(client),
        json={
            "title": "A useful note",
            "body": "<p>Keep this preview close.</p>",
            "journal_date": now.date().isoformat(),
            "tags": [],
            "file_ids": [],
        },
    )
    assert note_response.status_code == 201

    summary = await client.get(
        "/api/v1/home/summary",
        params={"timezone": "UTC", "period": now.strftime("%Y-%m")},
    )
    assert summary.status_code == 200
    assert [item["title"] for item in summary.json()["tasks"]["items"]] == [
        "Review the Home dashboard"
    ]
    assert summary.json()["notes"]["count"] == 1
    assert summary.json()["notes"]["items"][0]["preview"] == "Keep this preview close."

    assert (
        await client.delete(
            f"/api/v1/tasks/{task_response.json()['id']}",
            headers=await csrf_headers(client),
        )
    ).status_code == 204
    assert (
        await client.delete(
            f"/api/v1/notes/{note_response.json()['id']}",
            headers=await csrf_headers(client),
        )
    ).status_code == 204

    empty_again = await client.get(
        "/api/v1/home/summary",
        params={"timezone": "UTC", "period": now.strftime("%Y-%m")},
    )
    assert empty_again.status_code == 200
    assert empty_again.json()["tasks"]["items"] == []
    assert empty_again.json()["notes"]["count"] == 0
