"""HTTP adapters for the task service."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from ..attachments.errors import AttachmentError
from ..auth.service import CurrentAuth
from ..files.schemas import FileResponse
from ..files.service import FileRecord
from ..storage import DatabaseStorage
from ..tags.errors import TagError
from ..tasks.errors import TaskError
from ..tasks.schemas import (
    RecurrenceState,
    TaskCreateRequest,
    TaskListOrder,
    TaskListResponse,
    TaskPriority,
    TaskRecurrenceRequest,
    TaskReorderRequest,
    TaskResponse,
    TaskSeriesListResponse,
    TaskSeriesResponse,
    TaskSeriesUpdateRequest,
    TaskStatus,
    TaskSummaryResponse,
    TaskTagSummaryResponse,
    TaskUpdateRequest,
)
from ..tasks.service import (
    TaskListFilters,
    TaskRecord,
    TaskSeriesRecord,
    create_task,
    delete_task,
    end_task_series,
    get_task,
    get_task_series,
    list_task_series,
    list_tasks,
    pause_task_series,
    reorder_task,
    resume_task_series,
    skip_task_occurrence,
    summarize_tasks,
    update_task,
    update_task_series,
)
from .dependencies import (
    get_current_auth,
    get_database_storage,
    require_csrf_auth,
)

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])
series_router = APIRouter(prefix="/api/v1/task-series", tags=["task-series"])


def _raise_http(error: TaskError | TagError | AttachmentError) -> None:
    detail: dict[str, object] = {"code": error.code, "message": error.message}
    for attribute in ("unknown_tags", "allowed_tags"):
        if hasattr(error, attribute):
            detail[attribute] = getattr(error, attribute)
    raise HTTPException(status_code=error.status_code, detail=detail) from error


def _file_response(record: FileRecord) -> FileResponse:
    return FileResponse(
        id=record.id,
        name=record.name,
        size_bytes=record.size_bytes,
        sha256=record.sha256,
        tags=record.tags,
        context_status=record.context_status,
        created_at=record.created_at,
        updated_at=record.updated_at,
        deleted_at=record.deleted_at,
    )


def _response(record: TaskRecord) -> TaskResponse:
    return TaskResponse(
        id=record.id,
        title=record.title,
        description=record.description,
        status=record.status,
        priority=record.priority,
        position=record.position,
        start_at=record.start_at,
        due_at=record.due_at,
        tags=record.tags,
        attachments=[_file_response(file) for file in record.attachments],
        created_at=record.created_at,
        updated_at=record.updated_at,
        series_id=record.series_id,
        occurrence_key=record.occurrence_key,
        series_exception=record.series_exception,
        skipped_at=record.skipped_at,
    )


def _series_response(record: TaskSeriesRecord) -> TaskSeriesResponse:
    return TaskSeriesResponse(
        id=record.id,
        state=RecurrenceState(record.state),
        title=record.title,
        description=record.description,
        status=record.status,
        priority=record.priority,
        tags=record.tags,
        attachments=[_file_response(file) for file in record.attachments],
        recurrence=TaskRecurrenceRequest.model_validate(
            {
                "timezone": record.timezone,
                "frequency": record.frequency,
                "interval": record.interval,
                "weekdays": record.weekdays,
                "month_day": record.month_day,
                "month": record.month,
                "day": record.day,
                "until_date": record.until_date,
                "occurrence_count": record.occurrence_count,
            }
        ),
        materialized_through_at=record.materialized_through_at,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task_route(
    payload: TaskCreateRequest,
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(require_csrf_auth)],
) -> TaskResponse:
    """Create a task for the authenticated owner."""

    try:
        record = await create_task(storage, auth.user.id, payload)
    except (TaskError, TagError, AttachmentError) as exc:
        _raise_http(exc)
    return _response(record)


@router.get("/summary", response_model=TaskSummaryResponse)
async def task_summary_route(
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(get_current_auth)],
    timezone: Annotated[str, Query(min_length=1, max_length=64)] = "UTC",
) -> TaskSummaryResponse:
    """Return global counts for task views and populated tags."""

    try:
        summary = await summarize_tasks(storage, auth.user.id, timezone)
    except (TaskError, TagError, AttachmentError) as exc:
        _raise_http(exc)
    return TaskSummaryResponse(
        all=summary.all,
        today=summary.today,
        upcoming=summary.upcoming,
        overdue=summary.overdue,
        high_priority=summary.high_priority,
        tags=[
            TaskTagSummaryResponse(
                name=tag.name,
                count=tag.count,
                color=tag.color,
                active=tag.active,
            )
            for tag in summary.tags
        ],
    )


@router.get("", response_model=TaskListResponse)
async def list_tasks_route(
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(get_current_auth)],
    statuses: Annotated[list[TaskStatus] | None, Query(alias="status")] = None,
    priorities: Annotated[list[TaskPriority] | None, Query(alias="priority")] = None,
    tags: Annotated[list[str] | None, Query(alias="tag")] = None,
    search: Annotated[str | None, Query(max_length=200)] = None,
    due_from: datetime | None = None,
    due_to: datetime | None = None,
    scheduled_from: datetime | None = None,
    scheduled_to: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: str | None = None,
    order: TaskListOrder = TaskListOrder.DUE,
) -> TaskListResponse:
    """List non-deleted tasks using bounded cursor pagination."""

    try:
        page = await list_tasks(
            storage,
            auth.user.id,
            TaskListFilters(
                statuses=tuple(statuses or ()),
                priorities=tuple(priorities or ()),
                tags=tuple(tags or ()),
                search=search,
                due_from=due_from,
                due_to=due_to,
                scheduled_from=scheduled_from,
                scheduled_to=scheduled_to,
                limit=limit,
                cursor=cursor,
                order=order,
            ),
        )
    except (TaskError, TagError, AttachmentError) as exc:
        _raise_http(exc)
    return TaskListResponse(
        items=[_response(record) for record in page.items],
        next_cursor=page.next_cursor,
    )


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task_route(
    task_id: str,
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(get_current_auth)],
) -> TaskResponse:
    """Return one non-deleted task owned by the authenticated user."""

    try:
        record = await get_task(storage, auth.user.id, task_id)
    except (TaskError, TagError, AttachmentError) as exc:
        _raise_http(exc)
    return _response(record)


@router.post("/{task_id}/reorder", response_model=TaskResponse)
async def reorder_task_route(
    task_id: str,
    payload: TaskReorderRequest,
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(require_csrf_auth)],
) -> TaskResponse:
    """Move one owner-scoped task within the board ordering."""

    try:
        record = await reorder_task(storage, auth.user.id, task_id, payload)
    except (TaskError, TagError, AttachmentError) as exc:
        _raise_http(exc)
    return _response(record)


@router.patch("/{task_id}", response_model=TaskResponse)
async def update_task_route(
    task_id: str,
    payload: TaskUpdateRequest,
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(require_csrf_auth)],
) -> TaskResponse:
    """Apply a partial update to one owner-scoped task."""

    try:
        record = await update_task(storage, auth.user.id, task_id, payload)
    except (TaskError, TagError, AttachmentError) as exc:
        _raise_http(exc)
    return _response(record)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task_route(
    task_id: str,
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(require_csrf_auth)],
) -> Response:
    """Soft-delete one owner-scoped task."""

    try:
        await delete_task(storage, auth.user.id, task_id)
    except (TaskError, TagError, AttachmentError) as exc:
        _raise_http(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{task_id}/skip", response_model=TaskResponse)
async def skip_task_route(
    task_id: str,
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(require_csrf_auth)],
) -> TaskResponse:
    """Skip and retain one recurring task occurrence."""

    try:
        record = await skip_task_occurrence(storage, auth.user.id, task_id)
    except (TaskError, TagError, AttachmentError) as exc:
        _raise_http(exc)
    return _response(record)


@series_router.get("", response_model=TaskSeriesListResponse)
async def list_task_series_route(
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(get_current_auth)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> TaskSeriesListResponse:
    try:
        page = await list_task_series(storage, auth.user.id, limit)
    except (TaskError, TagError, AttachmentError) as exc:
        _raise_http(exc)
    return TaskSeriesListResponse(items=[_series_response(item) for item in page.items])


@series_router.get("/{series_id}", response_model=TaskSeriesResponse)
async def get_task_series_route(
    series_id: str,
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(get_current_auth)],
) -> TaskSeriesResponse:
    try:
        record = await get_task_series(storage, auth.user.id, series_id)
    except (TaskError, TagError, AttachmentError) as exc:
        _raise_http(exc)
    return _series_response(record)


@series_router.patch("/{series_id}", response_model=TaskSeriesResponse)
async def update_task_series_route(
    series_id: str,
    payload: TaskSeriesUpdateRequest,
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(require_csrf_auth)],
) -> TaskSeriesResponse:
    try:
        record = await update_task_series(storage, auth.user.id, series_id, payload)
    except (TaskError, TagError, AttachmentError) as exc:
        _raise_http(exc)
    return _series_response(record)


@series_router.post("/{series_id}/pause", response_model=TaskSeriesResponse)
async def pause_task_series_route(
    series_id: str,
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(require_csrf_auth)],
) -> TaskSeriesResponse:
    try:
        record = await pause_task_series(storage, auth.user.id, series_id)
    except (TaskError, TagError, AttachmentError) as exc:
        _raise_http(exc)
    return _series_response(record)


@series_router.post("/{series_id}/resume", response_model=TaskSeriesResponse)
async def resume_task_series_route(
    series_id: str,
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(require_csrf_auth)],
) -> TaskSeriesResponse:
    try:
        record = await resume_task_series(storage, auth.user.id, series_id)
    except (TaskError, AttachmentError) as exc:
        _raise_http(exc)
    return _series_response(record)


@series_router.post("/{series_id}/end", response_model=TaskSeriesResponse)
async def end_task_series_route(
    series_id: str,
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(require_csrf_auth)],
) -> TaskSeriesResponse:
    try:
        record = await end_task_series(storage, auth.user.id, series_id)
    except (TaskError, AttachmentError) as exc:
        _raise_http(exc)
    return _series_response(record)
