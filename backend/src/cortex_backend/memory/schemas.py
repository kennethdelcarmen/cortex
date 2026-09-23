"""Typed contracts for note operations."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator

from ..tags.schemas import TagColor
from .content import normalize_note_body


def _validate_optional_title(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        raise ValueError("title must contain content when provided")
    return normalized


def _validate_body(value: str | None) -> str | None:
    if value is None:
        return None
    return normalize_note_body(value)


class NoteCreateRequest(BaseModel):
    """Validated input for creating one canonical HTML note."""

    title: str | None = Field(default=None, max_length=200)
    body: str = Field(
        min_length=1,
        description="Note content as HTML; legacy Markdown input is normalized before storage.",
    )
    journal_date: date | None = None
    tags: list[str] = Field(default_factory=list, max_length=20)

    _validate_title = field_validator("title")(_validate_optional_title)
    _validate_note_body = field_validator("body")(_validate_body)


class NoteUpdateRequest(BaseModel):
    """Validated partial input for updating one canonical HTML note."""

    title: str | None = Field(default=None, max_length=200)
    body: str | None = Field(
        default=None,
        description="Note content as HTML; legacy Markdown input is normalized before storage.",
    )
    journal_date: date | None = None
    tags: list[str] | None = Field(default=None, max_length=20)

    _validate_title = field_validator("title")(_validate_optional_title)
    _validate_note_body = field_validator("body")(_validate_body)


class NoteResponse(BaseModel):
    """Transport response for one owner-scoped note."""

    id: str
    title: str | None
    body: str = Field(description="Sanitized canonical HTML note content.")
    journal_date: date | None
    tags: list[str]
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


class NoteListResponse(BaseModel):
    """Transport response for a paginated note query."""

    items: list[NoteResponse]
    next_cursor: str | None


class NoteTagSummaryResponse(BaseModel):
    """A normalized note tag and the number of active notes using it."""

    name: str
    count: int = Field(ge=0)
    color: TagColor
    active: bool


class NoteSummaryResponse(BaseModel):
    """Aggregate data used by the notes workspace."""

    tags: list[NoteTagSummaryResponse]
