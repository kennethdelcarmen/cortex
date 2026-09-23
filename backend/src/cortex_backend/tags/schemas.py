"""Protocol contracts for the shared tag catalog."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


class TagColor(StrEnum):
    ROSE = "rose"
    SEA_GLASS = "sea-glass"
    AMBER = "amber"
    SLATE = "slate"
    PLUM = "plum"
    VIOLET = "violet"
    SAND = "sand"
    DESTRUCTIVE = "destructive"


def _normalize_name(value: str) -> str:
    normalized = value.strip().casefold()
    if not normalized or len(normalized) > 64:
        raise ValueError("Tag names must be non-empty and at most 64 characters.")
    return normalized


class TagCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    color: TagColor = TagColor.SLATE

    _normalize_name = field_validator("name")(_normalize_name)


class TagUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    color: TagColor | None = None

    _normalize_name = field_validator("name")(_normalize_name)


class TagResponse(BaseModel):
    id: str
    name: str
    color: TagColor
    active: bool
    created_at: datetime
    archived_at: datetime | None


class TagListResponse(BaseModel):
    items: list[TagResponse]
