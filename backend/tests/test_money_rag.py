"""Money projections in the shared lexical and grounded retrieval pipeline."""

import os
import subprocess
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import pytest
from sqlalchemy import func, select

from cortex_backend.auth.models import User
from cortex_backend.chunking.models import ContentChunk
from cortex_backend.chunking.service import search_chunks
from cortex_backend.config import Settings
from cortex_backend.embeddings.provider import serialize_embedding
from cortex_backend.embeddings.service import process_embeddings_once
from cortex_backend.grounding.service import prepare_question
from cortex_backend.money.models import (
    MoneyAccount,
    MoneyBudget,
    MoneyCategory,
    MoneyPayee,
    MoneyPosting,
    MoneyTransaction,
)
from cortex_backend.money.rag import refresh_money_rag
from cortex_backend.money.rag_backfill import run_backfill
from cortex_backend.money.service import delete_budget
from cortex_backend.storage import SQLiteStorage


def migrate(database_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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


class FakeMoneyEmbeddingProvider:
    model_name = "BAAI/bge-small-en-v1.5"
    dimensions = 384

    async def embed_documents(self, texts: list[str]) -> list[bytes]:
        return [self._embed(text) for text in texts]

    async def embed_query(self, text: str) -> bytes:
        return self._embed(text)

    @staticmethod
    def _embed(text: str) -> bytes:
        values = [0.0] * 384
        values[0] = 1.0 if "groceries" in text.casefold() else 0.0
        values[1] = 1.0 if not values[0] else 0.0
        return serialize_embedding(values, dimensions=384)


async def seed_money(storage: SQLiteStorage, user_id: str) -> tuple[str, str, str, str, str]:
    now = datetime.now(UTC)

    def entity_id(kind: str) -> str:
        return str(uuid5(NAMESPACE_URL, f"money-rag:{user_id}:{kind}"))

    account_id = entity_id("account")
    payee_id = entity_id("payee")
    category_id = entity_id("category")
    budget_id = entity_id("budget")
    transaction_id = entity_id("transaction")
    async with storage.session() as db:
        async with db.begin():
            db.add(
                User(
                    id=user_id,
                    email=f"{user_id}@example.com",
                    password_hash="hash",
                    is_active=True,
                    is_owner=user_id.endswith("001"),
                    created_at=now,
                    updated_at=now,
                    password_changed_at=now,
                )
            )
            db.add(
                MoneyAccount(
                    id=account_id,
                    user_id=user_id,
                    name="Main checking",
                    account_type="checking",
                    institution_name="Local bank",
                    last_four="1234",
                    currency_code="USD",
                    opening_balance="100.00",
                    created_at=now,
                    updated_at=now,
                )
            )
            db.add(
                MoneyPayee(
                    id=payee_id,
                    user_id=user_id,
                    name="Corner Market",
                    created_at=now,
                    updated_at=now,
                )
            )
            db.add(
                MoneyCategory(
                    id=category_id,
                    user_id=user_id,
                    name="Groceries",
                    kind="expense",
                    created_at=now,
                    updated_at=now,
                )
            )
            await db.flush()
            db.add(
                MoneyBudget(
                    id=budget_id,
                    user_id=user_id,
                    category_id=category_id,
                    period="2026-10",
                    currency_code="USD",
                    amount="300.00",
                    created_at=now,
                    updated_at=now,
                )
            )
            db.add(
                MoneyTransaction(
                    id=transaction_id,
                    user_id=user_id,
                    transaction_date=date(2026, 10, 2),
                    name="Weekly groceries",
                    payee_id=payee_id,
                    memo="Fresh food",
                    state="posted",
                    reversal_of_id=None,
                    created_at=now,
                    updated_at=now,
                    voided_at=None,
                    void_reason=None,
                )
            )
            await db.flush()
            db.add_all(
                [
                    MoneyPosting(
                        id=entity_id("posting-account"),
                        user_id=user_id,
                        transaction_id=transaction_id,
                        position=0,
                        label=None,
                        account_id=account_id,
                        category_id=None,
                        currency_code="USD",
                        amount="-25.00",
                        reconciliation_state="uncleared",
                    ),
                    MoneyPosting(
                        id=entity_id("posting-category"),
                        user_id=user_id,
                        transaction_id=transaction_id,
                        position=1,
                        label=None,
                        account_id=None,
                        category_id=category_id,
                        currency_code="USD",
                        amount="25.00",
                        reconciliation_state="uncleared",
                    ),
                ]
            )
            await db.flush()
            await refresh_money_rag(
                db,
                user_id,
                account_ids=[account_id],
                payee_ids=[payee_id],
                category_ids=[category_id],
                budget_ids=[budget_id],
                transaction_ids=[transaction_id],
                now=now,
            )
    return account_id, payee_id, category_id, budget_id, transaction_id


@pytest.mark.asyncio
async def test_money_rag_is_grounded_owner_scoped_and_redacted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "money-rag.db"
    migrate(database_path, monkeypatch)
    storage = SQLiteStorage(database_path, sqlite_vec_enabled=True)
    await storage.check_ready()
    user_id = "00000000-0000-0000-0000-000000000001"
    other_user_id = "00000000-0000-0000-0000-000000000002"

    try:
        account_id, _, _, budget_id, transaction_id = await seed_money(storage, user_id)
        await seed_money(storage, other_user_id)

        account_hits = await search_chunks(
            storage,
            user_id,
            "main checking",
            source_types=["money_account"],
            retrieval_mode="lexical",
        )
        assert [hit.source_id for hit in account_hits] == [account_id]
        assert "1234" not in account_hits[0].text

        provider = FakeMoneyEmbeddingProvider()
        processed = await process_embeddings_once(
            storage,
            provider,
            Settings(database_path=database_path, embedding_batch_size=100),
        )
        assert processed >= 5
        hybrid_hits = await search_chunks(
            storage,
            user_id,
            "grocery budget",
            source_types=["money_transaction"],
            embedding_provider=provider,
            retrieval_mode="hybrid",
        )
        assert [hit.source_id for hit in hybrid_hits] == [transaction_id]
        assert hybrid_hits[0].vector_distance is not None

        package = await prepare_question(storage, user_id, "weekly groceries")
        assert package.has_context
        assert any(
            citation.source_type == "money_transaction" and citation.source_id == transaction_id
            for citation in package.citations
        )

        owner_transaction_hits = await search_chunks(
            storage,
            user_id,
            "weekly groceries",
            source_types=["money_transaction"],
            retrieval_mode="lexical",
        )
        assert owner_transaction_hits
        assert all(hit.user_id == user_id for hit in owner_transaction_hits)
        assert all(hit.source_id == transaction_id for hit in owner_transaction_hits)

        await delete_budget(storage, user_id, budget_id)
        assert (
            await search_chunks(
                storage,
                user_id,
                "groceries 2026-10",
                source_types=["money_budget"],
                retrieval_mode="lexical",
            )
            == []
        )
    finally:
        await storage.close()


@pytest.mark.asyncio
async def test_money_rag_keeps_voided_history_and_backfill_is_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "money-rag-history.db"
    migrate(database_path, monkeypatch)
    storage = SQLiteStorage(database_path)
    await storage.check_ready()
    user_id = "00000000-0000-0000-0000-000000000011"

    try:
        _, _, _, _, transaction_id = await seed_money(storage, user_id)
        async with storage.session() as db:
            async with db.begin():
                transaction = await db.get(MoneyTransaction, transaction_id)
                assert transaction is not None
                transaction.state = "voided"
                transaction.void_reason = "manual"
                transaction.voided_at = datetime.now(UTC)
                await db.flush()
                await refresh_money_rag(db, user_id, transaction_ids=[transaction_id])

        history = await search_chunks(
            storage,
            user_id,
            "voided",
            source_types=["money_transaction"],
            retrieval_mode="lexical",
        )
        assert [hit.source_id for hit in history] == [transaction_id]

        settings = Settings(environment="test", database_path=database_path)
        first = await run_backfill(settings, batch_size=1)
        first_count = await _chunk_count(storage)
        second = await run_backfill(settings, batch_size=1)
        second_count = await _chunk_count(storage)
        assert first == second == 5
        assert first_count == second_count
    finally:
        await storage.close()


async def _chunk_count(storage: SQLiteStorage) -> int:
    async with storage.session() as db:
        return int((await db.scalar(select(func.count()).select_from(ContentChunk))) or 0)
