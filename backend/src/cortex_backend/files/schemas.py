"""Protocol contracts for file operations."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

FileContextStatus = Literal["pending", "processing", "ready", "unsupported", "failed"]
FilePreviewKind = Literal["text", "pdf", "image"]


class FileResponse(BaseModel):
    """Transport response for one owner-scoped file."""

    id: str
    name: str
    size_bytes: int = Field(ge=0)
    sha256: str
    context_status: FileContextStatus
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


class FileListResponse(BaseModel):
    """Transport response for a bounded file listing."""

    items: list[FileResponse]
    next_cursor: str | None


class FileContextResponse(BaseModel):
    """Bounded derived context and preview state for one source file."""

    file_id: str
    name: str
    status: FileContextStatus
    text: str | None
    truncated: bool
    preview_kind: FilePreviewKind | None
    error: str | None
    processed_at: datetime | None
