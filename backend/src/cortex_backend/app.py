"""Application composition and FastAPI entry point."""

from fastapi import FastAPI

from .api.health import router as health_router
from .api.mcp import router as mcp_router
from .api.v1 import router as v1_router
from .config import Settings, get_settings
from .mcp import create_mcp_server
from .storage import InMemoryStorage, Storage


def create_app(
    settings: Settings | None = None,
    storage: Storage | None = None,
) -> FastAPI:
    """Build an application with explicit settings and storage dependencies."""

    resolved_settings = settings or get_settings()
    resolved_storage = storage or InMemoryStorage()

    application = FastAPI(
        title=resolved_settings.app_name,
        version=resolved_settings.service_version,
    )
    application.state.settings = resolved_settings
    application.state.storage = resolved_storage
    application.state.mcp_server = create_mcp_server(resolved_settings.app_name)

    application.include_router(health_router)
    application.include_router(v1_router)
    application.include_router(mcp_router)
    return application


app = create_app()
