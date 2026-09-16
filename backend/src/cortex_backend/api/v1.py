"""Versioned REST routes."""

from typing import Annotated

from fastapi import APIRouter, Depends

from ..config import Settings
from .dependencies import get_settings
from .schemas import ApiMetadataResponse

router = APIRouter(prefix="/api/v1", tags=["api"])


@router.get("", response_model=ApiMetadataResponse)
async def api_metadata(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ApiMetadataResponse:
    """Describe the active versioned API surface."""

    return ApiMetadataResponse(
        service=settings.app_name,
        api_version="v1",
    )
