"""FastMCP registry composition."""

from datetime import date, datetime

from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError

from .api.mcp import database_storage, get_mcp_auth
from .files.errors import FileError
from .files.schemas import FileContextResponse, FileListResponse, FileResponse
from .files.service import (
    DEFAULT_CONTEXT_CHARACTERS,
    MAX_CONTEXT_CHARACTERS,
    FileListFilters,
    FileRecord,
    delete_file,
    get_file,
    get_file_context,
    list_files,
    restore_file,
)
from .files.storage import FileBlobStore
from .logs.errors import ActivityLogError
from .logs.schemas import (
    ActivityLogCreateRequest,
    ActivityLogListResponse,
    ActivityLogResponse,
)
from .logs.service import ActivityLogFilters, ActivityLogRecord, append_log, list_logs
from .memory.errors import NoteError
from .memory.schemas import NoteCreateRequest, NoteListResponse, NoteResponse, NoteUpdateRequest
from .memory.service import (
    NoteListFilters,
    NoteRecord,
    create_note,
    delete_note,
    get_note,
    list_notes,
    restore_note,
    update_note,
)
from .storage import Storage
from .tags.errors import TagError
from .tags.schemas import TagListResponse, TagResponse
from .tags.service import list_tags
from .tasks.errors import TaskError
from .tasks.schemas import (
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
from .tasks.service import (
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


def _raise_tool(error: TaskError | NoteError | TagError) -> None:
    details = ""
    if hasattr(error, "unknown_tags") and hasattr(error, "allowed_tags"):
        details = f" Unknown tags: {error.unknown_tags}. Allowed tags: {error.allowed_tags}."
    raise ToolError(f"{error.code}: {error.message}{details}") from error


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


def _file_response(record: FileRecord) -> FileResponse:
    return FileResponse(
        id=record.id,
        name=record.name,
        size_bytes=record.size_bytes,
        sha256=record.sha256,
        context_status=record.context_status,
        created_at=record.created_at,
        updated_at=record.updated_at,
        deleted_at=record.deleted_at,
    )


def _raise_file_tool(error: FileError) -> None:
    raise ToolError(f"{error.code}: {error.message}") from error


def _note_response(record: NoteRecord) -> NoteResponse:
    return NoteResponse(
        id=record.id,
        title=record.title,
        body=record.body,
        journal_date=record.journal_date,
        tags=record.tags,
        created_at=record.created_at,
        updated_at=record.updated_at,
        deleted_at=record.deleted_at,
    )


def _raise_note_tool(error: NoteError | TagError) -> None:
    _raise_tool(error)


def create_mcp_server(
    name: str = "Cortex",
    storage: Storage | None = None,
    file_storage: FileBlobStore | None = None,
) -> FastMCP:
    """Create the MCP registry backed by shared domain service functions."""

    server = FastMCP(name)

    @server.tool(name="list_tags")
    async def list_tags_tool(ctx: Context | None = None) -> TagListResponse:
        """List active shared tags for note and task creation or updates."""

        del ctx
        records = await list_tags(
            database_storage(storage),
            get_mcp_auth().user.id,
        )
        return TagListResponse(
            items=[
                TagResponse(
                    id=record.id,
                    name=record.name,
                    color=record.color,
                    active=record.active,
                    created_at=record.created_at,
                    archived_at=record.archived_at,
                )
                for record in records
            ]
        )

    @server.tool(name="list_files")
    async def list_files_tool(
        include_deleted: bool = False,
        limit: int = 50,
        cursor: str | None = None,
        ctx: Context | None = None,
    ) -> FileListResponse:
        """List owner-scoped file metadata without returning binary contents."""

        del ctx
        try:
            page = await list_files(
                database_storage(storage),
                get_mcp_auth().user.id,
                FileListFilters(
                    include_deleted=include_deleted,
                    limit=limit,
                    cursor=cursor,
                ),
            )
        except FileError as exc:
            _raise_file_tool(exc)
        return FileListResponse(
            items=[_file_response(record) for record in page.items],
            next_cursor=page.next_cursor,
        )

    @server.tool(name="get_file")
    async def get_file_tool(file_id: str, ctx: Context) -> FileResponse:
        """Return one active owner-scoped file's metadata."""

        del ctx
        try:
            record = await get_file(database_storage(storage), get_mcp_auth().user.id, file_id)
        except FileError as exc:
            _raise_file_tool(exc)
        return _file_response(record)

    @server.tool(name="get_file_context")
    async def get_file_context_tool(
        file_id: str,
        max_characters: int = DEFAULT_CONTEXT_CHARACTERS,
        ctx: Context | None = None,
    ) -> FileContextResponse:
        """Return bounded extracted context for one active source file."""

        del ctx
        if not 1 <= max_characters <= MAX_CONTEXT_CHARACTERS:
            raise ToolError("invalid_file_query: The file list query is invalid.")
        try:
            if file_storage is None:
                raise ToolError("file_storage_unavailable: File storage is not available.")
            record = await get_file_context(
                database_storage(storage),
                file_storage,
                get_mcp_auth().user.id,
                file_id,
                max_characters,
            )
        except FileError as exc:
            _raise_file_tool(exc)
        return FileContextResponse(
            file_id=record.file_id,
            name=record.name,
            status=record.status,
            text=record.text,
            truncated=record.truncated,
            preview_kind=record.preview_kind,
            error=record.error,
            processed_at=record.processed_at,
        )

    @server.tool(name="delete_file")
    async def delete_file_tool(file_id: str, ctx: Context) -> str:
        """Soft-delete one active owner-scoped file."""

        del ctx
        try:
            await delete_file(database_storage(storage), get_mcp_auth().user.id, file_id)
        except FileError as exc:
            _raise_file_tool(exc)
        return "File deleted."

    @server.tool(name="restore_file")
    async def restore_file_tool(file_id: str, ctx: Context) -> FileResponse:
        """Restore one owner-scoped file."""

        del ctx
        try:
            record = await restore_file(database_storage(storage), get_mcp_auth().user.id, file_id)
        except FileError as exc:
            _raise_file_tool(exc)
        return _file_response(record)

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
        except (TaskError, TagError) as exc:
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
        except (TaskError, TagError) as exc:
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
        except (TaskError, TagError) as exc:
            _raise_tool(exc)
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

    @server.tool(name="get_task")
    async def get_task_tool(task_id: str, ctx: Context) -> TaskResponse:
        """Return one owner-scoped task."""

        del ctx
        try:
            record = await get_task(database_storage(storage), get_mcp_auth().user.id, task_id)
        except (TaskError, TagError) as exc:
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
        except (TaskError, TagError) as exc:
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
        except (TaskError, TagError) as exc:
            _raise_tool(exc)
        return _response(record)

    @server.tool(name="delete_task")
    async def delete_task_tool(task_id: str, ctx: Context) -> str:
        """Soft-delete one owner-scoped task."""

        del ctx
        try:
            await delete_task(database_storage(storage), get_mcp_auth().user.id, task_id)
        except (TaskError, TagError) as exc:
            _raise_tool(exc)
        return "Task deleted."

    @server.tool(name="skip_task_occurrence")
    async def skip_task_occurrence_tool(task_id: str, ctx: Context) -> TaskResponse:
        """Skip and retain one recurring task occurrence."""

        del ctx
        try:
            record = await skip_task_occurrence(
                database_storage(storage), get_mcp_auth().user.id, task_id
            )
        except (TaskError, TagError) as exc:
            _raise_tool(exc)
        return _response(record)

    @server.tool(name="list_task_series")
    async def list_task_series_tool(
        limit: int = 50,
        ctx: Context | None = None,
    ) -> TaskSeriesListResponse:
        """List owner-scoped recurrence series."""

        del ctx
        try:
            page = await list_task_series(database_storage(storage), get_mcp_auth().user.id, limit)
        except (TaskError, TagError) as exc:
            _raise_tool(exc)
        return TaskSeriesListResponse(items=[_series_response(item) for item in page.items])

    @server.tool(name="get_task_series")
    async def get_task_series_tool(series_id: str, ctx: Context) -> TaskSeriesResponse:
        """Return one owner-scoped recurrence series."""

        del ctx
        try:
            record = await get_task_series(
                database_storage(storage), get_mcp_auth().user.id, series_id
            )
        except (TaskError, TagError) as exc:
            _raise_tool(exc)
        return _series_response(record)

    @server.tool(name="update_task_series")
    async def update_task_series_tool(
        series_id: str,
        payload: TaskSeriesUpdateRequest,
        ctx: Context,
    ) -> TaskSeriesResponse:
        """Update a recurrence template or rule."""

        del ctx
        try:
            record = await update_task_series(
                database_storage(storage), get_mcp_auth().user.id, series_id, payload
            )
        except (TaskError, TagError) as exc:
            _raise_tool(exc)
        return _series_response(record)

    @server.tool(name="pause_task_series")
    async def pause_task_series_tool(series_id: str, ctx: Context) -> TaskSeriesResponse:
        """Pause future generation for a recurrence series."""

        del ctx
        try:
            record = await pause_task_series(
                database_storage(storage), get_mcp_auth().user.id, series_id
            )
        except (TaskError, TagError) as exc:
            _raise_tool(exc)
        return _series_response(record)

    @server.tool(name="resume_task_series")
    async def resume_task_series_tool(series_id: str, ctx: Context) -> TaskSeriesResponse:
        """Resume future generation for a recurrence series."""

        del ctx
        try:
            record = await resume_task_series(
                database_storage(storage), get_mcp_auth().user.id, series_id
            )
        except (TaskError, TagError) as exc:
            _raise_tool(exc)
        return _series_response(record)

    @server.tool(name="end_task_series")
    async def end_task_series_tool(series_id: str, ctx: Context) -> TaskSeriesResponse:
        """End future generation for a recurrence series."""

        del ctx
        try:
            record = await end_task_series(
                database_storage(storage), get_mcp_auth().user.id, series_id
            )
        except (TaskError, TagError) as exc:
            _raise_tool(exc)
        return _series_response(record)

    @server.tool(name="create_note")
    async def create_note_tool(payload: NoteCreateRequest, ctx: Context) -> NoteResponse:
        """Create an owner-scoped HTML note; legacy Markdown input is normalized."""

        del ctx
        try:
            record = await create_note(
                database_storage(storage),
                get_mcp_auth().user.id,
                payload,
            )
        except (NoteError, TagError) as exc:
            _raise_note_tool(exc)
        return _note_response(record)

    @server.tool(name="list_notes")
    async def list_notes_tool(
        tag: list[str] | None = None,
        search: str | None = None,
        journal_date_from: date | None = None,
        journal_date_to: date | None = None,
        include_deleted: bool = False,
        limit: int = 50,
        cursor: str | None = None,
        ctx: Context | None = None,
    ) -> NoteListResponse:
        """List owner-scoped notes; response bodies are sanitized HTML."""

        del ctx
        try:
            page = await list_notes(
                database_storage(storage),
                get_mcp_auth().user.id,
                NoteListFilters(
                    tags=tuple(tag or ()),
                    search=search,
                    journal_date_from=journal_date_from,
                    journal_date_to=journal_date_to,
                    include_deleted=include_deleted,
                    limit=limit,
                    cursor=cursor,
                ),
            )
        except (NoteError, TagError) as exc:
            _raise_note_tool(exc)
        return NoteListResponse(
            items=[_note_response(record) for record in page.items],
            next_cursor=page.next_cursor,
        )

    @server.tool(name="get_note")
    async def get_note_tool(note_id: str, ctx: Context) -> NoteResponse:
        """Return one active owner-scoped note with a sanitized HTML body."""

        del ctx
        try:
            record = await get_note(database_storage(storage), get_mcp_auth().user.id, note_id)
        except (NoteError, TagError) as exc:
            _raise_note_tool(exc)
        return _note_response(record)

    @server.tool(name="update_note")
    async def update_note_tool(
        note_id: str,
        payload: NoteUpdateRequest,
        ctx: Context,
    ) -> NoteResponse:
        """Update a note; legacy Markdown input is normalized and the body is returned as HTML."""

        del ctx
        try:
            record = await update_note(
                database_storage(storage), get_mcp_auth().user.id, note_id, payload
            )
        except (NoteError, TagError) as exc:
            _raise_note_tool(exc)
        return _note_response(record)

    @server.tool(name="delete_note")
    async def delete_note_tool(note_id: str, ctx: Context) -> str:
        """Soft-delete one active owner-scoped note."""

        del ctx
        try:
            await delete_note(database_storage(storage), get_mcp_auth().user.id, note_id)
        except (NoteError, TagError) as exc:
            _raise_note_tool(exc)
        return "Note deleted."

    @server.tool(name="restore_note")
    async def restore_note_tool(note_id: str, ctx: Context) -> NoteResponse:
        """Restore one owner-scoped note."""

        del ctx
        try:
            record = await restore_note(database_storage(storage), get_mcp_auth().user.id, note_id)
        except (NoteError, TagError) as exc:
            _raise_note_tool(exc)
        return _note_response(record)

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
