"""Local embedding provider, worker, and hybrid retrieval behavior."""

import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from struct import unpack

import pytest
from sqlalchemy import select, text

from cortex_backend.auth.models import User
from cortex_backend.chunking.service import ChunkSource, replace_source_chunks, search_chunks
from cortex_backend.config import Settings
from cortex_backend.embeddings.models import ContentChunkEmbedding
from cortex_backend.embeddings.provider import serialize_embedding
from cortex_backend.embeddings.service import process_embeddings_once
from cortex_backend.grounding.service import prepare_question
from cortex_backend.memory.models import Note
from cortex_backend.storage import SQLiteStorage


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


class FakeEmbeddingProvider:
    """Deterministic 384-dimensional provider for storage and retrieval tests."""

    model_name = "BAAI/bge-small-en-v1.5"
    dimensions = 384

    async def embed_documents(self, texts: list[str]) -> list[bytes]:
        return [self._embed(text) for text in texts]

    async def embed_query(self, text: str) -> bytes:
        return self._embed(text)

    @staticmethod
    def _embed(text: str) -> bytes:
        values = [0.0] * 384
        values[0] = 1.0 if "garden" in text.casefold() else 0.0
        values[1] = 1.0 if "finance" in text.casefold() else 0.0
        values[2] = 1.0 if not any(values) else 0.0
        return serialize_embedding(values, dimensions=384)


class FailingEmbeddingProvider(FakeEmbeddingProvider):
    async def embed_documents(self, texts: list[str]) -> list[bytes]:
        raise RuntimeError("model unavailable")

    async def embed_query(self, text: str) -> bytes:
        raise RuntimeError("model unavailable")


@pytest.mark.asyncio
async def test_provider_serializes_normalized_float32_vectors() -> None:
    vector = serialize_embedding([3.0, 4.0], dimensions=2)

    assert len(vector) == 8
    assert unpack("2f", vector) == pytest.approx((0.6, 0.8), abs=1e-6)


@pytest.mark.asyncio
async def test_embedding_worker_indexes_vectors_and_hybrid_search_is_owner_scoped(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "embeddings.db"
    migrate(database_path, monkeypatch)
    storage = SQLiteStorage(database_path, sqlite_vec_enabled=True)
    await storage.check_ready()
    assert await storage.vector_extension_ready()
    now = datetime.now(UTC)
    user_id = "00000000-0000-0000-0000-000000000101"
    note_id = "00000000-0000-0000-0000-000000000102"
    provider = FakeEmbeddingProvider()

    try:
        async with storage.session() as db:
            async with db.begin():
                db.add(
                    User(
                        id=user_id,
                        email="embedding@example.com",
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
                        title="Garden notes",
                        body="Garden planning",
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
                        title="Garden notes",
                        text="Garden planning and soil preparation",
                    ),
                    now=now,
                )

        async with storage.session() as db:
            pending = await db.scalars(select(ContentChunkEmbedding))
            assert [record.status for record in pending] == ["pending"]

        processed = await process_embeddings_once(
            storage,
            provider,
            Settings(
                database_path=database_path,
                embedding_batch_size=8,
                embedding_max_attempts=2,
            ),
        )
        assert processed == 1

        async with storage.session() as db:
            status = await db.scalar(select(ContentChunkEmbedding.status))
            vector_count = await db.scalar(text("SELECT count(*) FROM content_chunk_vectors"))
            assert status == "ready"
            assert vector_count == 1

        results = await search_chunks(
            storage,
            user_id,
            "garden planning",
            embedding_provider=provider,
        )
        assert [result.source_id for result in results] == [note_id]
        assert results[0].vector_distance is not None
        assert results[0].lexical_score is not None
        assert results[0].score > 0

        semantic = await search_chunks(
            storage,
            user_id,
            "garden question",
            embedding_provider=provider,
        )
        assert [result.source_id for result in semantic] == [note_id]
        assert semantic[0].lexical_score is None

        package = await prepare_question(
            storage,
            user_id,
            "garden question",
            embedding_provider=provider,
        )
        assert package.has_context
        assert package.citations[0].chunk_id == semantic[0].id
        assert package.citations[0].retrieval_score == semantic[0].score

        fallback = await search_chunks(
            storage,
            user_id,
            "garden planning",
            embedding_provider=FailingEmbeddingProvider(),
        )
        assert [result.source_id for result in fallback] == [note_id]
        assert fallback[0].vector_distance is None
    finally:
        await storage.close()


@pytest.mark.asyncio
async def test_embedding_failure_retries_then_exhausts(tmp_path: Path, monkeypatch) -> None:
    database_path = tmp_path / "retry.db"
    migrate(database_path, monkeypatch)
    storage = SQLiteStorage(database_path, sqlite_vec_enabled=True)
    now = datetime.now(UTC)
    user_id = "00000000-0000-0000-0000-000000000111"
    note_id = "00000000-0000-0000-0000-000000000112"

    try:
        async with storage.session() as db:
            async with db.begin():
                db.add(
                    User(
                        id=user_id,
                        email="retry@example.com",
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
                        title="Retry note",
                        body="Finance planning",
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
                        title="Retry note",
                        text="Finance planning",
                    ),
                    now=now,
                )

        settings = Settings(
            database_path=database_path,
            embedding_max_attempts=1,
            embedding_batch_size=1,
        )
        with pytest.raises(RuntimeError, match="model unavailable"):
            await process_embeddings_once(storage, FailingEmbeddingProvider(), settings)

        async with storage.session() as db:
            record = await db.scalar(select(ContentChunkEmbedding))
            assert record is not None
            assert record.status == "failed"
            assert record.attempts == 1
            assert record.last_error == "embedding_failed"
    finally:
        await storage.close()
