"""Application composition and FastAPI entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.auth import router as auth_router
from .api.health import router as health_router
from .api.logs import router as activity_logs_router
from .api.mcp import MCPAuthMiddleware
from .api.tasks import router as tasks_router
from .api.tasks import series_router as task_series_router
from .api.v1 import router as v1_router
from .auth.throttling import LoginThrottle
from .config import Settings, get_settings
from .mcp import create_mcp_server
from .storage import ClosableStorage, SQLiteStorage, Storage


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Release application-owned storage resources when the app shuts down."""

    async with application.state.mcp_app.lifespan(application):
        try:
            yield
        finally:
            storage = application.state.storage
            if isinstance(storage, ClosableStorage):
                await storage.close()


def create_app(
    settings: Settings | None = None,
    storage: Storage | None = None,
) -> FastAPI:
    """Build an application with explicit settings and storage dependencies."""

    resolved_settings = settings or get_settings()
    resolved_storage = (
        storage if storage is not None else SQLiteStorage(resolved_settings.database_path)
    )
    mcp_server = create_mcp_server(resolved_settings.app_name, resolved_storage)
    mcp_app = mcp_server.http_app(
        json_response=True,
        path="/",
        stateless_http=True,
        transport="streamable-http",
    )

    application = FastAPI(
        title=resolved_settings.app_name,
        version=resolved_settings.service_version,
        lifespan=lifespan,
    )
    application.state.settings = resolved_settings
    application.state.storage = resolved_storage
    application.state.mcp_server = mcp_server
    application.state.mcp_app = mcp_app
    application.state.login_throttle = LoginThrottle()

    application.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-CSRF-Token", "X-Setup-Secret"],
    )

    application.include_router(health_router)
    application.include_router(v1_router)
    application.include_router(auth_router)
    application.include_router(activity_logs_router)
    application.include_router(tasks_router)
    application.include_router(task_series_router)
    application.mount(
        "/mcp",
        MCPAuthMiddleware(
            mcp_app,
            resolved_storage,
        ),
    )
    return application


app = create_app()
