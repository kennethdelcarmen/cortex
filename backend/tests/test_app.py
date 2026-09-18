"""HTTP behavior tests for the application foundation."""

from pathlib import Path

from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from cortex_backend.app import create_app
from cortex_backend.config import Settings
from cortex_backend.mcp import create_mcp_server
from cortex_backend.storage import InMemoryStorage, SQLiteStorage


class SpyStorage:
    def __init__(self, *, ready: bool = True) -> None:
        self.ready = ready
        self.checks = 0
        self.close_checks = 0

    async def check_ready(self) -> None:
        self.checks += 1
        if not self.ready:
            raise RuntimeError("storage unavailable")

    async def close(self) -> None:
        self.close_checks += 1


async def request(app: object, path: str) -> tuple[int, dict[str, object]]:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(path)
    return response.status_code, response.json()


async def test_healthz_is_dependency_free() -> None:
    app = create_app()

    status_code, body = await request(app, "/healthz")

    assert status_code == 200
    assert body == {"status": "ok"}


async def test_readyz_uses_injected_storage() -> None:
    storage = SpyStorage()
    app = create_app(storage=storage)

    status_code, body = await request(app, "/readyz")

    assert status_code == 200
    assert body == {"status": "ready"}
    assert storage.checks == 1


async def test_readyz_returns_stable_error_when_storage_is_unavailable() -> None:
    app = create_app(storage=SpyStorage(ready=False))

    status_code, body = await request(app, "/readyz")

    assert status_code == 503
    assert body == {
        "detail": {
            "code": "storage_unavailable",
            "message": "Storage is not ready.",
        }
    }


async def test_sqlite_storage_readiness_creates_database_file(tmp_path) -> None:
    database_path = tmp_path / "nested" / "cortex.db"
    storage = SQLiteStorage(database_path)

    await storage.check_ready()
    await storage.close()

    assert database_path.is_file()


async def test_sqlite_storage_enables_foreign_keys(tmp_path) -> None:
    storage = SQLiteStorage(tmp_path / "cortex.db")

    await storage.check_ready()
    async with storage.session() as session:
        result = await session.execute(text("PRAGMA foreign_keys"))

    await storage.close()
    assert result.scalar_one() == 1


async def test_readyz_returns_stable_error_for_invalid_sqlite_path(tmp_path) -> None:
    blocked_parent = tmp_path / "not-a-directory"
    blocked_parent.write_text("not a directory")
    app = create_app(settings=Settings(database_path=blocked_parent / "cortex.db"))

    status_code, body = await request(app, "/readyz")
    await app.state.storage.close()

    assert status_code == 503
    assert body == {
        "detail": {
            "code": "storage_unavailable",
            "message": "Storage is not ready.",
        }
    }


async def test_versioned_api_reports_service_metadata() -> None:
    app = create_app(settings=Settings(app_name="Test Cortex"))

    status_code, body = await request(app, "/api/v1")

    assert status_code == 200
    assert body == {"service": "Test Cortex", "api_version": "v1"}


async def test_mcp_transport_requires_bearer_authentication() -> None:
    app = create_app()

    status_code, body = await request(app, "/mcp/")

    assert status_code == 401
    assert body == {
        "code": "unauthenticated",
        "message": "Authentication is required.",
    }


def test_app_owns_mcp_registry_and_storage_seams() -> None:
    app = create_app(settings=Settings(database_path=Path("data/test-cortex.db")))

    assert isinstance(app.state.mcp_server, type(create_mcp_server()))
    assert isinstance(app.state.storage, SQLiteStorage)


async def test_app_closes_closable_storage_on_shutdown() -> None:
    storage = SpyStorage()
    app = create_app(storage=storage)

    async with app.router.lifespan_context(app):
        pass

    assert storage.close_checks == 1


def test_in_memory_storage_remains_available_for_isolated_tests() -> None:
    app = create_app(storage=InMemoryStorage())

    assert isinstance(app.state.storage, InMemoryStorage)
