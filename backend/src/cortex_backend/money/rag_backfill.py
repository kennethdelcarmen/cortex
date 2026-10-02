"""Resumable backfill for existing money projections in the shared RAG index."""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func, or_, select

from ..config import Settings
from ..storage import SQLiteStorage
from .models import (
    MoneyAccount,
    MoneyBudget,
    MoneyCategory,
    MoneyInstallmentPlan,
    MoneyPayee,
    MoneyRecurringTransaction,
    MoneyTransaction,
)
from .rag import MoneyRagSourceType, refresh_money_source


@dataclass(frozen=True)
class MoneyRagBackfillProgress:
    source_type: MoneyRagSourceType
    processed: int
    total: int


ProgressCallback = Callable[[MoneyRagBackfillProgress], None]

_FAMILIES = (
    ("money_account", MoneyAccount),
    ("money_payee", MoneyPayee),
    ("money_category", MoneyCategory),
    ("money_budget", MoneyBudget),
    ("money_transaction", MoneyTransaction),
    ("money_recurring", MoneyRecurringTransaction),
    ("money_installment", MoneyInstallmentPlan),
)


async def _family_total(storage: SQLiteStorage, model: type[object]) -> int:
    async with storage.session() as db:
        return int((await db.scalar(select(func.count()).select_from(model))) or 0)


async def _backfill_family(
    storage: SQLiteStorage,
    source_type: MoneyRagSourceType,
    model: type[object],
    batch_size: int,
    callback: ProgressCallback | None,
    total: int,
) -> int:
    last_user_id = ""
    last_id = ""
    processed = 0
    while True:
        async with storage.session() as db:
            async with db.begin():
                user_column = model.user_id  # type: ignore[attr-defined]
                id_column = model.id  # type: ignore[attr-defined]
                rows = list(
                    (
                        await db.execute(
                            select(user_column, id_column)
                            .where(
                                or_(
                                    user_column > last_user_id,
                                    (user_column == last_user_id) & (id_column > last_id),
                                )
                            )
                            .order_by(user_column.asc(), id_column.asc())
                            .limit(batch_size)
                        )
                    ).all()
                )
                if not rows:
                    break
                for owner_id, source_id in rows:
                    await refresh_money_source(
                        db,
                        str(owner_id),
                        source_type,
                        str(source_id),
                        skip_if_current=True,
                    )
                last_user_id = str(rows[-1][0])
                last_id = str(rows[-1][1])
                batch_count = len(rows)
        processed += batch_count
        if callback is not None:
            callback(MoneyRagBackfillProgress(source_type, processed, total))
    return processed


async def run_backfill(
    settings: Settings,
    batch_size: int,
    *,
    on_progress: ProgressCallback | None = None,
) -> int:
    """Rebuild money projections in committed, idempotent batches."""

    if batch_size < 1 or batch_size > 1_000:
        raise ValueError("batch size must be between 1 and 1000")
    storage = SQLiteStorage(settings.database_path)
    try:
        await storage.check_ready()
        processed = 0
        for source_type, model in _FAMILIES:
            processed += await _backfill_family(
                storage,
                source_type,  # type: ignore[arg-type]
                model,
                batch_size,
                on_progress,
                await _family_total(storage, model),
            )
        return processed
    finally:
        await storage.close()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Backfill Cortex money RAG projections.")
    parser.add_argument("--database-path", type=Path)
    parser.add_argument("--batch-size", type=int, default=100)
    return parser


def _print_progress(progress: MoneyRagBackfillProgress) -> None:
    percentage = 100.0 if progress.total == 0 else progress.processed / progress.total * 100
    print(
        f"money RAG {progress.source_type} "
        f"{progress.processed}/{progress.total} ({percentage:.1f}%)",
        flush=True,
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    settings = Settings()
    if args.database_path is not None:
        settings.database_path = args.database_path
    processed = asyncio.run(run_backfill(settings, args.batch_size, on_progress=_print_progress))
    print(f"money RAG backfill complete: processed={processed}", flush=True)


if __name__ == "__main__":
    main()
