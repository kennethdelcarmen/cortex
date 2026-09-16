"""Operational health and readiness routes."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from ..storage import Storage
from .dependencies import get_storage
from .schemas import HealthResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


@router.get("/healthz", response_model=HealthResponse)
async def healthz() -> HealthResponse:
    """Return liveness without requiring external dependencies."""

    return HealthResponse(status="ok")


@router.get(
    "/readyz",
    response_model=HealthResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": HealthResponse}},
)
async def readyz(
    storage: Annotated[Storage, Depends(get_storage)],
) -> HealthResponse:
    """Return readiness after checking the configured storage boundary."""

    try:
        await storage.check_ready()
    except Exception as exc:
        logger.exception("Storage readiness check failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "storage_unavailable", "message": "Storage is not ready."},
        ) from exc

    return HealthResponse(status="ready")
