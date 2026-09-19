"""HTTP adapters for the activity-log service."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..auth.service import CurrentAuth
from ..logs.errors import ActivityLogError
from ..logs.schemas import (
    ActivityLogCreateRequest,
    ActivityLogListResponse,
    ActivityLogResponse,
)
from ..logs.service import (
    ActivityLogFilters,
    ActivityLogRecord,
    append_log,
    list_logs,
)
from ..storage import DatabaseStorage
from .dependencies import get_current_auth, get_database_storage, require_csrf_auth

router = APIRouter(prefix="/api/v1/activity-logs", tags=["activity-logs"])


def _raise_http(error: ActivityLogError) -> None:
    raise HTTPException(
        status_code=error.status_code,
        detail={"code": error.code, "message": error.message},
    ) from error


def _response(record: ActivityLogRecord) -> ActivityLogResponse:
    return ActivityLogResponse(
        id=record.id,
        user_id=record.user_id,
        event_type=record.event_type,
        entity_type=record.entity_type,
        entity_id=record.entity_id,
        metadata=record.metadata,
        created_at=record.created_at,
    )


@router.post("", response_model=ActivityLogResponse, status_code=status.HTTP_201_CREATED)
async def append_activity_log_route(
    payload: ActivityLogCreateRequest,
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(require_csrf_auth)],
) -> ActivityLogResponse:
    """Append one activity record for the authenticated owner."""

    try:
        record = await append_log(storage, auth.user.id, payload)
    except ActivityLogError as exc:
        _raise_http(exc)
    return _response(record)


@router.get("", response_model=ActivityLogListResponse)
async def list_activity_logs_route(
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(get_current_auth)],
    event_type: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    limit: Annotated[int, Query(description="Maximum number of records to return")] = 50,
    cursor: str | None = None,
) -> ActivityLogListResponse:
    """List newest-first activity records for the authenticated owner."""

    try:
        page = await list_logs(
            storage,
            auth.user.id,
            ActivityLogFilters(
                event_type=event_type,
                entity_type=entity_type,
                entity_id=entity_id,
                limit=limit,
                cursor=cursor,
            ),
        )
    except ActivityLogError as exc:
        _raise_http(exc)
    return ActivityLogListResponse(
        items=[_response(record) for record in page.items],
        next_cursor=page.next_cursor,
    )
