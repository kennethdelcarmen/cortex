"""Command-line backfill for local chunk embeddings."""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence
from pathlib import Path

from sqlalchemy import func, select

from ..config import Settings
from ..storage import SQLiteStorage
from .models import ContentChunkEmbedding
from .provider import LocalEmbeddingProvider
from .service import process_embeddings_once


async def run_backfill(settings: Settings) -> int:
    """Process pending embedding jobs until the queue is empty or blocked."""

    storage = SQLiteStorage(settings.database_path, sqlite_vec_enabled=True)
    provider = LocalEmbeddingProvider(settings.embedding_model_cache_path)
    processed = 0
    try:
        await storage.check_ready()
        while True:
            count = await process_embeddings_once(storage, provider, settings)
            processed += count
            if count == 0:
                break
        return processed
    finally:
        await storage.close()


async def pending_count(settings: Settings) -> int:
    """Return the number of pending or leased jobs for progress diagnostics."""

    storage = SQLiteStorage(settings.database_path)
    try:
        async with storage.session() as db:
            return int(
                (
                    await db.scalar(
                        select(func.count())
                        .select_from(ContentChunkEmbedding)
                        .where(ContentChunkEmbedding.status.in_(["pending", "processing"]))
                    )
                )
                or 0
            )
    finally:
        await storage.close()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Backfill Cortex local chunk embeddings.")
    parser.add_argument("--database-path", type=Path)
    parser.add_argument("--cache-path", type=Path)
    parser.add_argument("--batch-size", type=int)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    settings = Settings(embeddings_enabled=True)
    if args.database_path is not None:
        settings.database_path = args.database_path
    if args.cache_path is not None:
        settings.embedding_model_cache_path = args.cache_path
    if args.batch_size is not None:
        settings.embedding_batch_size = args.batch_size
    processed = asyncio.run(run_backfill(settings))
    print(f"embedding backfill complete: {processed} chunks", flush=True)


if __name__ == "__main__":
    main()
