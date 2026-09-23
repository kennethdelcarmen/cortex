"""Owner-scoped task use cases over the shared database storage seam."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import and_, case, delete, func, or_, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from ..storage import DatabaseStorage
from ..tags.schemas import TagColor
from ..tags.service import existing_tag_names, resolve_tag_names
from .errors import (
    InvalidCursorError,
    InvalidTaskDatesError,
    InvalidTaskDateTimezoneError,
    InvalidTaskQueryError,
    InvalidTaskRecurrenceError,
    InvalidTaskReorderError,
    InvalidTaskSeriesStateError,
    InvalidTaskSummaryTimezoneError,
    InvalidTaskTagError,
    RecurrenceAnchorRequiredError,
    TaskNotFoundError,
    TaskOccurrenceRequiredError,
    TaskSeriesNotFoundError,
)
from .models import Tag, Task, TaskSeries, TaskSeriesTag, TaskTag
from .recurrence import (
    HORIZON_DAYS,
    MAX_OCCURRENCES_PER_MATERIALIZATION,
    iter_occurrences,
    recurrence_request,
    split_recurrence,
    timezone_or_error,
)
from .schemas import (
    TaskCreateRequest,
    TaskListOrder,
    TaskPriority,
    TaskRecurrenceRequest,
    TaskReorderRequest,
    TaskSeriesUpdateRequest,
    TaskStatus,
    TaskUpdateRequest,
)


@dataclass(frozen=True)
class TaskRecord:
    id: str
    title: str
    description: str | None
    status: TaskStatus
    priority: TaskPriority
    position: int
    start_at: datetime | None
    due_at: datetime | None
    tags: list[str]
    created_at: datetime
    updated_at: datetime
    series_id: str | None
    occurrence_key: str | None
    series_exception: bool
    skipped_at: datetime | None


@dataclass(frozen=True)
class TaskSeriesRecord:
    id: str
    state: str
    title: str
    description: str | None
    status: TaskStatus
    priority: TaskPriority
    tags: list[str]
    timezone: str
    frequency: str
    interval: int
    weekdays: list[str]
    month_day: int | None
    month: int | None
    day: int | None
    until_date: date | None
    occurrence_count: int | None
    materialized_through_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class TaskSeriesPage:
    items: list[TaskSeriesRecord]


@dataclass(frozen=True)
class TaskListFilters:
    statuses: tuple[TaskStatus, ...] = ()
    priorities: tuple[TaskPriority, ...] = ()
    tags: tuple[str, ...] = ()
    search: str | None = None
    due_from: datetime | None = None
    due_to: datetime | None = None
    scheduled_from: datetime | None = None
    scheduled_to: datetime | None = None
    limit: int = 50
    cursor: str | None = None
    order: TaskListOrder = TaskListOrder.DUE


@dataclass(frozen=True)
class TaskPage:
    items: list[TaskRecord]
    next_cursor: str | None


@dataclass(frozen=True)
class TaskTagSummaryRecord:
    name: str
    count: int
    color: TagColor
    active: bool


@dataclass(frozen=True)
class TaskSummaryRecord:
    all: int
    today: int
    upcoming: int
    overdue: int
    high_priority: int
    tags: list[TaskTagSummaryRecord]


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _aware_or_error(value: datetime | None) -> datetime | None:
    if value is not None and value.utcoffset() is None:
        raise InvalidTaskDateTimezoneError()
    return value


def _normalized_input_datetime(value: datetime | None) -> datetime | None:
    value = _aware_or_error(value)
    return value.astimezone(UTC) if value is not None else None


def _validate_date_range(start_at: datetime | None, due_at: datetime | None) -> None:
    start_at = _aware_or_error(start_at)
    due_at = _aware_or_error(due_at)
    if start_at is not None and due_at is not None and start_at > due_at:
        raise InvalidTaskDatesError()


def normalize_tag_name(value: str) -> str:
    normalized = value.strip().casefold()
    if not normalized or len(normalized) > 64:
        raise InvalidTaskTagError()
    return normalized


def normalize_tag_names(values: list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
    if values is None:
        return ()
    normalized: dict[str, None] = {}
    for value in values:
        name = normalize_tag_name(value)
        normalized[name] = None
    if len(normalized) > 20:
        raise InvalidTaskTagError()
    return tuple(normalized)


def normalize_search(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().casefold()
    if not normalized:
        return None
    if len(normalized) > 200:
        raise InvalidTaskQueryError()
    return normalized


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _required_utc(value: datetime) -> datetime:
    normalized = _as_utc(value)
    assert normalized is not None
    return normalized


def _record(task: Task, tags: list[str]) -> TaskRecord:
    return TaskRecord(
        id=task.id,
        title=task.title,
        description=task.description,
        status=TaskStatus(task.status),
        priority=TaskPriority(task.priority),
        position=task.position,
        start_at=_as_utc(task.start_at),
        due_at=_as_utc(task.due_at),
        tags=tags,
        created_at=_required_utc(task.created_at),
        updated_at=_required_utc(task.updated_at),
        series_id=task.series_id,
        occurrence_key=task.occurrence_key,
        series_exception=task.series_exception,
        skipped_at=_as_utc(task.skipped_at),
    )


async def _tags_for_tasks(db: AsyncSession, task_ids: list[str]) -> dict[str, list[str]]:
    if not task_ids:
        return {}
    result = await db.execute(
        select(TaskTag.task_id, Tag.name)
        .join(Tag, Tag.id == TaskTag.tag_id)
        .where(TaskTag.task_id.in_(task_ids))
        .order_by(Tag.name.asc())
    )
    tags: dict[str, list[str]] = defaultdict(list)
    for task_id, name in result.all():
        tags[task_id].append(name)
    return tags


async def _replace_tags(
    db: AsyncSession,
    task_id: str,
    user_id: str,
    tag_names: list[str] | tuple[str, ...] | None,
) -> None:
    normalized_names = normalize_tag_names(tag_names)
    retained_names = await existing_tag_names(db, TaskTag, task_id)
    resolved = await resolve_tag_names(
        db,
        user_id,
        normalized_names,
        retain_inactive=retained_names,
    )
    await db.execute(delete(TaskTag).where(TaskTag.task_id == task_id))
    for name in normalized_names:
        tag = resolved[name]
        db.add(TaskTag(task_id=task_id, tag_id=tag.id))
    await db.flush()


async def _series_tags_for_series(db: AsyncSession, series_id: str) -> list[str]:
    result = await db.execute(
        select(Tag.name)
        .join(TaskSeriesTag, TaskSeriesTag.tag_id == Tag.id)
        .where(TaskSeriesTag.series_id == series_id)
        .order_by(Tag.name.asc())
    )
    return [name for (name,) in result.all()]


async def _replace_series_tags(
    db: AsyncSession,
    series_id: str,
    user_id: str,
    tag_names: list[str] | tuple[str, ...],
) -> None:
    normalized_names = normalize_tag_names(tag_names)
    retained_names = await existing_tag_names(db, TaskSeriesTag, series_id)
    resolved = await resolve_tag_names(
        db,
        user_id,
        normalized_names,
        retain_inactive=retained_names,
    )
    await db.execute(delete(TaskSeriesTag).where(TaskSeriesTag.series_id == series_id))
    for name in normalized_names:
        tag = resolved[name]
        db.add(TaskSeriesTag(series_id=series_id, tag_id=tag.id))
    await db.flush()


async def _get_series_row(db: AsyncSession, user_id: str, series_id: str) -> TaskSeries:
    series = await db.scalar(
        select(TaskSeries).where(TaskSeries.id == series_id, TaskSeries.user_id == user_id).limit(1)
    )
    if series is None:
        raise TaskSeriesNotFoundError()
    return series


def _series_record(series: TaskSeries, tags: list[str]) -> TaskSeriesRecord:
    rule = recurrence_request(series.timezone, series.rule)
    return TaskSeriesRecord(
        id=series.id,
        state=series.state,
        title=series.title,
        description=series.description,
        status=TaskStatus(series.status),
        priority=TaskPriority(series.priority),
        tags=tags,
        timezone=rule.timezone,
        frequency=rule.frequency.value,
        interval=rule.interval,
        weekdays=[weekday.value for weekday in rule.weekdays],
        month_day=rule.month_day,
        month=rule.month,
        day=rule.day,
        until_date=rule.until_date,
        occurrence_count=rule.occurrence_count,
        materialized_through_at=_as_utc(series.materialized_through_at),
        created_at=_required_utc(series.created_at),
        updated_at=_required_utc(series.updated_at),
    )


def _series_schedule(
    start_at: datetime | None,
    due_at: datetime | None,
) -> tuple[datetime, str, int | None]:
    if start_at is None and due_at is None:
        raise RecurrenceAnchorRequiredError()
    if start_at is not None and due_at is not None:
        duration = int((due_at - start_at).total_seconds())
        return start_at, "start", duration
    if start_at is not None:
        return start_at, "start", None
    assert due_at is not None
    return due_at, "due", None


def _validate_recurrence_schedule(
    payload: TaskRecurrenceRequest,
    anchor_at: datetime,
) -> None:
    timezone = timezone_or_error(payload.timezone)
    anchor_date = anchor_at.astimezone(timezone).date()
    if payload.until_date is not None and payload.until_date < anchor_date:
        raise InvalidTaskRecurrenceError()


def _occurrence_window(
    series: TaskSeries,
    occurrence_at: datetime,
) -> tuple[datetime | None, datetime | None]:
    if series.anchor_kind == "start":
        start_at = occurrence_at
        due_at = (
            occurrence_at + timedelta(seconds=series.duration_seconds)
            if series.duration_seconds is not None
            else None
        )
        return start_at, due_at
    return None, occurrence_at


async def _materialize_series(
    db: AsyncSession,
    series: TaskSeries,
    now: datetime,
) -> None:
    """Materialize one active series through the bounded future horizon."""

    if series.state != "active":
        return

    target = max(now + timedelta(days=HORIZON_DAYS), _required_utc(series.anchor_at))
    after_at = _as_utc(series.materialized_through_at)
    tag_rows = await db.execute(
        select(TaskSeriesTag.tag_id).where(TaskSeriesTag.series_id == series.id)
    )
    tag_ids = [tag_id for (tag_id,) in tag_rows.all()]
    generated = iter_occurrences(
        _required_utc(series.anchor_at),
        series.timezone,
        series.rule,
        after_at=after_at,
        through_at=target,
        limit=MAX_OCCURRENCES_PER_MATERIALIZATION,
    )

    for occurrence in generated:
        start_at, due_at = _occurrence_window(series, occurrence.utc_at)
        position = await _next_position(db, series.user_id, series.status)
        task_id = str(uuid4())
        statement = (
            sqlite_insert(Task)
            .values(
                id=task_id,
                user_id=series.user_id,
                title=series.title,
                description=series.description,
                status=series.status,
                priority=series.priority,
                position=position,
                start_at=start_at,
                due_at=due_at,
                created_at=now,
                updated_at=now,
                deleted_at=None,
                series_id=series.id,
                occurrence_key=occurrence.key,
                series_exception=False,
                skipped_at=None,
            )
            .on_conflict_do_nothing(index_elements=["series_id", "occurrence_key"])
        )
        result = await db.execute(statement)
        if getattr(result, "rowcount", 0):
            for tag_id in tag_ids:
                await db.execute(
                    sqlite_insert(TaskTag)
                    .values(task_id=task_id, tag_id=tag_id)
                    .on_conflict_do_nothing()
                )
        series.materialized_through_at = occurrence.utc_at

    series.updated_at = now
    await db.flush()


async def _get_task_row(db: AsyncSession, user_id: str, task_id: str) -> Task:
    task = await db.scalar(
        select(Task)
        .where(
            Task.id == task_id,
            Task.user_id == user_id,
            Task.deleted_at.is_(None),
        )
        .limit(1)
    )
    if task is None:
        raise TaskNotFoundError()
    return task


def _status_rank_expression() -> ColumnElement[int]:
    return case(
        (Task.status == TaskStatus.BACKLOG.value, 0),
        (Task.status == TaskStatus.TODO.value, 1),
        (Task.status == TaskStatus.IN_PROGRESS.value, 2),
        (Task.status == TaskStatus.DONE.value, 3),
        (Task.status == TaskStatus.CANCELED.value, 4),
        else_=5,
    )


async def _next_position(db: AsyncSession, user_id: str, status: str) -> int:
    maximum = await db.scalar(
        select(func.max(Task.position)).where(
            Task.user_id == user_id,
            Task.status == status,
            Task.deleted_at.is_(None),
        )
    )
    return int(maximum) + 1 if maximum is not None else 0


async def _remove_from_column(db: AsyncSession, task: Task) -> None:
    old_position = task.position
    task.position = -1
    await db.flush()
    await db.execute(
        update(Task)
        .where(
            Task.user_id == task.user_id,
            Task.status == task.status,
            Task.deleted_at.is_(None),
            Task.position > old_position,
        )
        .values(position=Task.position - 1)
    )


async def _move_to_column_end(db: AsyncSession, task: Task, status: str) -> None:
    if task.status != status:
        await _remove_from_column(db, task)
        task.status = status
        task.position = await _next_position(db, task.user_id, status)


async def create_task(
    storage: DatabaseStorage,
    user_id: str,
    payload: TaskCreateRequest,
) -> TaskRecord:
    """Create an owner-scoped task and its normalized tag memberships."""

    start_at = _normalized_input_datetime(payload.start_at)
    due_at = _normalized_input_datetime(payload.due_at)
    _validate_date_range(start_at, due_at)
    now = _utc_now()
    async with storage.session() as db:
        async with db.begin():
            if payload.recurrence is not None:
                timezone_name, rule = split_recurrence(payload.recurrence)
                timezone_or_error(timezone_name)
                anchor_at, anchor_kind, duration_seconds = _series_schedule(start_at, due_at)
                _validate_recurrence_schedule(payload.recurrence, anchor_at)
                series = TaskSeries(
                    id=str(uuid4()),
                    user_id=user_id,
                    title=payload.title,
                    description=payload.description,
                    status=payload.status.value,
                    priority=payload.priority.value,
                    timezone=timezone_name,
                    anchor_at=anchor_at,
                    anchor_kind=anchor_kind,
                    duration_seconds=duration_seconds,
                    rule=rule,
                    until_date=payload.recurrence.until_date,
                    occurrence_count=payload.recurrence.occurrence_count,
                    state="active",
                    materialized_through_at=None,
                    created_at=now,
                    updated_at=now,
                )
                db.add(series)
                await db.flush()
                await _replace_series_tags(db, series.id, user_id, payload.tags)
                await _materialize_series(db, series, now)
                first_occurrence = next(
                    iter_occurrences(
                        anchor_at,
                        timezone_name,
                        rule,
                        limit=1,
                    )
                )
                task = await db.scalar(
                    select(Task)
                    .where(
                        Task.user_id == user_id,
                        Task.series_id == series.id,
                        Task.occurrence_key == first_occurrence.key,
                    )
                    .limit(1)
                )
                assert task is not None
                tags = await _tags_for_tasks(db, [task.id])
                return _record(task, tags.get(task.id, []))

            task = Task(
                id=str(uuid4()),
                user_id=user_id,
                title=payload.title,
                description=payload.description,
                status=payload.status.value,
                priority=payload.priority.value,
                position=await _next_position(db, user_id, payload.status.value),
                start_at=start_at,
                due_at=due_at,
                created_at=now,
                updated_at=now,
                series_id=None,
                occurrence_key=None,
                series_exception=False,
                skipped_at=None,
            )
            db.add(task)
            await db.flush()
            await _replace_tags(db, task.id, user_id, payload.tags)
            tags = await _tags_for_tasks(db, [task.id])
            return _record(task, tags.get(task.id, []))


async def get_task(storage: DatabaseStorage, user_id: str, task_id: str) -> TaskRecord:
    """Return one non-deleted task owned by the authenticated user."""

    async with storage.session() as db:
        task = await _get_task_row(db, user_id, task_id)
        tags = await _tags_for_tasks(db, [task.id])
        return _record(task, tags.get(task.id, []))


def _filter_fingerprint(filters: TaskListFilters) -> str:
    payload = {
        "statuses": [status.value for status in filters.statuses],
        "priorities": [priority.value for priority in filters.priorities],
        "tags": list(normalize_tag_names(filters.tags)),
        "search": normalize_search(filters.search),
        "due_from": filters.due_from.isoformat() if filters.due_from else None,
        "due_to": filters.due_to.isoformat() if filters.due_to else None,
        "scheduled_from": (filters.scheduled_from.isoformat() if filters.scheduled_from else None),
        "scheduled_to": filters.scheduled_to.isoformat() if filters.scheduled_to else None,
    }
    if filters.order != TaskListOrder.DUE:
        payload["order"] = filters.order.value
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _encode_cursor(task: Task, fingerprint: str) -> str:
    payload = {
        "v": 1,
        "f": fingerprint,
        "due_at": _required_utc(task.due_at).isoformat() if task.due_at else None,
        "created_at": _required_utc(task.created_at).isoformat(),
        "id": task.id,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _encode_board_cursor(task: Task, fingerprint: str) -> str:
    payload = {
        "v": 2,
        "f": fingerprint,
        "status": task.status,
        "position": task.position,
        "created_at": _required_utc(task.created_at).isoformat(),
        "id": task.id,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str, fingerprint: str) -> tuple[datetime | None, datetime, str]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
        if payload.get("v") != 1 or payload.get("f") != fingerprint:
            raise ValueError
        due_at = payload.get("due_at")
        created_at = datetime.fromisoformat(payload["created_at"])
        task_id = payload["id"]
        if not isinstance(task_id, str) or not task_id:
            raise ValueError
        if due_at is not None:
            due_at = datetime.fromisoformat(due_at)
        if created_at.tzinfo is None or (due_at is not None and due_at.tzinfo is None):
            raise ValueError
        return due_at, created_at, task_id
    except (binascii.Error, ValueError, KeyError, TypeError, json.JSONDecodeError):
        raise InvalidCursorError() from None


def _decode_board_cursor(cursor: str, fingerprint: str) -> tuple[str, int, datetime, str]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
        if payload.get("v") != 2 or payload.get("f") != fingerprint:
            raise ValueError
        status = payload["status"]
        position = payload["position"]
        created_at = datetime.fromisoformat(payload["created_at"])
        task_id = payload["id"]
        if status not in {status.value for status in TaskStatus}:
            raise ValueError
        if not isinstance(position, int) or position < 0:
            raise ValueError
        if not isinstance(task_id, str) or not task_id:
            raise ValueError
        if created_at.tzinfo is None:
            raise ValueError
        return status, position, created_at, task_id
    except (binascii.Error, ValueError, KeyError, TypeError, json.JSONDecodeError):
        raise InvalidCursorError() from None


async def _materialize_active_series(
    db: AsyncSession,
    user_id: str,
    now: datetime,
) -> None:
    series_rows = list(
        (
            await db.scalars(
                select(TaskSeries).where(
                    TaskSeries.user_id == user_id,
                    TaskSeries.state == "active",
                )
            )
        ).all()
    )
    for series in series_rows:
        await _materialize_series(db, series, now)


async def list_tasks(
    storage: DatabaseStorage,
    user_id: str,
    filters: TaskListFilters,
) -> TaskPage:
    """Return a bounded, filtered page in due-date or board order."""

    if not 1 <= filters.limit <= 100:
        raise InvalidTaskQueryError()
    due_from = _normalized_input_datetime(filters.due_from)
    due_to = _normalized_input_datetime(filters.due_to)
    scheduled_from = _normalized_input_datetime(filters.scheduled_from)
    scheduled_to = _normalized_input_datetime(filters.scheduled_to)
    if (due_from is not None and due_to is not None and due_from > due_to) or (
        scheduled_from is not None and scheduled_to is not None and scheduled_from > scheduled_to
    ):
        raise InvalidTaskDatesError()

    normalized_tags = normalize_tag_names(filters.tags)
    normalized_filters = TaskListFilters(
        statuses=filters.statuses,
        priorities=filters.priorities,
        tags=normalized_tags,
        search=normalize_search(filters.search),
        due_from=due_from,
        due_to=due_to,
        scheduled_from=scheduled_from,
        scheduled_to=scheduled_to,
        limit=filters.limit,
        cursor=filters.cursor,
        order=filters.order,
    )
    fingerprint = _filter_fingerprint(normalized_filters)
    order_null = case((Task.due_at.is_(None), 1), else_=0)

    async with storage.session() as db:
        async with db.begin():
            await _materialize_active_series(db, user_id, _utc_now())
        stmt = select(Task).where(Task.user_id == user_id, Task.deleted_at.is_(None))
        if normalized_filters.statuses:
            stmt = stmt.where(
                Task.status.in_([status.value for status in normalized_filters.statuses])
            )
        if normalized_filters.priorities:
            stmt = stmt.where(
                Task.priority.in_([priority.value for priority in normalized_filters.priorities])
            )
        if normalized_filters.search is not None:
            search_pattern = f"%{normalized_filters.search}%"
            tag_search = (
                select(TaskTag.task_id)
                .join(Tag, Tag.id == TaskTag.tag_id)
                .where(
                    TaskTag.task_id == Task.id,
                    Tag.user_id == user_id,
                    func.lower(Tag.name).like(search_pattern),
                )
                .exists()
            )
            stmt = stmt.where(
                or_(
                    func.lower(Task.title).like(search_pattern),
                    func.lower(func.coalesce(Task.description, "")).like(search_pattern),
                    tag_search,
                )
            )
        if normalized_filters.due_from is not None:
            stmt = stmt.where(Task.due_at >= normalized_filters.due_from)
        if normalized_filters.due_to is not None:
            stmt = stmt.where(Task.due_at < normalized_filters.due_to)
        if (
            normalized_filters.scheduled_from is not None
            or normalized_filters.scheduled_to is not None
        ):
            scheduled_start = func.coalesce(Task.start_at, Task.due_at)
            scheduled_end = func.coalesce(Task.due_at, Task.start_at)
            if normalized_filters.scheduled_from is not None:
                stmt = stmt.where(scheduled_end >= normalized_filters.scheduled_from)
            if normalized_filters.scheduled_to is not None:
                stmt = stmt.where(scheduled_start < normalized_filters.scheduled_to)
        for tag_name in normalized_filters.tags:
            stmt = stmt.where(
                select(TaskTag.task_id)
                .join(Tag, Tag.id == TaskTag.tag_id)
                .where(
                    TaskTag.task_id == Task.id,
                    Tag.user_id == user_id,
                    Tag.name == tag_name,
                )
                .exists()
            )

        if normalized_filters.order == TaskListOrder.BOARD:
            status_rank = _status_rank_expression()
            if normalized_filters.cursor:
                cursor_status, cursor_position, cursor_created, cursor_id = _decode_board_cursor(
                    normalized_filters.cursor,
                    fingerprint,
                )
                cursor_rank = {status.value: index for index, status in enumerate(TaskStatus)}[
                    cursor_status
                ]
                stmt = stmt.where(
                    or_(
                        status_rank > cursor_rank,
                        and_(
                            status_rank == cursor_rank,
                            Task.position > cursor_position,
                        ),
                        and_(
                            status_rank == cursor_rank,
                            Task.position == cursor_position,
                            Task.created_at < cursor_created,
                        ),
                        and_(
                            status_rank == cursor_rank,
                            Task.position == cursor_position,
                            Task.created_at == cursor_created,
                            Task.id > cursor_id,
                        ),
                    )
                )
            stmt = stmt.order_by(
                status_rank.asc(),
                Task.position.asc(),
                Task.created_at.desc(),
                Task.id.asc(),
            )
        else:
            if normalized_filters.cursor:
                cursor_due, cursor_created, cursor_id = _decode_cursor(
                    normalized_filters.cursor,
                    fingerprint,
                )
                if cursor_due is None:
                    stmt = stmt.where(
                        or_(
                            and_(
                                order_null == 1,
                                Task.created_at < cursor_created,
                            ),
                            and_(
                                order_null == 1,
                                Task.created_at == cursor_created,
                                Task.id > cursor_id,
                            ),
                        )
                    )
                else:
                    stmt = stmt.where(
                        or_(
                            order_null > 0,
                            and_(
                                order_null == 0,
                                Task.due_at > cursor_due,
                            ),
                            and_(
                                order_null == 0,
                                Task.due_at == cursor_due,
                                Task.created_at < cursor_created,
                            ),
                            and_(
                                order_null == 0,
                                Task.due_at == cursor_due,
                                Task.created_at == cursor_created,
                                Task.id > cursor_id,
                            ),
                        )
                    )

            stmt = stmt.order_by(
                order_null.asc(),
                Task.due_at.asc(),
                Task.created_at.desc(),
                Task.id.asc(),
            )
        rows = list((await db.scalars(stmt.limit(normalized_filters.limit + 1))).all())
        page_rows = rows[: normalized_filters.limit]
        tags = await _tags_for_tasks(db, [task.id for task in page_rows])
        if len(rows) > normalized_filters.limit:
            next_cursor = (
                _encode_board_cursor(page_rows[-1], fingerprint)
                if normalized_filters.order == TaskListOrder.BOARD
                else _encode_cursor(page_rows[-1], fingerprint)
            )
        else:
            next_cursor = None
        return TaskPage(
            items=[_record(task, tags.get(task.id, [])) for task in page_rows],
            next_cursor=next_cursor,
        )


def _summary_day_bounds(timezone_name: str) -> tuple[datetime, datetime, datetime]:
    try:
        timezone = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        raise InvalidTaskSummaryTimezoneError() from None

    now = _utc_now()
    local_now = now.astimezone(timezone)
    today_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow_start = today_start + timedelta(days=1)
    return (
        now,
        today_start.astimezone(UTC),
        tomorrow_start.astimezone(UTC),
    )


async def summarize_tasks(
    storage: DatabaseStorage,
    user_id: str,
    timezone_name: str,
) -> TaskSummaryRecord:
    """Return global task-view counts and the user's populated tags."""

    now, today_start, tomorrow_start = _summary_day_bounds(timezone_name)
    active_statuses = [
        TaskStatus.BACKLOG.value,
        TaskStatus.TODO.value,
        TaskStatus.IN_PROGRESS.value,
    ]

    async with storage.session() as db:
        async with db.begin():
            await _materialize_active_series(db, user_id, now)
        base = select(func.count(Task.id)).where(
            Task.user_id == user_id,
            Task.deleted_at.is_(None),
        )

        async def count_tasks(*conditions: ColumnElement[bool]) -> int:
            result = await db.scalar(base.where(*conditions))
            return int(result or 0)

        today = await count_tasks(
            Task.status.in_(active_statuses),
            Task.due_at >= today_start,
            Task.due_at < tomorrow_start,
        )
        upcoming = await count_tasks(
            Task.status.in_(active_statuses),
            Task.due_at >= tomorrow_start,
        )
        overdue = await count_tasks(
            Task.status.in_(active_statuses),
            Task.due_at < now,
        )
        high_priority = await count_tasks(
            Task.status.in_(active_statuses),
            Task.priority == TaskPriority.HIGH.value,
        )

        tag_rows = await db.execute(
            select(Tag.name, Tag.color, Tag.archived_at, func.count(TaskTag.task_id))
            .join(TaskTag, TaskTag.tag_id == Tag.id)
            .join(
                Task,
                and_(
                    Task.id == TaskTag.task_id,
                    Task.user_id == user_id,
                    Task.deleted_at.is_(None),
                ),
            )
            .where(Tag.user_id == user_id)
            .group_by(Tag.name, Tag.color, Tag.archived_at)
            .order_by(Tag.name.asc())
        )
        tags = [
            TaskTagSummaryRecord(
                name=name,
                count=int(count),
                color=TagColor(color),
                active=archived_at is None,
            )
            for name, color, archived_at, count in tag_rows.all()
        ]

        return TaskSummaryRecord(
            all=await db.scalar(base) or 0,
            today=today,
            upcoming=upcoming,
            overdue=overdue,
            high_priority=high_priority,
            tags=tags,
        )


