"""HTTP behavior tests for the application foundation."""

from httpx import ASGITransport, AsyncClient

from cortex_backend.app import create_app
from cortex_backend.config import Settings
from cortex_backend.mcp import create_mcp_server
from cortex_backend.storage import InMemoryStorage


class SpyStorage:
    def __init__(self, *, ready: bool = True) -> None:
        self.ready = ready
        self.checks = 0

    async def check_ready(self) -> None:
        self.checks += 1
        if not self.ready:
            raise RuntimeError("storage unavailable")


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


async def test_versioned_api_reports_service_metadata() -> None:
    app = create_app(settings=Settings(app_name="Test Cortex"))

    status_code, body = await request(app, "/api/v1")

    assert status_code == 200
    assert body == {"service": "Test Cortex", "api_version": "v1"}


async def test_mcp_transport_is_explicitly_deferred() -> None:
    app = create_app()

    status_code, body = await request(app, "/mcp")

    assert status_code == 501
    assert body == {
        "code": "mcp_transport_not_configured",
        "message": "MCP transport is not configured yet.",
    }


def test_app_owns_mcp_registry_and_storage_seams() -> None:
    app = create_app()

    assert isinstance(app.state.mcp_server, type(create_mcp_server()))
    assert isinstance(app.state.storage, InMemoryStorage)
