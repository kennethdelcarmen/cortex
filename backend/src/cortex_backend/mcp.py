"""FastMCP registry composition."""

from datetime import datetime

from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError

from .api.mcp import database_storage, get_mcp_auth
from .logs.errors import ActivityLogError
from .logs.schemas import (
    ActivityLogCreateRequest,
    ActivityLogListResponse,
    ActivityLogResponse,
)
from .logs.service import ActivityLogFilters, ActivityLogRecord, append_log, list_logs
from .storage import Storage
from .tasks.errors import TaskError
from .tasks.schemas import (
    TaskCreateRequest,
    TaskListOrder,
    TaskListResponse,
    TaskPriority,
    TaskReorderRequest,
    TaskResponse,
    TaskStatus,
    TaskSummaryResponse,
    TaskTagSummaryResponse,
    TaskUpdateRequest,
)
from .tasks.service import (
    TaskListFilters,
    TaskRecord,
    create_task,
    delete_task,
    get_task,
    list_tasks,
    reorder_task,
    summarize_tasks,
    update_task,
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
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _raise_tool(error: TaskError) -> None:
    raise ToolError(f"{error.code}: {error.message}") from error


def _activity_log_response(record: ActivityLogRecord) -> ActivityLogResponse:
    return ActivityLogResponse(
        id=record.id,
        user_id=record.user_id,
        event_type=record.event_type,
        entity_type=record.entity_type,
        entity_id=record.entity_id,
        metadata=record.metadata,
        created_at=record.created_at,
    )


def _raise_activity_log_tool(error: ActivityLogError) -> None:
    raise ToolError(f"{error.code}: {error.message}") from error


def create_mcp_server(name: str = "Cortex", storage: Storage | None = None) -> FastMCP:
    """Create the MCP registry backed by shared task service functions."""

    server = FastMCP(name)

    @server.tool(name="create_task")
    async def create_task_tool(payload: TaskCreateRequest, ctx: Context) -> TaskResponse:
        """Create an owner-scoped task."""

        del ctx
        try:
            record = await create_task(
                database_storage(storage),
                get_mcp_auth().user.id,
                payload,
            )
        except TaskError as exc:
            _raise_tool(exc)
        return _response(record)

    @server.tool(name="list_tasks")
    async def list_tasks_tool(
        status: list[TaskStatus] | None = None,
        priority: list[TaskPriority] | None = None,
        tag: list[str] | None = None,
        search: str | None = None,
        due_from: datetime | None = None,
        due_to: datetime | None = None,
        scheduled_from: datetime | None = None,
        scheduled_to: datetime | None = None,
        limit: int = 50,
        cursor: str | None = None,
        order: TaskListOrder = TaskListOrder.DUE,
        ctx: Context | None = None,
    ) -> TaskListResponse:
        """List owner-scoped tasks with the same filters as REST."""

        del ctx
        try:
            page = await list_tasks(
                database_storage(storage),
                get_mcp_auth().user.id,
                TaskListFilters(
                    statuses=tuple(status or ()),
                    priorities=tuple(priority or ()),
                    tags=tuple(tag or ()),
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
        except TaskError as exc:
            _raise_tool(exc)
        return TaskListResponse(
            items=[_response(record) for record in page.items],
            next_cursor=page.next_cursor,
        )

    @server.tool(name="get_task_summary")
    async def get_task_summary_tool(
        timezone: str = "UTC",
        ctx: Context | None = None,
    ) -> TaskSummaryResponse:
        """Return global task-view counts and populated tags."""

        del ctx
        try:
            summary = await summarize_tasks(
                database_storage(storage),
                get_mcp_auth().user.id,
                timezone,
            )
        except TaskError as exc:
            _raise_tool(exc)
        return TaskSummaryResponse(
            all=summary.all,
            today=summary.today,
            upcoming=summary.upcoming,
            overdue=summary.overdue,
            high_priority=summary.high_priority,
            tags=[TaskTagSummaryResponse(name=tag.name, count=tag.count) for tag in summary.tags],
        )

    @server.tool(name="get_task")
    async def get_task_tool(task_id: str, ctx: Context) -> TaskResponse:
        """Return one owner-scoped task."""

        del ctx
        try:
            record = await get_task(database_storage(storage), get_mcp_auth().user.id, task_id)
        except TaskError as exc:
            _raise_tool(exc)
        return _response(record)

    @server.tool(name="reorder_task")
    async def reorder_task_tool(
        task_id: str,
        payload: TaskReorderRequest,
        ctx: Context,
    ) -> TaskResponse:
        """Move one owner-scoped task within the board ordering."""

        del ctx
        try:
            record = await reorder_task(
                database_storage(storage),
                get_mcp_auth().user.id,
                task_id,
                payload,
            )
        except TaskError as exc:
            _raise_tool(exc)
        return _response(record)

    @server.tool(name="update_task")
    async def update_task_tool(
        task_id: str,
        payload: TaskUpdateRequest,
        ctx: Context,
    ) -> TaskResponse:
        """Apply a partial update to one owner-scoped task."""

        del ctx
        try:
            record = await update_task(
                database_storage(storage),
                get_mcp_auth().user.id,
                task_id,
                payload,
            )
        except TaskError as exc:
            _raise_tool(exc)
        return _response(record)

    @server.tool(name="delete_task")
    async def delete_task_tool(task_id: str, ctx: Context) -> str:
        """Soft-delete one owner-scoped task."""

        del ctx
        try:
            await delete_task(database_storage(storage), get_mcp_auth().user.id, task_id)
        except TaskError as exc:
            _raise_tool(exc)
        return "Task deleted."

    @server.tool(name="append_activity_log")
    async def append_activity_log_tool(
        payload: ActivityLogCreateRequest,
        ctx: Context,
    ) -> ActivityLogResponse:
        """Append one owner-scoped activity record."""

        del ctx
        try:
            record = await append_log(
                database_storage(storage),
                get_mcp_auth().user.id,
                payload,
            )
        except ActivityLogError as exc:
            _raise_activity_log_tool(exc)
        return _activity_log_response(record)

    @server.tool(name="list_activity_logs")
    async def list_activity_logs_tool(
        event_type: str | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
        ctx: Context | None = None,
    ) -> ActivityLogListResponse:
        """List owner-scoped activity records with bounded cursor pagination."""

        del ctx
        try:
            page = await list_logs(
                database_storage(storage),
                get_mcp_auth().user.id,
                ActivityLogFilters(
                    event_type=event_type,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    limit=limit,
                    cursor=cursor,
                ),
            )
        except ActivityLogError as exc:
            _raise_activity_log_tool(exc)
        return ActivityLogListResponse(
            items=[_activity_log_response(record) for record in page.items],
            next_cursor=page.next_cursor,
        )

    return server
