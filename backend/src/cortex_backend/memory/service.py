"""Owner-scoped note use cases over the shared database storage seam."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import uuid4

from sqlalchemy import and_, delete, exists, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..storage import DatabaseStorage
from ..tasks.models import Tag
from .errors import (
    InvalidNoteCursorError,
    InvalidNoteQueryError,
    InvalidNoteTagError,
    NoteNotFoundError,
)
from .models import Note, NoteTag
from .schemas import NoteCreateRequest, NoteUpdateRequest

DEFAULT_NOTE_LIMIT = 50
MAX_NOTE_LIMIT = 100
MAX_SEARCH_LENGTH = 200


@dataclass(frozen=True)
class NoteRecord:
    """Transport-independent representation of one note."""

    id: str
    user_id: str
    title: str | None
    body: str
    journal_date: date | None
    tags: list[str]
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


@dataclass(frozen=True)
class NoteListFilters:
    """Filters for a bounded, recently-updated note query."""

    tags: tuple[str, ...] = ()
    search: str | None = None
    journal_date_from: date | None = None
    journal_date_to: date | None = None
    include_deleted: bool = False
    limit: int = DEFAULT_NOTE_LIMIT
    cursor: str | None = None


@dataclass(frozen=True)
class NotePage:
    """A bounded note page and an optional continuation cursor."""

    items: list[NoteRecord]
    next_cursor: str | None


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _record(note: Note, tags: list[str]) -> NoteRecord:
    return NoteRecord(
        id=note.id,
        user_id=note.user_id,
        title=note.title,
        body=note.body,
        journal_date=note.journal_date,
        tags=tags,
        created_at=_as_utc(note.created_at),
        updated_at=_as_utc(note.updated_at),
        deleted_at=_as_utc(note.deleted_at) if note.deleted_at is not None else None,
    )


def _normalize_tag_names(values: list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
    if values is None:
        return ()
    normalized: dict[str, None] = {}
    for value in values:
        name = value.strip().casefold()
        if not name or len(name) > 64:
            raise InvalidNoteTagError()
        normalized[name] = None
    if len(normalized) > 20:
        raise InvalidNoteTagError()
    return tuple(normalized)


def _normalize_search(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.strip().casefold().split())
    if not normalized:
        return None
    if len(normalized) > MAX_SEARCH_LENGTH:
        raise InvalidNoteQueryError()
    return normalized


def _fts_query(value: str | None) -> str | None:
    if value is None:
        return None
    tokens = re.findall(r"\w+", value, flags=re.UNICODE)
    if not tokens:
        return None
    return " AND ".join(f'"{token.replace(chr(34), chr(34) * 2)}"' for token in tokens)


def _filter_fingerprint(filters: NoteListFilters) -> str:
    payload = {
        "tags": list(filters.tags),
        "search": filters.search,
        "journal_date_from": (
            filters.journal_date_from.isoformat() if filters.journal_date_from else None
        ),
        "journal_date_to": (
            filters.journal_date_to.isoformat() if filters.journal_date_to else None
        ),
        "include_deleted": filters.include_deleted,
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _encode_cursor(note: Note, fingerprint: str) -> str:
    payload = {
        "v": 1,
        "f": fingerprint,
        "updated_at": _as_utc(note.updated_at).isoformat(),
        "id": note.id,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str, fingerprint: str) -> tuple[datetime, str]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
        if payload.get("v") != 1 or payload.get("f") != fingerprint:
            raise ValueError
        updated_at = datetime.fromisoformat(payload["updated_at"])
        note_id = payload["id"]
        if updated_at.tzinfo is None or not isinstance(note_id, str) or not note_id:
            raise ValueError
        return _as_utc(updated_at), note_id
    except (binascii.Error, ValueError, KeyError, TypeError, json.JSONDecodeError):
        raise InvalidNoteCursorError() from None


async def _tags_for_notes(db: AsyncSession, note_ids: list[str]) -> dict[str, list[str]]:
    if not note_ids:
        return {}
    result = await db.execute(
        select(NoteTag.note_id, Tag.name)
        .join(Tag, Tag.id == NoteTag.tag_id)
        .where(NoteTag.note_id.in_(note_ids))
        .order_by(Tag.name.asc())
    )
    tags: dict[str, list[str]] = defaultdict(list)
    for note_id, name in result.all():
        tags[note_id].append(name)
    return tags


async def _replace_tags(
    db: AsyncSession,
    note_id: str,
    user_id: str,
    tag_names: list[str] | tuple[str, ...] | None,
) -> None:
    normalized_names = _normalize_tag_names(tag_names)
    await db.execute(delete(NoteTag).where(NoteTag.note_id == note_id))
    for name in normalized_names:
        tag = await db.scalar(select(Tag).where(Tag.user_id == user_id, Tag.name == name).limit(1))
        if tag is None:
            tag = Tag(id=str(uuid4()), user_id=user_id, name=name, created_at=_utc_now())
            db.add(tag)
            await db.flush()
        db.add(NoteTag(note_id=note_id, tag_id=tag.id))
    await db.flush()


async def _sync_fts(db: AsyncSession, note: Note, tags: list[str]) -> None:
    await db.execute(
        text("DELETE FROM notes_fts WHERE note_id = :note_id"),
        {"note_id": note.id},
    )
    await db.execute(
        text(
            "INSERT INTO notes_fts (note_id, title, body, tags) "
            "VALUES (:note_id, :title, :body, :tags)"
        ),
        {
            "note_id": note.id,
            "title": note.title or "",
            "body": note.body,
            "tags": " ".join(tags),
        },
    )


async def _get_note_row(
    db: AsyncSession,
    user_id: str,
    note_id: str,
    *,
    include_deleted: bool = False,
) -> Note:
    stmt = select(Note).where(Note.id == note_id, Note.user_id == user_id).limit(1)
    if not include_deleted:
        stmt = stmt.where(Note.deleted_at.is_(None))
    note = await db.scalar(stmt)
    if note is None:
        raise NoteNotFoundError()
    return note


async def create_note(
    storage: DatabaseStorage,
    user_id: str,
    payload: NoteCreateRequest,
) -> NoteRecord:
    """Create one owner-scoped Markdown note."""

    now = _utc_now()
    async with storage.session() as db:
        async with db.begin():
            note = Note(
                id=str(uuid4()),
                user_id=user_id,
                title=payload.title,
                body=payload.body,
                journal_date=payload.journal_date,
                created_at=now,
                updated_at=now,
                deleted_at=None,
            )
            db.add(note)
            await db.flush()
            await _replace_tags(db, note.id, user_id, payload.tags)
            tags = (await _tags_for_notes(db, [note.id])).get(note.id, [])
            await _sync_fts(db, note, tags)
            return _record(note, tags)


async def get_note(storage: DatabaseStorage, user_id: str, note_id: str) -> NoteRecord:
    """Return one active note owned by the authenticated user."""

    async with storage.session() as db:
        note = await _get_note_row(db, user_id, note_id)
        tags = (await _tags_for_notes(db, [note.id])).get(note.id, [])
        return _record(note, tags)


async def update_note(
    storage: DatabaseStorage,
    user_id: str,
    note_id: str,
    payload: NoteUpdateRequest,
) -> NoteRecord:
    """Apply a partial update to one active note."""

    fields = payload.model_fields_set
    now = _utc_now()
    async with storage.session() as db:
        async with db.begin():
            note = await _get_note_row(db, user_id, note_id)
            if "title" in fields:
                note.title = payload.title
            if "body" in fields and payload.body is not None:
                note.body = payload.body
            if "journal_date" in fields:
                note.journal_date = payload.journal_date
            if "tags" in fields:
                await _replace_tags(db, note.id, user_id, payload.tags or [])
            if fields:
                note.updated_at = now
            await db.flush()
            tags = (await _tags_for_notes(db, [note.id])).get(note.id, [])
            await _sync_fts(db, note, tags)
            return _record(note, tags)


async def delete_note(storage: DatabaseStorage, user_id: str, note_id: str) -> None:
    """Soft-delete one active note."""

    now = _utc_now()
    async with storage.session() as db:
        async with db.begin():
            note = await _get_note_row(db, user_id, note_id)
            note.deleted_at = now
            note.updated_at = now
            await db.flush()


async def restore_note(
    storage: DatabaseStorage,
    user_id: str,
    note_id: str,
) -> NoteRecord:
    """Restore one note, returning active notes unchanged for retry safety."""

    now = _utc_now()
    async with storage.session() as db:
        async with db.begin():
            note = await _get_note_row(db, user_id, note_id, include_deleted=True)
            if note.deleted_at is not None:
                note.deleted_at = None
                note.updated_at = now
                await db.flush()
            tags = (await _tags_for_notes(db, [note.id])).get(note.id, [])
            return _record(note, tags)


async def list_notes(
    storage: DatabaseStorage,
    user_id: str,
    filters: NoteListFilters | None = None,
) -> NotePage:
    """Return a bounded, filtered page of notes ordered by recent updates."""

    resolved = filters or NoteListFilters()
    if not 1 <= resolved.limit <= MAX_NOTE_LIMIT:
        raise InvalidNoteQueryError()
    journal_date_from = resolved.journal_date_from
    journal_date_to = resolved.journal_date_to
    if (
        journal_date_from is not None
        and journal_date_to is not None
        and journal_date_from > journal_date_to
    ):
        raise InvalidNoteQueryError()

    normalized = NoteListFilters(
        tags=_normalize_tag_names(resolved.tags),
        search=_normalize_search(resolved.search),
        journal_date_from=journal_date_from,
        journal_date_to=journal_date_to,
        include_deleted=resolved.include_deleted,
        limit=resolved.limit,
        cursor=resolved.cursor,
    )
    fingerprint = _filter_fingerprint(normalized)

    async with storage.session() as db:
        stmt = select(Note).where(Note.user_id == user_id)
        if not normalized.include_deleted:
            stmt = stmt.where(Note.deleted_at.is_(None))
        if normalized.journal_date_from is not None:
            stmt = stmt.where(Note.journal_date >= normalized.journal_date_from)
        if normalized.journal_date_to is not None:
            stmt = stmt.where(Note.journal_date <= normalized.journal_date_to)
        for tag_name in normalized.tags:
            stmt = stmt.where(
                exists(
                    select(NoteTag.note_id)
                    .join(Tag, Tag.id == NoteTag.tag_id)
                    .where(
                        NoteTag.note_id == Note.id,
                        Tag.user_id == user_id,
                        Tag.name == tag_name,
                    )
                )
            )
        fts_query = _fts_query(normalized.search)
        if fts_query is not None:
            stmt = stmt.where(
                text(
                    "EXISTS (SELECT 1 FROM notes_fts "
                    "WHERE notes_fts.note_id = notes.id "
                    "AND notes_fts MATCH :fts_query)"
                ).bindparams(fts_query=fts_query)
            )
        if normalized.cursor:
            cursor_updated_at, cursor_id = _decode_cursor(normalized.cursor, fingerprint)
            stmt = stmt.where(
                or_(
                    Note.updated_at < cursor_updated_at,
                    and_(Note.updated_at == cursor_updated_at, Note.id < cursor_id),
                )
            )

        stmt = stmt.order_by(Note.updated_at.desc(), Note.id.desc())
        rows = list((await db.scalars(stmt.limit(normalized.limit + 1))).all())
        page_rows = rows[: normalized.limit]
        tags_by_note = await _tags_for_notes(db, [note.id for note in page_rows])
        next_cursor = (
            _encode_cursor(page_rows[-1], fingerprint) if len(rows) > normalized.limit else None
        )
        return NotePage(
            items=[_record(note, tags_by_note.get(note.id, [])) for note in page_rows],
            next_cursor=next_cursor,
        )