async def update_task(
    storage: DatabaseStorage,
    user_id: str,
    task_id: str,
    payload: TaskUpdateRequest,
) -> TaskRecord:
    """Apply a partial update and optionally replace tag membership."""

    async with storage.session() as db:
        async with db.begin():
            task = await _get_task_row(db, user_id, task_id)
            values = payload.model_dump(exclude_unset=True)
            if values and task.series_id is not None:
                task.series_exception = True
            start_at = values.get("start_at", _as_utc(task.start_at))
            due_at = values.get("due_at", _as_utc(task.due_at))
            if "start_at" in values:
                start_at = _normalized_input_datetime(start_at)
            if "due_at" in values:
                due_at = _normalized_input_datetime(due_at)
            _validate_date_range(start_at, due_at)

            for field in ("title", "description", "start_at", "due_at"):
                if field in values:
                    value = values[field]
                    if field in {"start_at", "due_at"}:
                        value = _normalized_input_datetime(value)
                    setattr(task, field, value)
            if "status" in values:
                if values["status"] is None:
                    raise ValueError("status cannot be null")
                await _move_to_column_end(db, task, values["status"].value)
            if "priority" in values:
                if values["priority"] is None:
                    raise ValueError("priority cannot be null")
                task.priority = values["priority"].value
            if "tags" in values:
                await _replace_tags(db, task.id, user_id, values["tags"])
            task.updated_at = _utc_now()
            await db.flush()
            tags = await _tags_for_tasks(db, [task.id])
            return _record(task, tags.get(task.id, []))


