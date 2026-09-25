"""Cross-domain recovery use cases over the shared database storage seam."""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, func, literal, or_, select, union_all

from ..files.errors import FileError, FileStorageUnavailableError
from ..files.models import File
from ..files.service import (
    permanently_delete_file,
    restore_file,
)
from ..files.storage import FileBlobStore
from ..memory.errors import NoteError
from ..memory.models import Note
from ..memory.service import permanently_delete_note, restore_note
from ..storage import DatabaseStorage
from ..tags.errors import TagError
from ..tags.service import permanently_delete_tag, restore_tag
from ..tasks.errors import TaskError
from ..tasks.models import Tag, Task
from ..tasks.service import permanently_delete_task, restore_task
from .errors import InvalidRecoveryCursorError, InvalidRecoveryQueryError
from .schemas import (
    RecoveryErrorResponse,
    RecoveryItemReference,
    RecoveryItemType,
    RecoveryMutationResult,
    RecoveryMutationStatus,
)

DEFAULT_RECOVERY_LIMIT = 50
MAX_RECOVERY_LIMIT = 100


@dataclass(frozen=True)
class RecoveryListFilters:
    """Filters for the bounded, newest-first recovery feed."""

    limit: int = DEFAULT_RECOVERY_LIMIT
    cursor: str | None = None


@dataclass(frozen=True)
class RecoveryItemRecord:
    """Transport-independent summary for one recoverable record."""

    type: RecoveryItemType
    id: str
    label: str
    removed_at: datetime
    created_at: datetime


@dataclass(frozen=True)
class RecoveryPage:
    """A bounded recovery page and an optional continuation cursor."""

    items: list[RecoveryItemRecord]
    next_cursor: str | None


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _encode_cursor(item: RecoveryItemRecord) -> str:
    payload = {
        "v": 1,
        "removed_at": _as_utc(item.removed_at).isoformat(),
        "type": item.type.value,
        "id": item.id,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, str, str]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
        removed_at = datetime.fromisoformat(payload["removed_at"])
        item_type = payload["type"]
        item_id = payload["id"]
        if (
            payload.get("v") != 1
            or removed_at.tzinfo is None
            or item_type not in {item_type.value for item_type in RecoveryItemType}
            or not isinstance(item_id, str)
            or not item_id
        ):
            raise ValueError
        return _as_utc(removed_at), item_type, item_id
    except (binascii.Error, ValueError, KeyError, TypeError, json.JSONDecodeError):
        raise InvalidRecoveryCursorError() from None


def _normalized_filters(filters: RecoveryListFilters) -> RecoveryListFilters:
    if not 1 <= filters.limit <= MAX_RECOVERY_LIMIT:
        raise InvalidRecoveryQueryError()
    return filters


def _recovery_query(user_id: str) -> Any:
    return union_all(
        select(
            Task.id.label("id"),
            literal(RecoveryItemType.TASK.value).label("type"),
            Task.title.label("label"),
            Task.deleted_at.label("removed_at"),
            Task.created_at.label("created_at"),
        ).where(Task.user_id == user_id, Task.deleted_at.is_not(None)),
        select(
            Note.id.label("id"),
            literal(RecoveryItemType.NOTE.value).label("type"),
            func.coalesce(Note.title, literal("Untitled note")).label("label"),
            Note.deleted_at.label("removed_at"),
            Note.created_at.label("created_at"),
        ).where(Note.user_id == user_id, Note.deleted_at.is_not(None)),
        select(
            File.id.label("id"),
            literal(RecoveryItemType.FILE.value).label("type"),
            File.original_name.label("label"),
            File.deleted_at.label("removed_at"),
            File.created_at.label("created_at"),
        ).where(File.user_id == user_id, File.deleted_at.is_not(None)),
        select(
            Tag.id.label("id"),
            literal(RecoveryItemType.TAG.value).label("type"),
            Tag.name.label("label"),
            Tag.archived_at.label("removed_at"),
            Tag.created_at.label("created_at"),
        ).where(Tag.user_id == user_id, Tag.archived_at.is_not(None)),
    ).subquery()


