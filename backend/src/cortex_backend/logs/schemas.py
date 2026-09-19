"""Typed contracts for activity-log operations."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

MAX_METADATA_BYTES = 16 * 1024


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        raise ValueError("value must contain content")
    return normalized


class ActivityLogCreateRequest(BaseModel):
    """Validated input for appending one activity record."""

    event_type: str = Field(min_length=1, max_length=64)
    entity_type: str | None = Field(default=None, max_length=64)
    entity_id: str | None = Field(default=None, max_length=128)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("event_type", "entity_type", "entity_id")
    @classmethod
    def text_must_contain_content(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = _normalize_optional_text(value)
        assert normalized is not None
        return normalized

    @field_validator("metadata")
    @classmethod
    def metadata_must_be_bounded_json(cls, value: dict[str, Any]) -> dict[str, Any]:
        try:
            serialized = json.dumps(
                value,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
            )
        except (TypeError, ValueError):
            raise ValueError("metadata must contain JSON-compatible values") from None
        if len(serialized.encode("utf-8")) > MAX_METADATA_BYTES:
            raise ValueError(f"metadata must be at most {MAX_METADATA_BYTES} bytes")
        return value


class ActivityLogResponse(BaseModel):
    """Transport response for one owner-scoped activity record."""

    id: str
    user_id: str
    event_type: str
    entity_type: str | None
    entity_id: str | None
    metadata: dict[str, Any]
    created_at: datetime


class ActivityLogListResponse(BaseModel):
    """Transport response for a paginated activity history query."""

    items: list[ActivityLogResponse]
    next_cursor: str | None