async def reorder_task(
    storage: DatabaseStorage,
    user_id: str,
    task_id: str,
    payload: TaskReorderRequest,
) -> TaskRecord:
    """Move a task to a status column and place it before an optional sibling."""

    async with storage.session() as db:
        async with db.begin():
            task = await _get_task_row(db, user_id, task_id)
            target_status = payload.status.value

            if task.series_id is not None:
                task.series_exception = True

            if payload.before_task_id == task.id:
                raise InvalidTaskReorderError()

            await _remove_from_column(db, task)

            before_task = None
            if payload.before_task_id is not None:
                before_task = await _get_task_row(db, user_id, payload.before_task_id)
                if before_task.status != target_status:
                    raise InvalidTaskReorderError()

            if before_task is None:
                position = await _next_position(db, user_id, target_status)
            else:
                position = before_task.position
                await db.execute(
                    update(Task)
                    .where(
                        Task.user_id == user_id,
                        Task.status == target_status,
                        Task.deleted_at.is_(None),
                        Task.position >= position,
                    )
                    .values(position=Task.position + 1)
                )

            task.status = target_status
            task.position = position
            task.updated_at = _utc_now()
            await db.flush()
            tags = await _tags_for_tasks(db, [task.id])
            return _record(task, tags.get(task.id, []))


