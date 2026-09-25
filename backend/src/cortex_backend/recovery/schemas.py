"""Protocol contracts for cross-domain recovery operations."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class RecoveryItemType(StrEnum):
    TASK = "task"
    NOTE = "note"
    FILE = "file"
    TAG = "tag"


class RecoveryMutationStatus(StrEnum):
    RESTORED = "restored"
    PERMANENTLY_DELETED = "permanently_deleted"
    FAILED = "failed"


class RecoveryItemReference(BaseModel):
    """Owner-scoped reference to one recoverable domain record."""

    type: RecoveryItemType
    id: str = Field(min_length=1, max_length=64)


class RecoveryItemResponse(BaseModel):
    """Summary metadata for one recoverable record."""

    type: RecoveryItemType
    id: str
    label: str
    removed_at: datetime
    created_at: datetime


class RecoveryListResponse(BaseModel):
    """A bounded, cursor-paginated recovery feed."""

    items: list[RecoveryItemResponse]
    next_cursor: str | None


class RecoveryBatchRequest(BaseModel):
    """One or more recovery references to mutate."""

    items: list[RecoveryItemReference] = Field(min_length=1, max_length=100)


class RecoveryErrorResponse(BaseModel):
    """Stable error information for one failed bulk item."""

    code: str
    message: str


class RecoveryMutationResult(BaseModel):
    """Outcome for one requested recovery mutation."""

    item: RecoveryItemReference
    status: RecoveryMutationStatus
    error: RecoveryErrorResponse | None = None


class RecoveryMutationResponse(BaseModel):
    """Independent outcomes for a recovery mutation batch."""

    results: list[RecoveryMutationResult]
