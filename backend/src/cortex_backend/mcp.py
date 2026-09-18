"""FastMCP registry composition."""

from datetime import datetime

from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError

from .api.mcp import database_storage, get_mcp_auth
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
        due_from: datetime | None = None,
        due_to: datetime | None = None,
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
                    due_from=due_from,
                    due_to=due_to,
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

    return server