async def delete_task(storage: DatabaseStorage, user_id: str, task_id: str) -> None:
    """Soft-delete one owner-scoped task."""

    async with storage.session() as db:
        async with db.begin():
            task = await _get_task_row(db, user_id, task_id)
            now = _utc_now()
            task.deleted_at = now
            task.updated_at = now
            if task.series_id is not None:
                task.series_exception = True
            await db.flush()
            await db.execute(
                update(Task)
                .where(
                    Task.user_id == user_id,
                    Task.status == task.status,
                    Task.deleted_at.is_(None),
                    Task.position > task.position,
                )
                .values(position=Task.position - 1)
            )


async def get_task_series(
    storage: DatabaseStorage,
    user_id: str,
    series_id: str,
) -> TaskSeriesRecord:
    """Return one owner-scoped recurrence series."""

    async with storage.session() as db:
        series = await _get_series_row(db, user_id, series_id)
        tags = await _series_tags_for_series(db, series.id)
        return _series_record(series, tags)


async def list_task_series(
    storage: DatabaseStorage,
    user_id: str,
    limit: int = 50,
) -> TaskSeriesPage:
    """Return a bounded list of owner-scoped recurrence series."""

    if not 1 <= limit <= 100:
        raise InvalidTaskQueryError()
    async with storage.session() as db:
        async with db.begin():
            await _materialize_active_series(db, user_id, _utc_now())
        series_rows = list(
            (
                await db.scalars(
                    select(TaskSeries)
                    .where(TaskSeries.user_id == user_id)
                    .order_by(TaskSeries.updated_at.desc(), TaskSeries.id.asc())
                    .limit(limit)
                )
            ).all()
        )
        return TaskSeriesPage(
            items=[
                _series_record(series, await _series_tags_for_series(db, series.id))
                for series in series_rows
            ]
        )


