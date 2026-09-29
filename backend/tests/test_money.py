"""Money API behavior over a migrated temporary SQLite database."""

import json
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


async def test_money_crud_balancing_budgets_and_reversal(client: AsyncClient) -> None:
    await setup_owner(client)
    headers = await csrf_headers(client)

    account = await client.post(
        "/api/v1/money/accounts",
        headers=headers,
        json={
            "name": " Main Checking ",
            "account_type": "checking",
            "institution_name": "Local Bank",
            "last_four": "1234",
            "currency_code": "usd",
            "opening_balance": "100.00",
        },
    )
    assert account.status_code == 201, account.text
    account_body = account.json()
    assert account_body["name"] == "Main Checking"
    assert account_body["balance"] == "100.00"

    category = await client.post(
        "/api/v1/money/categories",
        headers=headers,
        json={"name": " Groceries ", "kind": "expense"},
    )
    assert category.status_code == 201, category.text
    category_id = category.json()["id"]

    payee = await client.post(
        "/api/v1/money/payees",
        headers=headers,
        json={"name": " Market "},
    )
    assert payee.status_code == 201, payee.text
    payee_id = payee.json()["id"]

    transaction = await client.post(
        "/api/v1/money/transactions",
        headers=headers,
        json={
            "transaction_date": "2026-09-27",
            "name": "Weekly groceries",
            "payee_id": payee_id,
            "memo": "Weekly groceries",
            "postings": [
                {
                    "account_id": account_body["id"],
                    "currency_code": "USD",
                    "amount": "-10.00",
                },
                {
                    "category_id": category_id,
                    "currency_code": "USD",
                    "amount": "10.00",
                },
            ],
        },
    )
    assert transaction.status_code == 201, transaction.text
    transaction_body = transaction.json()
    assert transaction_body["name"] == "Weekly groceries"
    assert {posting["amount"] for posting in transaction_body["postings"]} == {
        "-10.00",
        "10.00",
    }

    renamed = await client.patch(
        f"/api/v1/money/transactions/{transaction_body['id']}",
        headers=headers,
        json={"name": "  Saturday groceries  "},
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["name"] == "Saturday groceries"
    transaction_body = renamed.json()

    refreshed_account = await client.get(f"/api/v1/money/accounts/{account_body['id']}")
    assert refreshed_account.status_code == 200
    assert refreshed_account.json()["balance"] == "90.00"

    budget = await client.put(
        f"/api/v1/money/budgets/2026-09/{category_id}/USD",
        headers=headers,
        json={"amount": "25.00"},
    )
    assert budget.status_code == 200, budget.text
    assert budget.json()["spent_amount"] == "10.00"

    account_posting = next(
        posting
        for posting in transaction_body["postings"]
        if posting["account_id"] == account_body["id"]
    )
    cleared = await client.post(
        f"/api/v1/money/transactions/{transaction_body['id']}/postings/{account_posting['id']}/clear",
        headers=headers,
    )
    assert cleared.status_code == 200, cleared.text
    reconciled = await client.post(
        f"/api/v1/money/transactions/{transaction_body['id']}/postings/{account_posting['id']}/reconcile",
        headers=headers,
    )
    assert reconciled.status_code == 200, reconciled.text

    locked = await client.patch(
        f"/api/v1/money/transactions/{transaction_body['id']}",
        headers=headers,
        json={"memo": "Should not edit"},
    )
    assert locked.status_code == 409
    assert locked.json()["detail"]["code"] == "money_transaction_locked"

    reversal = await client.post(
        f"/api/v1/money/transactions/{transaction_body['id']}/reverse",
        headers=headers,
    )
    assert reversal.status_code == 200, reversal.text
    assert reversal.json()["reversal_of_id"] == transaction_body["id"]
    assert reversal.json()["name"] == "Reversal of Saturday groceries"

    final_account = await client.get(f"/api/v1/money/accounts/{account_body['id']}")
    assert final_account.json()["balance"] == "100.00"
    final_budget = await client.get(f"/api/v1/money/budgets/{budget.json()['id']}")
    assert final_budget.json()["spent_amount"] == "0.00"

    deleted_budget = await client.delete(
        f"/api/v1/money/budgets/{budget.json()['id']}",
        headers=headers,
    )
    assert deleted_budget.status_code == 204, deleted_budget.text
    missing_budget = await client.get(f"/api/v1/money/budgets/{budget.json()['id']}")
    assert missing_budget.status_code == 404
    assert missing_budget.json()["detail"]["code"] == "money_budget_not_found"

    listed = await client.get("/api/v1/money/transactions")
    assert [item["id"] for item in listed.json()["items"]] == [reversal.json()["id"]]
    all_transactions = await client.get(
        "/api/v1/money/transactions", params={"include_voided": "true"}
    )
    assert {item["state"] for item in all_transactions.json()["items"]} == {"posted", "voided"}


async def test_money_rejects_unbalanced_currency_and_auth_mutations(client: AsyncClient) -> None:
    await setup_owner(client)
    no_csrf = await client.post(
        "/api/v1/money/accounts",
        json={
            "name": "Checking",
            "account_type": "checking",
            "currency_code": "USD",
        },
    )
    assert no_csrf.status_code == 403

    headers = await csrf_headers(client)
    account = await client.post(
        "/api/v1/money/accounts",
        headers=headers,
        json={
            "name": "Checking",
            "account_type": "checking",
            "currency_code": "USD",
        },
    )
    assert account.status_code == 201
    category = await client.post(
        "/api/v1/money/categories",
        headers=headers,
        json={"name": "Food", "kind": "expense"},
    )
    assert category.status_code == 201

    missing_name = await client.post(
        "/api/v1/money/transactions",
        headers=headers,
        json={
            "transaction_date": "2026-09-27",
            "name": "   ",
            "postings": [],
        },
    )
    assert missing_name.status_code == 422

    long_name = await client.post(
        "/api/v1/money/transactions",
        headers=headers,
        json={
            "transaction_date": "2026-09-27",
            "name": "x" * 201,
            "postings": [],
        },
    )
    assert long_name.status_code == 422

    unbalanced = await client.post(
        "/api/v1/money/transactions",
        headers=headers,
        json={
            "transaction_date": "2026-09-27",
            "name": "Unbalanced transaction",
            "postings": [
                {
                    "account_id": account.json()["id"],
                    "currency_code": "USD",
                    "amount": "-10.00",
                },
                {
                    "category_id": category.json()["id"],
                    "currency_code": "USD",
                    "amount": "9.00",
                },
            ],
        },
    )
    assert unbalanced.status_code == 422
    assert unbalanced.json()["detail"]["code"] == "money_unbalanced_transaction"

    unsupported_currency = await client.post(
        "/api/v1/money/accounts",
        headers=headers,
        json={
            "name": "Crypto",
            "account_type": "other",
            "currency_code": "BTC",
        },
    )
    assert unsupported_currency.status_code == 422


async def test_money_summary_aggregates_currency_and_reversal_state(client: AsyncClient) -> None:
    await setup_owner(client)
    headers = await csrf_headers(client)

    php_account = await client.post(
        "/api/v1/money/accounts",
        headers=headers,
        json={
            "name": "PHP checking",
            "account_type": "checking",
            "currency_code": "PHP",
            "opening_balance": "100.00",
        },
    )
    usd_account = await client.post(
        "/api/v1/money/accounts",
        headers=headers,
        json={
            "name": "USD checking",
            "account_type": "checking",
            "currency_code": "USD",
            "opening_balance": "50.00",
        },
    )
    expense = await client.post(
        "/api/v1/money/categories",
        headers=headers,
        json={"name": "Groceries", "kind": "expense"},
    )
    income = await client.post(
        "/api/v1/money/categories",
        headers=headers,
        json={"name": "Salary", "kind": "income"},
    )
    budget = await client.put(
        f"/api/v1/money/budgets/2026-09/{expense.json()['id']}/PHP",
        headers=headers,
        json={"amount": "20.00"},
    )
    assert budget.status_code == 200

    reversed_transaction = await client.post(
        "/api/v1/money/transactions",
        headers=headers,
        json={
            "transaction_date": "2026-09-10",
            "name": "PHP expense",
            "postings": [
                {
                    "account_id": php_account.json()["id"],
                    "currency_code": "PHP",
                    "amount": "-10.00",
                },
                {
                    "category_id": expense.json()["id"],
                    "currency_code": "PHP",
                    "amount": "10.00",
                },
            ],
        },
    )
    account_posting = next(
        posting
        for posting in reversed_transaction.json()["postings"]
        if posting["account_id"]
    )
    await client.post(
        f"/api/v1/money/transactions/{reversed_transaction.json()['id']}/postings/{account_posting['id']}/clear",
        headers=headers,
    )
    await client.post(
        f"/api/v1/money/transactions/{reversed_transaction.json()['id']}/postings/{account_posting['id']}/reconcile",
        headers=headers,
    )
    reversal = await client.post(
        f"/api/v1/money/transactions/{reversed_transaction.json()['id']}/reverse",
        headers=headers,
    )
    assert reversal.status_code == 200

    income_transaction = await client.post(
        "/api/v1/money/transactions",
        headers=headers,
        json={
            "transaction_date": "2026-09-11",
            "name": "PHP income",
            "postings": [
                {
                    "account_id": php_account.json()["id"],
                    "currency_code": "PHP",
                    "amount": "40.00",
                },
                {
                    "category_id": income.json()["id"],
                    "currency_code": "PHP",
                    "amount": "-40.00",
                },
            ],
        },
    )
    assert income_transaction.status_code == 201

    php_summary = await client.get(
        "/api/v1/money/summary",
        params={"period": "2026-09", "currency_code": "PHP"},
    )
    assert php_summary.status_code == 200, php_summary.text
    assert php_summary.json() == {
        "period": "2026-09",
        "currency_code": "PHP",
        "total_balance": "140.00",
        "income_amount": "40.00",
        "spending_amount": "0.00",
        "budget_amount": "20.00",
        "budget_spent_amount": "0.00",
        "budget_remaining_amount": "20.00",
    }

    usd_summary = await client.get(
        "/api/v1/money/summary",
        params={"period": "2026-09", "currency_code": "USD"},
    )
    assert usd_summary.status_code == 200, usd_summary.text
    assert usd_summary.json()["total_balance"] == "50.00"
    assert usd_summary.json()["income_amount"] == "0.00"
    assert usd_summary.json()["spending_amount"] == "0.00"
    assert usd_account.json()["currency_code"] == "USD"


async def test_money_archive_and_cursor_listing(client: AsyncClient) -> None:
    await setup_owner(client)
    headers = await csrf_headers(client)
    for name in ("Checking", "Savings"):
        response = await client.post(
            "/api/v1/money/accounts",
            headers=headers,
            json={"name": name, "account_type": "checking", "currency_code": "USD"},
        )
        assert response.status_code == 201

    first_page = await client.get("/api/v1/money/accounts", params={"limit": 1})
    assert first_page.status_code == 200
    assert first_page.json()["next_cursor"]
    second_page = await client.get(
        "/api/v1/money/accounts",
        params={"limit": 1, "cursor": first_page.json()["next_cursor"]},
    )
    assert second_page.status_code == 200
    assert len(second_page.json()["items"]) == 1

    account_id = first_page.json()["items"][0]["id"]
    second_account_id = second_page.json()["items"][0]["id"]
    archived = await client.post(
        f"/api/v1/money/accounts/{account_id}/archive",
        headers=headers,
    )
    assert archived.status_code == 200
    archived_second = await client.post(
        f"/api/v1/money/accounts/{second_account_id}/archive",
        headers=headers,
    )
    assert archived_second.status_code == 200
    active = await client.get("/api/v1/money/accounts")
    assert account_id not in {item["id"] for item in active.json()["items"]}
    included = await client.get("/api/v1/money/accounts", params={"include_archived": "true"})
    assert account_id in {item["id"] for item in included.json()["items"]}
    archived_only = await client.get(
        "/api/v1/money/accounts", params={"archived_only": "true", "limit": 1}
    )
    assert archived_only.status_code == 200
    assert archived_only.json()["next_cursor"]
    archived_only_second_page = await client.get(
        "/api/v1/money/accounts",
        params={
            "archived_only": "true",
            "limit": 1,
            "cursor": archived_only.json()["next_cursor"],
        },
    )
    archived_ids = {
        item["id"]
        for item in archived_only.json()["items"] + archived_only_second_page.json()["items"]
    }
    assert archived_ids == {account_id, second_account_id}

    restored = await client.post(
        f"/api/v1/money/accounts/{account_id}/restore",
        headers=headers,
    )
    assert restored.status_code == 200
    restored_second = await client.post(
        f"/api/v1/money/accounts/{second_account_id}/restore",
        headers=headers,
    )
    assert restored_second.status_code == 200
    restored_active = await client.get("/api/v1/money/accounts")
    assert account_id in {item["id"] for item in restored_active.json()["items"]}
    restored_archived = await client.get("/api/v1/money/accounts", params={"archived_only": "true"})
    assert account_id not in {item["id"] for item in restored_archived.json()["items"]}


async def test_money_account_update_preserves_balance(client: AsyncClient) -> None:
    await setup_owner(client)
    headers = await csrf_headers(client)
    account = await client.post(
        "/api/v1/money/accounts",
        headers=headers,
        json={
            "name": "Main checking",
            "account_type": "checking",
            "institution_name": "Local bank",
            "last_four": "1234",
            "currency_code": "PHP",
            "opening_balance": "100.00",
        },
    )
    assert account.status_code == 201, account.text
    account_id = account.json()["id"]

    updated = await client.patch(
        f"/api/v1/money/accounts/{account_id}",
        headers=headers,
        json={"name": "Updated checking", "institution_name": "New bank"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "Updated checking"
    assert updated.json()["institution_name"] == "New bank"
    assert updated.json()["balance"] == "100.00"
    assert updated.json()["currency_code"] == "PHP"
    searched = await client.get(
        "/api/v1/money/accounts", params={"search": "updated CHECKING"}
    )
    assert [item["name"] for item in searched.json()["items"]] == ["Updated checking"]


async def test_money_transaction_name_search_covers_ledger_context_and_cursor_fingerprint(
    client: AsyncClient,
) -> None:
    await setup_owner(client)
    headers = await csrf_headers(client)
    account = await client.post(
        "/api/v1/money/accounts",
        headers=headers,
        json={"name": "Main account", "account_type": "checking", "currency_code": "PHP"},
    )
    category = await client.post(
        "/api/v1/money/categories",
        headers=headers,
        json={"name": "Groceries", "kind": "expense"},
    )
    payee = await client.post(
        "/api/v1/money/payees",
        headers=headers,
        json={"name": "Saturday market"},
    )
    assert account.status_code == category.status_code == payee.status_code == 201

    first = await client.post(
        "/api/v1/money/transactions",
        headers=headers,
        json={
            "transaction_date": "2026-09-20",
            "name": "Grocery run",
            "memo": "Fresh produce",
            "payee_id": payee.json()["id"],
            "postings": [
                {"account_id": account.json()["id"], "currency_code": "PHP", "amount": "-10.00"},
                {"category_id": category.json()["id"], "currency_code": "PHP", "amount": "10.00"},
            ],
        },
    )
    second = await client.post(
        "/api/v1/money/transactions",
        headers=headers,
        json={
            "transaction_date": "2026-09-19",
            "name": "Internet bill",
            "memo": "Monthly service",
            "postings": [
                {"account_id": account.json()["id"], "currency_code": "PHP", "amount": "-20.00"},
                {"category_id": category.json()["id"], "currency_code": "PHP", "amount": "20.00"},
            ],
        },
    )
    assert first.status_code == second.status_code == 201

    async def search(term: str):
        response = await client.get("/api/v1/money/transactions", params={"search": term})
        assert response.status_code == 200, response.text
        return {item["id"] for item in response.json()["items"]}

    first_id = first.json()["id"]
    assert first_id in await search("grocery")
    assert first_id in await search("produce")
    assert first_id in await search("market")
    assert first_id in await search("groceries")
    assert first_id in await search("main account")
    assert second.json()["id"] in await search("internet")

    first_page = await client.get(
        "/api/v1/money/transactions",
        params={"search": "main", "limit": 1},
    )
    assert first_page.status_code == 200
    assert first_page.json()["next_cursor"]
    different_search = await client.get(
        "/api/v1/money/transactions",
        params={"search": "groceries", "limit": 1, "cursor": first_page.json()["next_cursor"]},
    )
    assert different_search.status_code == 400


@asynccontextmanager
async def mcp_client(tmp_path, monkeypatch):
    database_path = tmp_path / "mcp-cortex.db"
    migrate(database_path, monkeypatch)
    app = create_app(
        settings=Settings(
            environment="test",
            database_path=database_path,
            setup_secret=SecretStr(SETUP_SECRET),
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


async def test_mcp_money_tools_share_rest_persistence(tmp_path, monkeypatch) -> None:
    async with mcp_client(tmp_path, monkeypatch) as client:
        await setup_owner(client)
        headers = await initialize_mcp(client)

        created_account = await client.post(
            "/mcp/",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "create_money_account",
                    "arguments": {
                        "payload": {
                            "name": "MCP checking",
                            "account_type": "checking",
                            "currency_code": "USD",
                            "opening_balance": "50.00",
                        }
                    },
                },
            },
        )
        assert created_account.status_code == 200, created_account.text
        assert "MCP checking" in created_account.text

        account_list = await client.get("/api/v1/money/accounts")
        assert [item["name"] for item in account_list.json()["items"]] == ["MCP checking"]
        account_id = account_list.json()["items"][0]["id"]

        mcp_account_list = await client.post(
            "/mcp/",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 21,
                "method": "tools/call",
                "params": {
                    "name": "list_money_accounts",
                    "arguments": {"archived_only": False},
                },
            },
        )
        assert mcp_account_list.status_code == 200, mcp_account_list.text
        mcp_account_list_body = json.loads(mcp_account_list.json()["result"]["content"][0]["text"])
        assert [item["id"] for item in mcp_account_list_body["items"]] == [account_id]

        created_category = await client.post(
            "/mcp/",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "create_money_category",
                    "arguments": {"payload": {"name": "MCP food", "kind": "expense"}},
                },
            },
        )
        assert created_category.status_code == 200, created_category.text
        category_list = await client.get("/api/v1/money/categories")
        category_id = category_list.json()["items"][0]["id"]

        created_transaction = await client.post(
            "/mcp/",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "create_money_transaction",
                    "arguments": {
                        "payload": {
                            "transaction_date": "2026-09-27",
                            "name": "MCP transaction",
                            "postings": [
                                {
                                    "account_id": account_id,
                                    "currency_code": "USD",
                                    "amount": "-5.00",
                                },
                                {
                                    "category_id": category_id,
                                    "currency_code": "USD",
                                    "amount": "5.00",
                                },
                            ],
                        }
                    },
                },
            },
        )
        assert created_transaction.status_code == 200, created_transaction.text
        assert "MCP transaction" in created_transaction.text
        rest_transactions = await client.get("/api/v1/money/transactions")
        assert len(rest_transactions.json()["items"]) == 1
        assert rest_transactions.json()["items"][0]["name"] == "MCP transaction"
        rest_summary = await client.get(
            "/api/v1/money/summary",
            params={"period": "2026-09", "currency_code": "USD"},
        )
        assert rest_summary.status_code == 200, rest_summary.text

        summary = await client.post(
            "/mcp/",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {
                    "name": "get_money_summary",
                    "arguments": {"period": "2026-09", "currency_code": "USD"},
                },
            },
        )
        assert summary.status_code == 200, summary.text
        mcp_summary = json.loads(summary.json()["result"]["content"][0]["text"])
        assert mcp_summary == rest_summary.json()
