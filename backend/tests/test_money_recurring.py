"""Recurring money transaction behavior and calendar-rule coverage."""

import json
import os
import subprocess
import sys
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr, ValidationError

from cortex_backend.app import create_app
from cortex_backend.config import Settings
from cortex_backend.money.schemas import MoneyRecurrenceRequest
from cortex_backend.money.service import process_due_recurring_transactions
from cortex_backend.recurrence import iter_calendar_occurrences, local_date

SETUP_SECRET = "test-setup-secret"


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
            setup_secret=SecretStr(SETUP_SECRET),
            installment_charging_enabled=False,
            recurring_transaction_posting_enabled=False,
        )
    )
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as test_client:
        yield test_client
    await app.state.storage.close()


async def setup_owner(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/setup",
        headers={"X-Setup-Secret": SETUP_SECRET},
        json={
            "email": "owner@example.com",
            "password": "correct horse battery staple",
            "use_setup_secret_as_mcp_key": True,
        },
    )
    assert response.status_code == 201, response.text


async def csrf_headers(client: AsyncClient) -> dict[str, str]:
    token = client.cookies.get("cortex_csrf")
    assert token is not None
    return {"Origin": "http://testserver", "X-CSRF-Token": token}


@asynccontextmanager
async def mcp_client(tmp_path: Path, monkeypatch):
    database_path = tmp_path / "mcp-cortex.db"
    migrate(database_path, monkeypatch)
    app = create_app(
        settings=Settings(
            environment="test",
            database_path=database_path,
            setup_secret=SecretStr(SETUP_SECRET),
            installment_charging_enabled=False,
            recurring_transaction_posting_enabled=False,
        )
    )
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as test_client:
            yield test_client


