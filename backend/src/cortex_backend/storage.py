"""Persistence contracts and storage adapters."""

from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from sqlalchemy import event, text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


class Storage(Protocol):
    """Minimal persistence boundary required by the application."""

    async def check_ready(self) -> None:
        """Raise when the backing store cannot serve requests."""


@runtime_checkable
class DatabaseStorage(Storage, Protocol):
    """Persistence boundary for services that need transactional SQL access."""

    def session(self) -> AbstractAsyncContextManager[AsyncSession]:
        """Return an application-owned asynchronous database session."""


@runtime_checkable
class ClosableStorage(Storage, Protocol):
    """Optional lifecycle boundary for storage adapters with resources."""

    async def close(self) -> None:
        """Release resources owned by the adapter."""


class InMemoryStorage:
    """No-op storage adapter used by deterministic tests."""

    async def check_ready(self) -> None:
        """Report the in-memory adapter as ready."""

    async def close(self) -> None:
        """Release no resources."""


class SQLiteStorage:
    """Async SQLite storage foundation for future persisted domain features."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        self._engine: AsyncEngine = create_async_engine(
            URL.create(
                drivername="sqlite+aiosqlite",
                database=str(database_path),
            )
        )
        self._session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
            self._engine,
            expire_on_commit=False,
        )

        @event.listens_for(self._engine.sync_engine, "connect")
        def enable_sqlite_foreign_keys(dbapi_connection: Any, _: Any) -> None:
            """Enable SQLite foreign-key enforcement for every pooled connection."""

            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("PRAGMA foreign_keys=ON")
            finally:
                cursor.close()

    @property
    def database_path(self) -> Path:
        """Return the configured database file path."""

        return self._database_path

    async def check_ready(self) -> None:
        """Create the parent directory and verify that SQLite accepts a query."""

        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        async with self._engine.connect() as connection:
            await connection.execute(text("SELECT 1"))

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Yield a transactional-capable session without hiding commit policy."""

        async with self._session_factory() as session:
            yield session

    async def close(self) -> None:
        """Dispose the engine and any pooled resources."""

        await self._engine.dispose()