async def list_recovery_items(
    storage: DatabaseStorage,
    user_id: str,
    filters: RecoveryListFilters | None = None,
) -> RecoveryPage:
    """Return a unified, bounded page of deleted or archived records."""

    normalized = _normalized_filters(filters or RecoveryListFilters())
    recovery = _recovery_query(user_id)
    statement = select(
        recovery.c.id,
        recovery.c.type,
        recovery.c.label,
        recovery.c.removed_at,
        recovery.c.created_at,
    )
    if normalized.cursor:
        cursor_removed_at, cursor_type, cursor_id = _decode_cursor(normalized.cursor)
        statement = statement.where(
            or_(
                recovery.c.removed_at < cursor_removed_at,
                and_(
                    recovery.c.removed_at == cursor_removed_at,
                    recovery.c.type > cursor_type,
                ),
                and_(
                    recovery.c.removed_at == cursor_removed_at,
                    recovery.c.type == cursor_type,
                    recovery.c.id > cursor_id,
                ),
            )
        )
    statement = statement.order_by(
        recovery.c.removed_at.desc(),
        recovery.c.type.asc(),
        recovery.c.id.asc(),
    ).limit(normalized.limit + 1)

    async with storage.session() as db:
        rows = list((await db.execute(statement)).all())

    page_rows = rows[: normalized.limit]
    items = [
        RecoveryItemRecord(
            type=RecoveryItemType(row.type),
            id=row.id,
            label=row.label,
            removed_at=_as_utc(row.removed_at),
            created_at=_as_utc(row.created_at),
        )
        for row in page_rows
    ]
    next_cursor = _encode_cursor(items[-1]) if len(rows) > normalized.limit else None
    return RecoveryPage(items=items, next_cursor=next_cursor)


async def _restore_item(
    storage: DatabaseStorage,
    file_storage: FileBlobStore | None,
    user_id: str,
    item: RecoveryItemReference,
) -> None:
    del file_storage
    if item.type is RecoveryItemType.TASK:
        await restore_task(storage, user_id, item.id)
    elif item.type is RecoveryItemType.NOTE:
        await restore_note(storage, user_id, item.id)
    elif item.type is RecoveryItemType.FILE:
        await restore_file(storage, user_id, item.id)
    else:
        await restore_tag(storage, user_id, item.id)


async def _permanently_delete_item(
    storage: DatabaseStorage,
    file_storage: FileBlobStore | None,
    user_id: str,
    item: RecoveryItemReference,
) -> None:
    if item.type is RecoveryItemType.TASK:
        await permanently_delete_task(storage, user_id, item.id)
    elif item.type is RecoveryItemType.NOTE:
        await permanently_delete_note(storage, user_id, item.id)
    elif item.type is RecoveryItemType.FILE:
        if file_storage is None:
            raise FileStorageUnavailableError()
        await permanently_delete_file(storage, file_storage, user_id, item.id)
    else:
        await permanently_delete_tag(storage, user_id, item.id)


_EXPECTED_ITEM_ERRORS = (FileError, NoteError, TagError, TaskError)


async def mutate_recovery_items(
    storage: DatabaseStorage,
    file_storage: FileBlobStore | None,
    user_id: str,
    items: list[RecoveryItemReference],
    *,
    permanent: bool,
) -> list[RecoveryMutationResult]:
    """Mutate recovery records independently and preserve request order."""

    unique_items: list[RecoveryItemReference] = []
    seen: set[tuple[str, str]] = set()
    for item in items:
        key = (item.type.value, item.id)
        if key not in seen:
            seen.add(key)
            unique_items.append(item)

    outcomes: dict[tuple[str, str], RecoveryMutationResult] = {}
    for item in unique_items:
        try:
            if permanent:
                await _permanently_delete_item(storage, file_storage, user_id, item)
                status = RecoveryMutationStatus.PERMANENTLY_DELETED
            else:
                await _restore_item(storage, file_storage, user_id, item)
                status = RecoveryMutationStatus.RESTORED
        except _EXPECTED_ITEM_ERRORS as exc:
            outcomes[(item.type.value, item.id)] = RecoveryMutationResult(
                item=item,
                status=RecoveryMutationStatus.FAILED,
                error=RecoveryErrorResponse(code=exc.code, message=exc.message),
            )
        else:
            outcomes[(item.type.value, item.id)] = RecoveryMutationResult(
                item=item,
                status=status,
            )

    return [outcomes[(item.type.value, item.id)] for item in items]