async def initialize_mcp(client: AsyncClient) -> dict[str, str]:
    session_token = client.cookies.get("cortex_session")
    assert session_token is not None
    headers = {
        "Authorization": f"Bearer {session_token}",
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
    assert initialized.status_code == 200, initialized.text
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


async def create_resources(client: AsyncClient, headers: dict[str, str]) -> tuple[str, str]:
    account = await client.post(
        "/api/v1/money/accounts",
        headers=headers,
        json={
            "name": "Checking",
            "account_type": "checking",
            "currency_code": "USD",
            "opening_balance": "1000",
        },
    )
    assert account.status_code == 201, account.text
    category = await client.post(
        "/api/v1/money/categories",
        headers=headers,
        json={"name": "Utilities", "kind": "expense"},
    )
    assert category.status_code == 201, category.text
    return account.json()["id"], category.json()["id"]


def posting_payload(account_id: str, category_id: str, amount: str = "10") -> list[dict[str, str]]:
    return [
        {"account_id": account_id, "currency_code": "USD", "amount": f"-{amount}"},
        {"category_id": category_id, "currency_code": "USD", "amount": amount},
    ]


def test_calendar_occurrences_cover_intervals_clamping_and_bounds() -> None:
    monthly = list(iter_calendar_occurrences(date(2026, 1, 31), "monthly", month_day=31, limit=4))
    assert [item.occurrence_date for item in monthly] == [
        date(2026, 1, 31),
        date(2026, 2, 28),
        date(2026, 3, 31),
        date(2026, 4, 30),
    ]

    weekly = list(
        iter_calendar_occurrences(
            date(2026, 1, 5),
            "weekly",
            interval=2,
            weekdays=(0, 2),
            occurrence_count=5,
        )
    )
    assert [item.occurrence_date for item in weekly] == [
        date(2026, 1, 5),
        date(2026, 1, 7),
        date(2026, 1, 19),
        date(2026, 1, 21),
        date(2026, 2, 2),
    ]
    assert [item.sequence_number for item in weekly] == [1, 2, 3, 4, 5]

    yearly = list(
        iter_calendar_occurrences(
            date(2026, 2, 28),
            "yearly",
            interval=2,
            year_month=2,
            year_day=29,
            until_date=date(2031, 2, 28),
        )
    )
    assert [item.occurrence_date for item in yearly] == [
        date(2026, 2, 28),
        date(2028, 2, 29),
        date(2030, 2, 28),
    ]


def test_recurrence_request_rejects_invalid_selectors() -> None:
    with pytest.raises(ValidationError):
        MoneyRecurrenceRequest(timezone="UTC", frequency="weekly")
    with pytest.raises(ValidationError):
        MoneyRecurrenceRequest(
            timezone="UTC",
            frequency="monthly",
            month_day=1,
            weekdays=["monday"],
        )
    with pytest.raises(ValidationError):
        MoneyRecurrenceRequest(
            timezone="UTC",
            frequency="yearly",
            month=1,
            until_date=date(2026, 12, 31),
            occurrence_count=2,
        )


def test_local_date_is_timezone_and_dst_safe() -> None:
    assert local_date(datetime(2026, 3, 8, 4, 30, tzinfo=UTC), "America/New_York") == date(
        2026, 3, 7
    )
    assert local_date(datetime(2026, 3, 8, 5, 30, tzinfo=UTC), "America/New_York") == date(
        2026, 3, 8
    )


@pytest.mark.asyncio
async def test_recurring_catches_up_each_occurrence_and_is_idempotent(client: AsyncClient) -> None:
    await setup_owner(client)
    headers = await csrf_headers(client)
    account_id, category_id = await create_resources(client, headers)
    created = await client.post(
        "/api/v1/money/recurring-transactions",
        headers=headers,
        json={
            "start_date": "2026-09-01",
            "name": "Weekly utilities",
            "recurrence": {
                "timezone": "UTC",
                "frequency": "weekly",
                "weekdays": ["tuesday"],
            },
            "postings": posting_payload(account_id, category_id),
        },
    )
    assert created.status_code == 201, created.text
    schedule_id = created.json()["id"]

    owner_id = (await client.get("/api/v1/auth/me")).json()["id"]
    storage = client._transport.app.state.storage
    before_due = await process_due_recurring_transactions(
        storage, owner_id, datetime(2026, 8, 31, 23, 0, tzinfo=UTC)
    )
    assert before_due.processed_count == 0
    result = await process_due_recurring_transactions(
        storage, owner_id, datetime(2026, 9, 22, 23, 0, tzinfo=UTC)
    )
    assert result.processed_count == 4
    assert result.failed_count == 0

    repeated = await process_due_recurring_transactions(
        storage, owner_id, datetime(2026, 9, 22, 23, 0, tzinfo=UTC)
    )
    assert repeated.processed_count == 0
    schedule = await client.get(f"/api/v1/money/recurring-transactions/{schedule_id}")
    assert schedule.status_code == 200
    body = schedule.json()
    assert body["posted_count"] == 4
    assert [item["due_date"] for item in body["occurrences"]] == [
        "2026-09-01",
        "2026-09-08",
        "2026-09-15",
        "2026-09-22",
        "2026-09-29",
    ]
    assert body["next_occurrence_date"] == "2026-09-29"

    transactions = await client.get("/api/v1/money/transactions")
    assert transactions.status_code == 200
    assert [item["transaction_date"] for item in transactions.json()["items"]] == [
        "2026-09-22",
        "2026-09-15",
        "2026-09-08",
        "2026-09-01",
    ]


@pytest.mark.asyncio
async def test_pause_resume_skips_missed_occurrences_and_end_is_permanent(
    client: AsyncClient,
) -> None:
    await setup_owner(client)
    headers = await csrf_headers(client)
    account_id, category_id = await create_resources(client, headers)
    created = await client.post(
        "/api/v1/money/recurring-transactions",
        headers=headers,
        json={
            "start_date": "2026-01-01",
            "name": "Monthly utilities",
            "recurrence": {
                "timezone": "UTC",
                "frequency": "monthly",
                "month_day": 1,
            },
            "postings": posting_payload(account_id, category_id),
        },
    )
    assert created.status_code == 201, created.text
    schedule_id = created.json()["id"]

    paused = await client.post(
        f"/api/v1/money/recurring-transactions/{schedule_id}/pause", headers=headers
    )
    assert paused.status_code == 200
    assert paused.json()["state"] == "paused"

    resumed = await client.post(
        f"/api/v1/money/recurring-transactions/{schedule_id}/resume", headers=headers
    )
    assert resumed.status_code == 200, resumed.text
    resumed_body = resumed.json()
    assert resumed_body["state"] == "active"
    assert resumed_body["occurrences"][0]["status"] == "skipped"
    assert resumed_body["next_occurrence_date"] >= date.today().isoformat()

    ended = await client.post(
        f"/api/v1/money/recurring-transactions/{schedule_id}/end", headers=headers
    )
    assert ended.status_code == 200, ended.text
    ended_body = ended.json()
    assert ended_body["state"] == "ended"
    assert ended_body["next_occurrence_date"] is None
    assert ended_body["occurrences"][-1]["status"] == "skipped"

    second_end = await client.post(
        f"/api/v1/money/recurring-transactions/{schedule_id}/end", headers=headers
    )
    assert second_end.status_code == 409


@pytest.mark.asyncio
async def test_future_only_edit_and_archived_resource_retry(client: AsyncClient) -> None:
    await setup_owner(client)
    headers = await csrf_headers(client)
    account_id, category_id = await create_resources(client, headers)
    created = await client.post(
        "/api/v1/money/recurring-transactions",
        headers=headers,
        json={
            "start_date": "2026-09-01",
            "name": "Editable utility",
            "recurrence": {
                "timezone": "UTC",
                "frequency": "weekly",
                "weekdays": ["tuesday"],
            },
            "postings": posting_payload(account_id, category_id),
        },
    )
    assert created.status_code == 201, created.text
    schedule_id = created.json()["id"]
    owner_id = (await client.get("/api/v1/auth/me")).json()["id"]
    storage = client._transport.app.state.storage

    first = await process_due_recurring_transactions(
        storage, owner_id, datetime(2026, 9, 1, tzinfo=UTC)
    )
    assert first.processed_count == 1

    updated = await client.patch(
        f"/api/v1/money/recurring-transactions/{schedule_id}",
        headers=headers,
        json={
            "name": "Edited utility",
            "postings": posting_payload(account_id, category_id, "20"),
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "Edited utility"

    archived = await client.post(f"/api/v1/money/categories/{category_id}/archive", headers=headers)
    assert archived.status_code == 200, archived.text
    failed = await process_due_recurring_transactions(
        storage, owner_id, datetime(2026, 9, 8, tzinfo=UTC)
    )
    assert failed.processed_count == 0
    assert failed.failed_count == 1

    still_scheduled = await client.get(f"/api/v1/money/recurring-transactions/{schedule_id}")
    assert still_scheduled.json()["occurrences"][-1]["status"] == "scheduled"
    assert len((await client.get("/api/v1/money/transactions")).json()["items"]) == 1

    restored = await client.post(f"/api/v1/money/categories/{category_id}/restore", headers=headers)
    assert restored.status_code == 200, restored.text
    retried = await process_due_recurring_transactions(
        storage, owner_id, datetime(2026, 9, 8, tzinfo=UTC)
    )
    assert retried.processed_count == 1
    transactions = (await client.get("/api/v1/money/transactions")).json()["items"]
    assert len(transactions) == 2
    assert transactions[0]["name"] == "Edited utility"
    assert {posting["amount"] for posting in transactions[0]["postings"]} == {
        "-20",
        "20",
    }


@pytest.mark.asyncio
async def test_recurring_supports_transfer_and_split_templates(client: AsyncClient) -> None:
    await setup_owner(client)
    headers = await csrf_headers(client)
    source_account_id, category_id = await create_resources(client, headers)
    destination = await client.post(
        "/api/v1/money/accounts",
        headers=headers,
        json={
            "name": "Savings",
            "account_type": "savings",
            "currency_code": "USD",
            "opening_balance": "0",
        },
    )
    assert destination.status_code == 201, destination.text
    schedule = await client.post(
        "/api/v1/money/recurring-transactions",
        headers=headers,
        json={
            "start_date": "2026-09-30",
            "name": "Transfer and split",
            "recurrence": {
                "timezone": "UTC",
                "frequency": "monthly",
                "month_day": 30,
                "occurrence_count": 1,
            },
            "postings": [
                {"account_id": source_account_id, "currency_code": "USD", "amount": "-100"},
                {
                    "account_id": destination.json()["id"],
                    "currency_code": "USD",
                    "amount": "50",
                },
                {"category_id": category_id, "currency_code": "USD", "amount": "50"},
            ],
        },
    )
    assert schedule.status_code == 201, schedule.text
    owner_id = (await client.get("/api/v1/auth/me")).json()["id"]
    result = await process_due_recurring_transactions(
        client._transport.app.state.storage,
        owner_id,
        datetime(2026, 9, 30, 23, 0, tzinfo=UTC),
    )
    assert result.processed_count == 1
    transactions = (await client.get("/api/v1/money/transactions")).json()["items"]
    assert len(transactions) == 1
    assert {posting["amount"] for posting in transactions[0]["postings"]} == {
        "-100",
        "50",
    }
    assert any(
        posting["account_id"] == destination.json()["id"] for posting in transactions[0]["postings"]
    )


@pytest.mark.asyncio
async def test_mcp_recurring_operations_match_rest(tmp_path, monkeypatch) -> None:
    async with mcp_client(tmp_path, monkeypatch) as client:
        await setup_owner(client)
        mcp_headers = await initialize_mcp(client)
        rest_headers = await csrf_headers(client)
        account_id, category_id = await create_resources(client, rest_headers)

        async def call_tool(request_id: int, name: str, arguments: dict[str, object]) -> dict:
            response = await client.post(
                "/mcp/",
                headers=mcp_headers,
                json={
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "method": "tools/call",
                    "params": {"name": name, "arguments": arguments},
                },
            )
            assert response.status_code == 200, response.text
            return json.loads(response.json()["result"]["content"][0]["text"])

        created = await call_tool(
            2,
            "create_money_recurring_transaction",
            {
                "payload": {
                    "start_date": "2026-09-01",
                    "name": "MCP recurring utility",
                    "recurrence": {
                        "timezone": "UTC",
                        "frequency": "weekly",
                        "weekdays": ["tuesday"],
                    },
                    "postings": posting_payload(account_id, category_id),
                }
            },
        )
        rest_schedule = await client.get(f"/api/v1/money/recurring-transactions/{created['id']}")
        assert rest_schedule.status_code == 200
        assert rest_schedule.json()["id"] == created["id"]

        listed = await call_tool(3, "list_money_recurring_transactions", {})
        assert [item["id"] for item in listed["items"]] == [created["id"]]

        processed = await call_tool(4, "process_due_money_recurring_transactions", {})
        assert processed["processed_count"] > 0
        after_process = await client.get(f"/api/v1/money/recurring-transactions/{created['id']}")
        assert after_process.json()["posted_count"] == processed["processed_count"]

        paused = await call_tool(
            5,
            "pause_money_recurring_transaction",
            {"recurring_transaction_id": created["id"]},
        )
        assert paused["state"] == "paused"
        assert (await client.get(f"/api/v1/money/recurring-transactions/{created['id']}")).json()[
            "state"
        ] == "paused"
