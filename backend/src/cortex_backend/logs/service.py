"""Owner-scoped activity-log use cases over the shared database storage seam."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import and_, or_, select

from ..storage import DatabaseStorage
from .errors import InvalidActivityLogCursorError, InvalidActivityLogQueryError
from .models import ActivityLog
from .schemas import MAX_METADATA_BYTES, ActivityLogCreateRequest

DEFAULT_LOG_LIMIT = 50
MAX_LOG_LIMIT = 100


@dataclass(frozen=True)
class ActivityLogRecord:
    """Transport-independent representation of one activity record."""

    id: str
    user_id: str
    event_type: str
    entity_type: str | None
    entity_id: str | None
    metadata: dict[str, Any]
    created_at: datetime


@dataclass(frozen=True)
class ActivityLogFilters:
    """Owner-scoped filters for newest-first activity history."""

    event_type: str | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    limit: int = DEFAULT_LOG_LIMIT
    cursor: str | None = None


@dataclass(frozen=True)
class ActivityLogPage:
    """A bounded activity-log page and an optional continuation cursor."""

    items: list[ActivityLogRecord]
    next_cursor: str | None


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _record(log: ActivityLog) -> ActivityLogRecord:
    return ActivityLogRecord(
        id=log.id,
        user_id=log.user_id,
        event_type=log.event_type,
        entity_type=log.entity_type,
        entity_id=log.entity_id,
        metadata=dict(log.metadata_json),
        created_at=_as_utc(log.created_at),
    )


def _normalize_filter(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        raise InvalidActivityLogQueryError()
    return normalized


def _normalized_filters(filters: ActivityLogFilters) -> ActivityLogFilters:
    if not 1 <= filters.limit <= MAX_LOG_LIMIT:
        raise InvalidActivityLogQueryError()
    return ActivityLogFilters(
        event_type=_normalize_filter(filters.event_type),
        entity_type=_normalize_filter(filters.entity_type),
        entity_id=_normalize_filter(filters.entity_id),
        limit=filters.limit,
        cursor=filters.cursor,
    )


def _filter_fingerprint(filters: ActivityLogFilters) -> str:
    payload = {
        "event_type": filters.event_type,
        "entity_type": filters.entity_type,
        "entity_id": filters.entity_id,
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _encode_cursor(log: ActivityLog, fingerprint: str) -> str:
    payload = {
        "v": 1,
        "f": fingerprint,
        "created_at": _as_utc(log.created_at).isoformat(),
        "id": log.id,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str, fingerprint: str) -> tuple[datetime, str]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
        if payload.get("v") != 1 or payload.get("f") != fingerprint:
            raise ValueError
        created_at = datetime.fromisoformat(payload["created_at"])
        log_id = payload["id"]
        if created_at.tzinfo is None or not isinstance(log_id, str) or not log_id:
            raise ValueError
        return _as_utc(created_at), log_id
    except (binascii.Error, ValueError, KeyError, TypeError, json.JSONDecodeError):
        raise InvalidActivityLogCursorError() from None


async def append_log(
    storage: DatabaseStorage,
    user_id: str,
    payload: ActivityLogCreateRequest,
) -> ActivityLogRecord:
    """Append one owner-scoped activity record."""

    if not user_id.strip():
        raise InvalidActivityLogQueryError()
    metadata_size = len(
        json.dumps(
            payload.metadata,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    if metadata_size > MAX_METADATA_BYTES:
        raise InvalidActivityLogQueryError()

    now = _utc_now()
    async with storage.session() as db:
        async with db.begin():
            log = ActivityLog(
                id=str(uuid4()),
                user_id=user_id,
                event_type=payload.event_type,
                entity_type=payload.entity_type,
                entity_id=payload.entity_id,
                metadata_json=dict(payload.metadata),
                created_at=now,
            )
            db.add(log)
            await db.flush()
            return _record(log)


async def list_logs(
    storage: DatabaseStorage,
    user_id: str,
    filters: ActivityLogFilters | None = None,
) -> ActivityLogPage:
    """Return a bounded newest-first page of activity records for one owner."""

    if not user_id.strip():
        raise InvalidActivityLogQueryError()
    normalized = _normalized_filters(filters or ActivityLogFilters())
    fingerprint = _filter_fingerprint(normalized)

    async with storage.session() as db:
        stmt = select(ActivityLog).where(ActivityLog.user_id == user_id)
        if normalized.event_type is not None:
            stmt = stmt.where(ActivityLog.event_type == normalized.event_type)
        if normalized.entity_type is not None:
            stmt = stmt.where(ActivityLog.entity_type == normalized.entity_type)
        if normalized.entity_id is not None:
            stmt = stmt.where(ActivityLog.entity_id == normalized.entity_id)
        if normalized.cursor:
            cursor_created_at, cursor_id = _decode_cursor(normalized.cursor, fingerprint)
            stmt = stmt.where(
                or_(
                    ActivityLog.created_at < cursor_created_at,
                    and_(
                        ActivityLog.created_at == cursor_created_at,
                        ActivityLog.id < cursor_id,
                    ),
                )
            )

        stmt = stmt.order_by(ActivityLog.created_at.desc(), ActivityLog.id.desc())
        rows = list((await db.scalars(stmt.limit(normalized.limit + 1))).all())
        page_rows = rows[: normalized.limit]
        next_cursor = (
            _encode_cursor(page_rows[-1], fingerprint) if len(rows) > normalized.limit else None
        )
        return ActivityLogPage(
            items=[_record(log) for log in page_rows],
            next_cursor=next_cursor,
        )
