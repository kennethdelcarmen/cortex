"""Protocol and domain schemas for task operations."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


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


class TaskCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=10_000)
    status: TaskStatus = TaskStatus.BACKLOG
    priority: TaskPriority = TaskPriority.NONE
    start_at: datetime | None = None
    due_at: datetime | None = None
    tags: list[str] = Field(default_factory=list, max_length=20)

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


class TaskListResponse(BaseModel):
    items: list[TaskResponse]
    next_cursor: str | None