async def _future_series_tasks(
    db: AsyncSession,
    series_id: str,
    now: datetime,
) -> list[Task]:
    return list(
        (
            await db.scalars(
                select(Task).where(
                    Task.series_id == series_id,
                    Task.deleted_at.is_(None),
                    Task.series_exception.is_(False),
                    or_(Task.due_at >= now, Task.start_at >= now),
                )
            )
        ).all()
    )


async def _apply_series_template(
    db: AsyncSession,
    series: TaskSeries,
    tasks: list[Task],
    tag_names: tuple[str, ...],
    now: datetime,
) -> None:
    for task in tasks:
        if task.status != series.status:
            await _move_to_column_end(db, task, series.status)
        task.title = series.title
        task.description = series.description
        task.priority = series.priority
        task.updated_at = now
        await _replace_tags(db, task.id, series.user_id, list(tag_names))


async def update_task_series(
    storage: DatabaseStorage,
    user_id: str,
    series_id: str,
    payload: TaskSeriesUpdateRequest,
) -> TaskSeriesRecord:
    """Update a series template or rule and preserve occurrence exceptions."""

    async with storage.session() as db:
        async with db.begin():
            series = await _get_series_row(db, user_id, series_id)
            if series.state == "ended":
                raise InvalidTaskSeriesStateError()
            now = _utc_now()
            existing_tags = tuple(await _series_tags_for_series(db, series.id))
            values = payload.model_dump(exclude_unset=True)
            recurrence_changed = "recurrence" in values and payload.recurrence is not None

            if payload.title is not None:
                series.title = payload.title
            if "description" in values:
                series.description = payload.description
            if payload.status is not None:
                series.status = payload.status.value
            if payload.priority is not None:
                series.priority = payload.priority.value
            tag_names = existing_tags
            if "tags" in values and payload.tags is not None:
                tag_names = normalize_tag_names(payload.tags)
                await _replace_series_tags(db, series.id, user_id, list(tag_names))

            future_tasks = await _future_series_tasks(db, series.id, now)
            if recurrence_changed:
                assert payload.recurrence is not None
                timezone_name, rule = split_recurrence(payload.recurrence)
                timezone_or_error(timezone_name)
                _validate_recurrence_schedule(
                    payload.recurrence,
                    _required_utc(series.anchor_at),
                )
                series.timezone = timezone_name
                series.rule = rule
                series.until_date = payload.recurrence.until_date
                series.occurrence_count = payload.recurrence.occurrence_count
                replacement_occurrences = {
                    occurrence.key: occurrence
                    for occurrence in iter_occurrences(
                        series.anchor_at,
                        timezone_name,
                        rule,
                        after_at=now - timedelta(seconds=1),
                        through_at=now + timedelta(days=HORIZON_DAYS),
                        limit=MAX_OCCURRENCES_PER_MATERIALIZATION,
                    )
                }
                applicable_tasks: list[Task] = []
                for task in future_tasks:
                    occurrence_key = task.occurrence_key
                    occurrence = (
                        replacement_occurrences.get(occurrence_key)
                        if occurrence_key is not None
                        else None
                    )
                    if occurrence is None:
                        task.series_id = None
                        task.occurrence_key = None
                        task.series_exception = False
                        continue
                    task.start_at, task.due_at = _occurrence_window(series, occurrence.utc_at)
                    applicable_tasks.append(task)
                future_tasks = applicable_tasks
                series.materialized_through_at = None

            await _apply_series_template(db, series, future_tasks, tag_names, now)
            series.updated_at = now
            if series.state == "active":
                await _materialize_series(db, series, now)
            await db.flush()
            return _series_record(series, list(tag_names))


