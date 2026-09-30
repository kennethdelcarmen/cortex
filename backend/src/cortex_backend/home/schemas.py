"""Typed contracts for the authenticated Home dashboard."""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from ..tasks.schemas import TaskPriority, TaskStatus


class HomeTaskCounts(BaseModel):
    today: int = Field(ge=0)
    upcoming: int = Field(ge=0)
    overdue: int = Field(ge=0)
    high_priority: int = Field(ge=0)


class HomeTaskResponse(BaseModel):
    id: str
    title: str
    status: TaskStatus
    priority: TaskPriority
    start_at: datetime | None
    due_at: datetime | None
    overdue: bool


class HomeTasksResponse(BaseModel):
    counts: HomeTaskCounts
    items: list[HomeTaskResponse]


class HomeNoteResponse(BaseModel):
    id: str
    title: str | None
    journal_date: date | None
    updated_at: datetime
    preview: str


class HomeNotesResponse(BaseModel):
    count: int = Field(ge=0)
    items: list[HomeNoteResponse]


class HomeMoneyMovementResponse(BaseModel):
    id: str
    transaction_date: date
    name: str
    direction: str
    amount: str
    currency_code: str


class HomeMoneyResponse(BaseModel):
    period: str
    currency_code: str
    total_balance: str
    income_amount: str
    spending_amount: str
    budget_amount: str
    budget_spent_amount: str
    budget_remaining_amount: str
    movements: list[HomeMoneyMovementResponse]


class HomeActivityResponse(BaseModel):
    id: str
    user_id: str
    event_type: str
    entity_type: str | None
    entity_id: str | None
    metadata: dict[str, Any]
    created_at: datetime


class HomeSummaryResponse(BaseModel):
    period: str
    currency_code: str
    tasks: HomeTasksResponse
    notes: HomeNotesResponse
    money: HomeMoneyResponse
    activity: list[HomeActivityResponse]
