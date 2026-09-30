"""HTTP adapter for the authenticated Home dashboard read model."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth.service import CurrentAuth
from ..home.schemas import (
    HomeActivityResponse,
    HomeMoneyMovementResponse,
    HomeMoneyResponse,
    HomeNoteResponse,
    HomeNotesResponse,
    HomeSummaryResponse,
    HomeTaskCounts,
    HomeTaskResponse,
    HomeTasksResponse,
)
from ..home.service import get_home_summary
from ..logs.errors import ActivityLogError
from ..memory.errors import NoteError
from ..money.errors import MoneyError
from ..storage import DatabaseStorage
from ..tasks.errors import TaskError
from .dependencies import get_current_auth, get_database_storage

router = APIRouter(prefix="/api/v1/home", tags=["home"])


@router.get("/summary", response_model=HomeSummaryResponse)
async def home_summary_route(
    auth: Annotated[CurrentAuth, Depends(get_current_auth)],
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    timezone: Annotated[str, Query(min_length=1, max_length=64)] = "UTC",
    period: Annotated[str, Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")] = date.today().strftime(
        "%Y-%m"
    ),
    currency_code: Annotated[str, Query(min_length=3, max_length=3)] = "PHP",
) -> HomeSummaryResponse:
    """Return the bounded cross-domain read model for the authenticated owner."""

    try:
        summary = await get_home_summary(
            storage,
            auth.user.id,
            timezone,
            period,
            currency_code,
        )
    except (TaskError, NoteError, MoneyError, ActivityLogError, ValueError) as exc:
        if isinstance(exc, ValueError):
            raise HTTPException(
                status_code=422,
                detail={"code": "invalid_home_query", "message": str(exc)},
            ) from exc
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc

    return HomeSummaryResponse(
        period=summary.period,
        currency_code=summary.currency_code,
        tasks=HomeTasksResponse(
            counts=HomeTaskCounts(**summary.task_counts),
            items=[
                HomeTaskResponse(
                    id=task.id,
                    title=task.title,
                    status=task.status,
                    priority=task.priority,
                    start_at=task.start_at,
                    due_at=task.due_at,
                    overdue=task.overdue,
                )
                for task in summary.tasks
            ],
        ),
        notes=HomeNotesResponse(
            count=summary.note_count,
            items=[
                HomeNoteResponse(
                    id=note.id,
                    title=note.title,
                    journal_date=note.journal_date,
                    updated_at=note.updated_at,
                    preview=note.preview,
                )
                for note in summary.notes
            ],
        ),
        money=HomeMoneyResponse(
            period=summary.money.period,
            currency_code=summary.money.currency_code,
            total_balance=summary.money.total_balance,
            income_amount=summary.money.income_amount,
            spending_amount=summary.money.spending_amount,
            budget_amount=summary.money.budget_amount,
            budget_spent_amount=summary.money.budget_spent_amount,
            budget_remaining_amount=summary.money.budget_remaining_amount,
            movements=[
                HomeMoneyMovementResponse(
                    id=movement.id,
                    transaction_date=movement.transaction_date,
                    name=movement.name,
                    direction=movement.direction,
                    amount=movement.amount,
                    currency_code=movement.currency_code,
                )
                for movement in summary.movements
            ],
        ),
        activity=[
            HomeActivityResponse(
                id=log.id,
                user_id=log.user_id,
                event_type=log.event_type,
                entity_type=log.entity_type,
                entity_id=log.entity_id,
                metadata=log.metadata,
                created_at=log.created_at,
            )
            for log in summary.activity
        ],
    )
