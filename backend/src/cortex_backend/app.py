"""Application composition and FastAPI entry point."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.auth import router as auth_router
from .api.files import router as files_router
from .api.health import router as health_router
from .api.logs import router as activity_logs_router
from .api.mcp import MCPAuthMiddleware
from .api.notes import router as notes_router
from .api.tags import router as tags_router
from .api.tasks import router as tasks_router
from .api.tasks import series_router as task_series_router
from .api.v1 import router as v1_router
from .auth.throttling import LoginThrottle
from .config import Settings, get_settings
from .files.processing import FileProcessingHealth, run_file_processing_loop
from .files.storage import FileBlobStore, LocalFileBlobStore
from .mcp import create_mcp_server
from .storage import ClosableStorage, DatabaseStorage, SQLiteStorage, Storage


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Release application-owned storage resources when the app shuts down."""

    processing_task: asyncio.Task[None] | None = None
    async with application.state.mcp_app.lifespan(application):
        try:
            if (
                application.state.settings.file_processing_enabled
                and isinstance(application.state.storage, DatabaseStorage)
                and isinstance(application.state.file_storage, FileBlobStore)
            ):
                processing_task = asyncio.create_task(
                    run_file_processing_loop(
                        application.state.storage,
                        application.state.file_storage,
                        application.state.settings,
                        application.state.file_processing_health,
                    )
                )
                application.state.file_processing_task = processing_task
            yield
        finally:
            if processing_task is not None:
                processing_task.cancel()
                with suppress(asyncio.CancelledError):
                    await processing_task
            application.state.file_processing_task = None
            storage = application.state.storage
            if isinstance(storage, ClosableStorage):
                await storage.close()


def create_app(
    settings: Settings | None = None,
    storage: Storage | None = None,
    file_storage: FileBlobStore | None = None,
) -> FastAPI:
    """Build an application with explicit settings and storage dependencies."""

    resolved_settings = settings or get_settings()
    resolved_storage = (
        storage if storage is not None else SQLiteStorage(resolved_settings.database_path)
    )
    resolved_file_storage = (
        file_storage
        if file_storage is not None
        else LocalFileBlobStore(resolved_settings.file_storage_path)
    )
    mcp_server = create_mcp_server(
        resolved_settings.app_name,
        resolved_storage,
        resolved_file_storage,
    )
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
    application.state.file_storage = resolved_file_storage
    application.state.mcp_server = mcp_server
    application.state.mcp_app = mcp_app
    application.state.login_throttle = LoginThrottle()
    application.state.file_processing_health = FileProcessingHealth(
        enabled=(
            resolved_settings.file_processing_enabled
            and isinstance(resolved_storage, DatabaseStorage)
            and isinstance(resolved_file_storage, FileBlobStore)
        )
    )
    application.state.file_processing_task = None

    application.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-CSRF-Token", "X-Setup-Secret"],
    )

    application.include_router(health_router)
    application.include_router(v1_router)
    application.include_router(auth_router)
    application.include_router(activity_logs_router)
    application.include_router(files_router)
    application.include_router(notes_router)
    application.include_router(tags_router)
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