async def _transition_series(
    storage: DatabaseStorage,
    user_id: str,
    series_id: str,
    target_state: str,
) -> TaskSeriesRecord:
    async with storage.session() as db:
        async with db.begin():
            series = await _get_series_row(db, user_id, series_id)
            allowed = {
                "paused": {"active"},
                "active": {"paused"},
                "ended": {"active", "paused"},
            }
            if target_state not in allowed or series.state not in allowed[target_state]:
                raise InvalidTaskSeriesStateError()
            now = _utc_now()
            series.state = target_state
            series.updated_at = now
            if target_state == "paused":
                series.paused_at = now
            elif target_state == "ended":
                series.ended_at = now
            elif target_state == "active":
                series.paused_at = None
                await _materialize_series(db, series, now)
            await db.flush()
            return _series_record(series, await _series_tags_for_series(db, series.id))


async def pause_task_series(
    storage: DatabaseStorage, user_id: str, series_id: str
) -> TaskSeriesRecord:
    """Pause future generation while leaving existing occurrences intact."""

    return await _transition_series(storage, user_id, series_id, "paused")


async def resume_task_series(
    storage: DatabaseStorage, user_id: str, series_id: str
) -> TaskSeriesRecord:
    """Resume generation for a paused series."""

    return await _transition_series(storage, user_id, series_id, "active")


async def end_task_series(
    storage: DatabaseStorage, user_id: str, series_id: str
) -> TaskSeriesRecord:
    """End future generation while preserving materialized occurrences."""

    return await _transition_series(storage, user_id, series_id, "ended")


async def skip_task_occurrence(
    storage: DatabaseStorage,
    user_id: str,
    task_id: str,
) -> TaskRecord:
    """Cancel and retain one recurring occurrence as an explicit skip."""

    async with storage.session() as db:
        async with db.begin():
            task = await _get_task_row(db, user_id, task_id)
            if task.series_id is None:
                raise TaskOccurrenceRequiredError()
            await _move_to_column_end(db, task, TaskStatus.CANCELED.value)
            now = _utc_now()
            task.status = TaskStatus.CANCELED.value
            task.skipped_at = now
            task.series_exception = True
            task.updated_at = now
            await db.flush()
            tags = await _tags_for_tasks(db, [task.id])
            return _record(task, tags.get(task.id, []))
