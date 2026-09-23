"""Protocol and domain schemas for task operations."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator, model_validator

from ..tags.schemas import TagColor


class TaskStatus(StrEnum):
    BACKLOG = "backlog"
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    CANCELED = "canceled"


class TaskPriority(StrEnum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class TaskListOrder(StrEnum):
    DUE = "due"
    BOARD = "board"


class RecurrenceFrequency(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"


class RecurrenceState(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    ENDED = "ended"


class RecurrenceWeekday(StrEnum):
    MONDAY = "monday"
    TUESDAY = "tuesday"
    WEDNESDAY = "wednesday"
    THURSDAY = "thursday"
    FRIDAY = "friday"
    SATURDAY = "saturday"
    SUNDAY = "sunday"


def _validate_aware_datetime(value: datetime | None) -> datetime | None:
    if value is not None and value.utcoffset() is None:
        raise ValueError("datetime must include a timezone")
    return value


def _validate_tag_names(value: list[str] | None) -> list[str] | None:
    if value is None:
        return None
    if len(value) > 20:
        raise ValueError("at most 20 tags are allowed")
    for tag in value:
        normalized = tag.strip()
        if not normalized or len(normalized) > 64:
            raise ValueError("tags must be non-empty and at most 64 characters")
    return [tag.strip() for tag in value]


class TaskRecurrenceRequest(BaseModel):
    """A bounded calendar recurrence definition."""

    timezone: str = Field(min_length=1, max_length=64)
    frequency: RecurrenceFrequency
    interval: int = Field(default=1, ge=1, le=365)
    weekdays: list[RecurrenceWeekday] = Field(default_factory=list, max_length=7)
    month_day: int | None = Field(default=None, ge=1, le=31)
    month: int | None = Field(default=None, ge=1, le=12)
    day: int | None = Field(default=None, ge=1, le=31)
    until_date: date | None = None
    occurrence_count: int | None = Field(default=None, ge=1, le=100_000)

    @field_validator("timezone")
    @classmethod
    def timezone_must_have_content(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def validate_selectors(self) -> TaskRecurrenceRequest:
        if len(set(self.weekdays)) != len(self.weekdays):
            raise ValueError("weekly recurrence weekdays must be unique")
        if self.frequency == RecurrenceFrequency.WEEKLY and not self.weekdays:
            raise ValueError("weekly recurrence requires at least one weekday")
        if self.frequency != RecurrenceFrequency.WEEKLY and self.weekdays:
            raise ValueError("weekdays are only valid for weekly recurrence")
        if self.frequency != RecurrenceFrequency.MONTHLY and self.month_day is not None:
            raise ValueError("month_day is only valid for monthly recurrence")
        if self.frequency != RecurrenceFrequency.YEARLY and (
            self.month is not None or self.day is not None
        ):
            raise ValueError("month and day are only valid for yearly recurrence")
        if (self.month is None) != (self.day is None):
            raise ValueError("yearly recurrence requires both month and day")
        if self.until_date is not None and self.occurrence_count is not None:
            raise ValueError("until_date and occurrence_count cannot both be set")
        return self


class TaskCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=10_000)
    status: TaskStatus = TaskStatus.BACKLOG
    priority: TaskPriority = TaskPriority.NONE
    start_at: datetime | None = None
    due_at: datetime | None = None
    tags: list[str] = Field(default_factory=list, max_length=20)
    recurrence: TaskRecurrenceRequest | None = None

    @field_validator("title")
    @classmethod
    def title_must_have_content(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("title must have content")
        return value

    _validate_start_at = field_validator("start_at")(_validate_aware_datetime)
    _validate_due_at = field_validator("due_at")(_validate_aware_datetime)
    _validate_tags = field_validator("tags")(_validate_tag_names)


class TaskUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=10_000)
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    start_at: datetime | None = None
    due_at: datetime | None = None
    tags: list[str] | None = Field(default=None, max_length=20)

    @field_validator("title")
    @classmethod
    def title_must_have_content(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("title must have content")
        return value

    _validate_start_at = field_validator("start_at")(_validate_aware_datetime)
    _validate_due_at = field_validator("due_at")(_validate_aware_datetime)
    _validate_tags = field_validator("tags")(_validate_tag_names)

    @field_validator("status", "priority", mode="before")
    @classmethod
    def enum_fields_cannot_be_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("status and priority cannot be null")
        return value


class TaskReorderRequest(BaseModel):
    status: TaskStatus
    before_task_id: str | None = None


class TaskResponse(BaseModel):
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


class TaskSeriesUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=10_000)
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    tags: list[str] | None = Field(default=None, max_length=20)
    recurrence: TaskRecurrenceRequest | None = None

    @field_validator("title")
    @classmethod
    def title_must_have_content(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("title must have content")
        return value

    _validate_tags = field_validator("tags")(_validate_tag_names)


class TaskSeriesResponse(BaseModel):
    id: str
    state: RecurrenceState
    title: str
    description: str | None
    status: TaskStatus
    priority: TaskPriority
    tags: list[str]
    recurrence: TaskRecurrenceRequest
    materialized_through_at: datetime | None
    created_at: datetime
    updated_at: datetime


class TaskSeriesListResponse(BaseModel):
    items: list[TaskSeriesResponse]


class TaskListResponse(BaseModel):
    items: list[TaskResponse]
    next_cursor: str | None


class TaskTagSummaryResponse(BaseModel):
    name: str
    count: int = Field(ge=0)
    color: TagColor
    active: bool


class TaskSummaryResponse(BaseModel):
    all: int = Field(ge=0)
    today: int = Field(ge=0)
    upcoming: int = Field(ge=0)
    overdue: int = Field(ge=0)
    high_priority: int = Field(ge=0)
    tags: list[TaskTagSummaryResponse]
