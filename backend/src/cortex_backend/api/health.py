"""Operational health and readiness routes."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..files.processing import FileProcessingHealth
from ..files.storage import FileBlobStore
from ..storage import Storage
from .dependencies import get_file_storage, get_storage
from .schemas import HealthResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


@router.get("/healthz", response_model=HealthResponse, response_model_exclude_defaults=True)
async def healthz() -> HealthResponse:
    """Return liveness without requiring external dependencies."""

    return HealthResponse(status="ok")


@router.get(
    "/readyz",
    response_model=HealthResponse,
    response_model_exclude_defaults=True,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": HealthResponse}},
)
async def readyz(
    request: Request,
    storage: Annotated[Storage, Depends(get_storage)],
    file_storage: Annotated[FileBlobStore, Depends(get_file_storage)],
) -> HealthResponse:
    """Return readiness after checking database and file storage boundaries."""

    try:
        await storage.check_ready()
        await file_storage.check_ready()
    except Exception as exc:
        logger.exception("Storage readiness check failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "storage_unavailable", "message": "Storage is not ready."},
        ) from exc

    worker_health: FileProcessingHealth | None = getattr(
        request.app.state, "file_processing_health", None
    )
    if worker_health is not None and worker_health.enabled:
        worker_task = getattr(request.app.state, "file_processing_task", None)
        if not worker_health.ready or worker_task is None or worker_task.done():
            logger.error(
                "File context worker is not ready",
                extra={"state": worker_health.state},
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "code": "file_processing_unavailable",
                    "message": "File processing worker is not ready.",
                },
            )

        if worker_health.warnings:
            return HealthResponse(status="degraded", warnings=list(worker_health.warnings))

    return HealthResponse(status="ready")
