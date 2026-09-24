"""Protocol contracts for file operations."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class FileRenameRequest(BaseModel):
    """Validated metadata-only file rename."""

    name: str = Field(min_length=1, max_length=255)

    @field_validator("name")
    @classmethod
    def name_must_have_content(cls, value: str) -> str:
        return value.strip()


class FileResponse(BaseModel):
    """Transport response for one owner-scoped file."""

    id: str
    name: str
    media_type: str
    size_bytes: int = Field(ge=0)
    sha256: str
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


class FileListResponse(BaseModel):
    """Transport response for a bounded file listing."""

    items: list[FileResponse]
    next_cursor: str | None
