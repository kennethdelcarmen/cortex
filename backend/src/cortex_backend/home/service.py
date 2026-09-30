"""Authenticated Home dashboard read model orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..logs.service import ActivityLogFilters, ActivityLogRecord, list_logs
from ..memory.content import html_to_text
from ..memory.service import NoteListFilters, NoteRecord, count_notes, list_notes
from ..money.service import (
    MoneySummaryRecord,
    TransactionListFilters,
    TransactionRecord,
    get_money_summary,
    list_transactions,
)
from ..storage import DatabaseStorage
from ..tasks.schemas import TaskListOrder, TaskPriority, TaskStatus
from ..tasks.service import TaskListFilters, TaskRecord, list_tasks, summarize_tasks

HOME_TASK_LIMIT = 8
HOME_NOTE_LIMIT = 3
HOME_MOVEMENT_LIMIT = 4
HOME_ACTIVITY_LIMIT = 6
ACTIVE_TASK_STATUSES = (
    TaskStatus.BACKLOG,
    TaskStatus.TODO,
    TaskStatus.IN_PROGRESS,
)


@dataclass(frozen=True)
class HomeTaskItem:
    id: str
    title: str
    status: TaskStatus
    priority: TaskPriority
    start_at: datetime | None
    due_at: datetime | None
    overdue: bool


@dataclass(frozen=True)
class HomeNoteItem:
    id: str
    title: str | None
    journal_date: date | None
    updated_at: datetime
    preview: str


@dataclass(frozen=True)
class HomeMovement:
    id: str
    transaction_date: date
    name: str
    direction: str
    amount: str
    currency_code: str


@dataclass(frozen=True)
class HomeSummaryRecord:
    period: str
    currency_code: str
    task_counts: dict[str, int]
    tasks: list[HomeTaskItem]
    note_count: int
    notes: list[HomeNoteItem]
    money: MoneySummaryRecord
    movements: list[HomeMovement]
    activity: list[ActivityLogRecord]


def _period_bounds(period: str) -> tuple[date, date]:
    year, month = (int(part) for part in period.split("-"))
    start = date(year, month, 1)
    next_month = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
    return start, next_month - timedelta(days=1)


def _day_bounds(timezone_name: str) -> tuple[datetime, datetime, datetime]:
    try:
        timezone = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError("Invalid timezone.") from None
    now = datetime.now(UTC)
    local_now = now.astimezone(timezone)
    today_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow_start = today_start + timedelta(days=1)
    return now, today_start.astimezone(UTC), tomorrow_start.astimezone(UTC)


def _task_item(task: TaskRecord, now: datetime) -> HomeTaskItem:
    return HomeTaskItem(
        id=task.id,
        title=task.title,
        status=task.status,
        priority=task.priority,
        start_at=task.start_at,
        due_at=task.due_at,
        overdue=task.due_at is not None and task.due_at < now,
    )


def _note_item(note: NoteRecord) -> HomeNoteItem:
    preview = html_to_text(note.body)
    if len(preview) > 180:
        preview = f"{preview[:177].rstrip()}…"
    return HomeNoteItem(
        id=note.id,
        title=note.title,
        journal_date=note.journal_date,
        updated_at=note.updated_at,
        preview=preview,
    )


def _movement(transaction: TransactionRecord) -> HomeMovement:
    category_postings = [posting for posting in transaction.postings if posting.category_id]
    account_postings = [posting for posting in transaction.postings if posting.account_id]
    currency_code = transaction.postings[0].currency_code if transaction.postings else "PHP"

    if category_postings:
        category_amount = sum(
            (Decimal(posting.amount) for posting in category_postings),
            Decimal(0),
        )
        direction = "expense" if category_amount > 0 else "income"
        amount = abs(category_amount)
    else:
        account_amount = sum((Decimal(posting.amount) for posting in account_postings), Decimal(0))
        direction = "transfer"
        amount = abs(account_amount) if account_amount else abs(Decimal(account_postings[0].amount))

    return HomeMovement(
        id=transaction.id,
        transaction_date=transaction.transaction_date,
        name=transaction.name,
        direction=direction,
        amount=format(amount, "f"),
        currency_code=currency_code,
    )


async def get_home_summary(
    storage: DatabaseStorage,
    user_id: str,
    timezone_name: str,
    period: str,
    currency_code: str,
) -> HomeSummaryRecord:
    """Build the Home read model from existing domain use cases."""

    now, _today_start, tomorrow_start = _day_bounds(timezone_name)
    period_start, period_end = _period_bounds(period)
    task_summary = await summarize_tasks(storage, user_id, timezone_name)
    task_page = await list_tasks(
        storage,
        user_id,
        TaskListFilters(
            statuses=ACTIVE_TASK_STATUSES,
            due_to=tomorrow_start,
            limit=HOME_TASK_LIMIT * 3,
            order=TaskListOrder.DUE,
        ),
    )
    tasks = [_task_item(task, now) for task in task_page.items]
    tasks.sort(key=lambda item: (not item.overdue, item.due_at is None, item.due_at or now))

    note_count, note_page = await _notes(storage, user_id)
    money = await get_money_summary(storage, user_id, period, currency_code)
    transaction_page = await list_transactions(
        storage,
        user_id,
        TransactionListFilters(
            date_from=period_start,
            date_to=period_end,
            currency_code=currency_code,
            limit=HOME_MOVEMENT_LIMIT,
        ),
    )
    activity_page = await list_logs(
        storage,
        user_id,
        ActivityLogFilters(limit=HOME_ACTIVITY_LIMIT),
    )

    return HomeSummaryRecord(
        period=period,
        currency_code=currency_code,
        task_counts={
            "today": task_summary.today,
            "upcoming": task_summary.upcoming,
            "overdue": task_summary.overdue,
            "high_priority": task_summary.high_priority,
        },
        tasks=tasks[:HOME_TASK_LIMIT],
        note_count=note_count,
        notes=[_note_item(note) for note in note_page],
        money=money,
        movements=[_movement(transaction) for transaction in transaction_page.items],
        activity=activity_page.items,
    )


async def _notes(storage: DatabaseStorage, user_id: str) -> tuple[int, list[NoteRecord]]:
    count = await count_notes(storage, user_id)
    page = await list_notes(storage, user_id, NoteListFilters(limit=HOME_NOTE_LIMIT))
    return count, page.items
