"""Use cases for the shared owner-scoped tag catalog."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..files.models import File, FileTag
from ..memory.content import html_to_text
from ..memory.models import Note, NoteTag
from ..storage import DatabaseStorage
from ..tasks.models import Tag, TaskSeriesTag, TaskTag
from .errors import (
    InvalidTagNameError,
    TagInactiveError,
    TagMustBeArchivedError,
    TagNameConflictError,
    TagNotFoundError,
    UnknownTagError,
)
from .schemas import TagColor, TagCreateRequest, TagUpdateRequest


@dataclass(frozen=True)
class TagRecord:
    id: str
    name: str
    color: TagColor
    active: bool
    created_at: datetime
    archived_at: datetime | None


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def normalize_tag_name(value: str) -> str:
    normalized = value.strip().casefold()
    if not normalized or len(normalized) > 64:
        raise InvalidTagNameError()
    return normalized


def _record(tag: Tag) -> TagRecord:
    return TagRecord(
        id=tag.id,
        name=tag.name,
        color=TagColor(tag.color),
        active=tag.archived_at is None,
        created_at=_as_utc(tag.created_at),
        archived_at=_as_utc(tag.archived_at) if tag.archived_at is not None else None,
    )


async def _get_tag(db: AsyncSession, user_id: str, tag_id: str) -> Tag:
    tag = await db.scalar(select(Tag).where(Tag.id == tag_id, Tag.user_id == user_id).limit(1))
    if tag is None:
        raise TagNotFoundError()
    return tag


async def list_tags(
    storage: DatabaseStorage,
    user_id: str,
    *,
    include_inactive: bool = False,
) -> list[TagRecord]:
    async with storage.session() as db:
        stmt = select(Tag).where(Tag.user_id == user_id)
        if not include_inactive:
            stmt = stmt.where(Tag.archived_at.is_(None))
        stmt = stmt.order_by(Tag.archived_at.is_not(None), Tag.name.asc())
        return [_record(tag) for tag in (await db.scalars(stmt)).all()]


async def create_tag(
    storage: DatabaseStorage,
    user_id: str,
    payload: TagCreateRequest,
) -> TagRecord:
    now = _utc_now()
    name = normalize_tag_name(payload.name)
    async with storage.session() as db:
        async with db.begin():
            existing = await db.scalar(
                select(Tag).where(Tag.user_id == user_id, Tag.name == name).limit(1)
            )
            if existing is not None:
                if existing.archived_at is not None:
                    raise TagInactiveError()
                raise TagNameConflictError()
            tag = Tag(
                id=str(uuid4()),
                user_id=user_id,
                name=name,
                color=payload.color.value,
                created_at=now,
                archived_at=None,
            )
            db.add(tag)
            await db.flush()
            return _record(tag)


async def update_tag(
    storage: DatabaseStorage,
    user_id: str,
    tag_id: str,
    payload: TagUpdateRequest,
) -> TagRecord:
    async with storage.session() as db:
        async with db.begin():
            tag = await _get_tag(db, user_id, tag_id)
            if payload.name is not None:
                name = normalize_tag_name(payload.name)
                conflict = await db.scalar(
                    select(Tag)
                    .where(
                        Tag.user_id == user_id,
                        Tag.name == name,
                        Tag.id != tag_id,
                    )
                    .limit(1)
                )
                if conflict is not None:
                    raise TagNameConflictError()
                tag.name = name
                await _refresh_note_search_for_tag(db, tag.id)
                await _refresh_file_search_for_tag(db, tag.id)
            if payload.color is not None:
                tag.color = payload.color.value
            await db.flush()
            return _record(tag)


async def archive_tag(storage: DatabaseStorage, user_id: str, tag_id: str) -> TagRecord:
    async with storage.session() as db:
        async with db.begin():
            tag = await _get_tag(db, user_id, tag_id)
            if tag.archived_at is None:
                tag.archived_at = _utc_now()
                await db.flush()
            return _record(tag)


async def restore_tag(storage: DatabaseStorage, user_id: str, tag_id: str) -> TagRecord:
    async with storage.session() as db:
        async with db.begin():
            tag = await _get_tag(db, user_id, tag_id)
            if tag.archived_at is not None:
                tag.archived_at = None
                await db.flush()
            return _record(tag)


async def permanently_delete_tag(
    storage: DatabaseStorage,
    user_id: str,
    tag_id: str,
) -> None:
    async with storage.session() as db:
        async with db.begin():
            tag = await _get_tag(db, user_id, tag_id)
            if tag.archived_at is None:
                raise TagMustBeArchivedError()

            note_ids = list(
                (await db.scalars(select(NoteTag.note_id).where(NoteTag.tag_id == tag.id))).all()
            )
            file_ids = list(
                (await db.scalars(select(FileTag.file_id).where(FileTag.tag_id == tag.id))).all()
            )
            await db.execute(delete(NoteTag).where(NoteTag.tag_id == tag.id))
            await db.execute(delete(FileTag).where(FileTag.tag_id == tag.id))
            await db.execute(delete(TaskTag).where(TaskTag.tag_id == tag.id))
            await db.execute(delete(TaskSeriesTag).where(TaskSeriesTag.tag_id == tag.id))
            await db.delete(tag)
            await db.flush()
            await _refresh_note_search_for_notes(db, note_ids)
            await _refresh_file_search_for_files(db, file_ids)


async def resolve_tag_names(
    db: AsyncSession,
    user_id: str,
    names: Iterable[str],
    *,
    retain_inactive: Iterable[str] = (),
) -> dict[str, Tag]:
    """Resolve submitted names without creating catalog entries."""

    normalized_names = tuple(dict.fromkeys(normalize_tag_name(name) for name in names))
    if not normalized_names:
        return {}
    retained = set(retain_inactive)
    rows = list(
        (
            await db.scalars(
                select(Tag).where(Tag.user_id == user_id, Tag.name.in_(normalized_names))
            )
        ).all()
    )
    by_name = {tag.name: tag for tag in rows}
    unknown = [
        name
        for name in normalized_names
        if name not in by_name or (by_name[name].archived_at is not None and name not in retained)
    ]
    if unknown:
        allowed = list(
            (
                await db.scalars(
                    select(Tag.name)
                    .where(Tag.user_id == user_id, Tag.archived_at.is_(None))
                    .order_by(Tag.name.asc())
                )
            ).all()
        )
        raise UnknownTagError(unknown, allowed)
    return by_name


async def existing_tag_names(
    db: AsyncSession,
    association_model: type[TaskTag] | type[TaskSeriesTag] | type[NoteTag] | type[FileTag],
    owner_id: str,
) -> set[str]:
    """Return names already attached to one record for safe inactive retention."""

    if association_model is TaskTag:
        stmt = (
            select(Tag.name)
            .join(TaskTag, TaskTag.tag_id == Tag.id)
            .where(TaskTag.task_id == owner_id)
        )
    elif association_model is TaskSeriesTag:
        stmt = (
            select(Tag.name)
            .join(TaskSeriesTag, TaskSeriesTag.tag_id == Tag.id)
            .where(TaskSeriesTag.series_id == owner_id)
        )
    elif association_model is NoteTag:
        stmt = (
            select(Tag.name)
            .join(NoteTag, NoteTag.tag_id == Tag.id)
            .where(NoteTag.note_id == owner_id)
        )
    else:
        stmt = (
            select(Tag.name)
            .join(FileTag, FileTag.tag_id == Tag.id)
            .where(FileTag.file_id == owner_id)
        )
    return set((await db.scalars(stmt)).all())


async def _refresh_note_search_for_tag(db: AsyncSession, tag_id: str) -> None:
    note_ids = list(
        (await db.scalars(select(NoteTag.note_id).where(NoteTag.tag_id == tag_id))).all()
    )
    await _refresh_note_search_for_notes(db, note_ids)


async def _refresh_file_search_for_tag(db: AsyncSession, tag_id: str) -> None:
    file_ids = list(
        (await db.scalars(select(FileTag.file_id).where(FileTag.tag_id == tag_id))).all()
    )
    await _refresh_file_search_for_files(db, file_ids)


async def _refresh_file_search_for_files(db: AsyncSession, file_ids: Iterable[str]) -> None:
    file_ids = list(file_ids)
    if not file_ids:
        return
    from ..files.service import _sync_file_search_for_file

    files = list((await db.scalars(select(File).where(File.id.in_(file_ids)))).all())
    for file in files:
        await _sync_file_search_for_file(db, file)


async def _refresh_note_search_for_notes(
    db: AsyncSession,
    note_ids: Iterable[str],
) -> None:
    note_ids = list(note_ids)
    if not note_ids:
        return
    notes = list((await db.scalars(select(Note).where(Note.id.in_(note_ids)))).all())
    for note in notes:
        names = list(
            (
                await db.scalars(
                    select(Tag.name)
                    .join(NoteTag, NoteTag.tag_id == Tag.id)
                    .where(NoteTag.note_id == note.id)
                    .order_by(Tag.name.asc())
                )
            ).all()
        )
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
                "body": html_to_text(note.body),
                "tags": " ".join(names),
            },
        )
