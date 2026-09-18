"""HTTP adapters for the task service."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from ..auth.service import CurrentAuth
from ..storage import DatabaseStorage
from ..tasks.errors import TaskError
from ..tasks.schemas import (
    TaskCreateRequest,
    TaskListOrder,
    TaskListResponse,
    TaskPriority,
    TaskReorderRequest,
    TaskResponse,
    TaskStatus,
    TaskUpdateRequest,
)
from ..tasks.service import (
    TaskListFilters,
    TaskRecord,
    create_task,
    delete_task,
    get_task,
    list_tasks,
    reorder_task,
    update_task,
)
from .dependencies import (
    get_current_auth,
    get_database_storage,
    require_csrf_auth,
)

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


def _raise_http(error: TaskError) -> None:
    raise HTTPException(
        status_code=error.status_code,
        detail={"code": error.code, "message": error.message},
    ) from error


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
    except TaskError as exc:
        _raise_http(exc)
    return _response(record)


@router.get("", response_model=TaskListResponse)
async def list_tasks_route(
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(get_current_auth)],
    statuses: Annotated[list[TaskStatus] | None, Query(alias="status")] = None,
    priorities: Annotated[list[TaskPriority] | None, Query(alias="priority")] = None,
    tags: Annotated[list[str] | None, Query(alias="tag")] = None,
    due_from: datetime | None = None,
    due_to: datetime | None = None,
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
                due_from=due_from,
                due_to=due_to,
                limit=limit,
                cursor=cursor,
                order=order,
            ),
        )
    except TaskError as exc:
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
    except TaskError as exc:
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
    except TaskError as exc:
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
    except TaskError as exc:
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
    except TaskError as exc:
        _raise_http(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
