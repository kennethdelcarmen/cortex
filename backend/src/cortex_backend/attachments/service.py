"""Shared attachment use cases over the database storage seam."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..files.models import File, FileContextJob, FileTag
from ..files.schemas import FileContextStatus
from ..files.service import FileRecord
from ..tasks.models import Tag
from .errors import AttachmentError
from .models import NoteFile, TaskFile, TaskSeriesFile

MAX_ATTACHMENTS = 20


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def normalize_file_ids(file_ids: Iterable[str] | None) -> list[str]:
    """Deduplicate attachment IDs while preserving the caller's order."""

    normalized: list[str] = []
    seen: set[str] = set()
    for file_id in file_ids or ():
        if not isinstance(file_id, str) or not file_id or file_id in seen:
            if not isinstance(file_id, str) or not file_id:
                raise AttachmentError()
            continue
        seen.add(file_id)
        normalized.append(file_id)
    if len(normalized) > MAX_ATTACHMENTS:
        raise AttachmentError()
    return normalized


async def _file_records(
    db: AsyncSession,
    user_id: str,
    files: list[File],
) -> dict[str, FileRecord]:
    if not files:
        return {}

    file_ids = [file.id for file in files]
    tag_rows = await db.execute(
        select(FileTag.file_id, Tag.name)
        .join(Tag, Tag.id == FileTag.tag_id)
        .where(FileTag.file_id.in_(file_ids))
        .order_by(Tag.name.asc())
    )
    tags: dict[str, list[str]] = defaultdict(list)
    for file_id, name in tag_rows.all():
        tags[file_id].append(name)

    jobs = list(
        (
            await db.scalars(
                select(FileContextJob).where(
                    FileContextJob.user_id == user_id,
                    FileContextJob.source_sha256.in_({file.sha256 for file in files}),
                )
            )
        ).all()
    )
    statuses: dict[str, FileContextStatus] = {
        job.source_sha256: cast(FileContextStatus, job.status) for job in jobs
    }

    return {
        file.id: FileRecord(
            id=file.id,
            user_id=file.user_id,
            name=file.original_name,
            storage_key=file.storage_key,
            size_bytes=file.size_bytes,
            sha256=file.sha256,
            tags=tags.get(file.id, []),
            context_status=statuses.get(file.sha256, "pending"),
            created_at=_as_utc(file.created_at),
            updated_at=_as_utc(file.updated_at),
            deleted_at=_as_utc(file.deleted_at) if file.deleted_at is not None else None,
        )
        for file in files
    }


async def _validate_active_files(
    db: AsyncSession,
    user_id: str,
    file_ids: list[str],
) -> None:
    if not file_ids:
        return
    rows = list(
        (
            await db.scalars(
                select(File).where(
                    File.user_id == user_id,
                    File.id.in_(file_ids),
                    File.deleted_at.is_(None),
                )
            )
        ).all()
    )
    if len(rows) != len(file_ids):
        raise AttachmentError()


async def _replace_links(
    db: AsyncSession,
    user_id: str,
    association_model: type[Any],
    owner_column: Any,
    owner_id: str,
    file_ids: Iterable[str] | None,
    *,
    preserve_deleted: bool = True,
) -> None:
    normalized = normalize_file_ids(file_ids)
    await _validate_active_files(db, user_id, normalized)

    next_position = 0
    if preserve_deleted:
        deleted_positions: Any = await db.scalars(
            select(association_model.position)
            .join(File, File.id == association_model.file_id)
            .where(
                owner_column == owner_id,
                File.user_id == user_id,
                File.deleted_at.is_not(None),
            )
        )
        retained_positions = list(deleted_positions.all())
        next_position = max(retained_positions, default=-1) + 1

    delete_statement = delete(association_model).where(owner_column == owner_id)
    if preserve_deleted:
        delete_statement = delete_statement.where(
            association_model.file_id.in_(select(File.id).where(File.deleted_at.is_(None)))
        )
    await db.execute(delete_statement)
    for position, file_id in enumerate(normalized, start=next_position):
        db.add(
            association_model(
                **{
                    owner_column.key: owner_id,
                    "file_id": file_id,
                    "position": position,
                }
            )
        )
    await db.flush()


async def replace_note_attachments(
    db: AsyncSession,
    user_id: str,
    note_id: str,
    file_ids: Iterable[str] | None,
) -> None:
    await _replace_links(db, user_id, NoteFile, NoteFile.note_id, note_id, file_ids)


async def replace_task_attachments(
    db: AsyncSession,
    user_id: str,
    task_id: str,
    file_ids: Iterable[str] | None,
) -> None:
    await _replace_links(db, user_id, TaskFile, TaskFile.task_id, task_id, file_ids)


async def replace_series_attachments(
    db: AsyncSession,
    user_id: str,
    series_id: str,
    file_ids: Iterable[str] | None,
) -> None:
    await _replace_links(db, user_id, TaskSeriesFile, TaskSeriesFile.series_id, series_id, file_ids)


async def copy_series_attachments(
    db: AsyncSession,
    series_id: str,
    task_id: str,
) -> None:
    await db.execute(delete(TaskFile).where(TaskFile.task_id == task_id))
    rows = list(
        (
            await db.scalars(
                select(TaskSeriesFile)
                .where(TaskSeriesFile.series_id == series_id)
                .order_by(TaskSeriesFile.position.asc())
            )
        ).all()
    )
    for row in rows:
        db.add(TaskFile(task_id=task_id, file_id=row.file_id, position=row.position))
    await db.flush()


async def _attachments_for(
    db: AsyncSession,
    user_id: str,
    association_model: type[Any],
    owner_column: Any,
    owner_ids: list[str],
) -> dict[str, list[FileRecord]]:
    if not owner_ids:
        return {}
    result = await db.execute(
        select(owner_column, association_model.position, File)
        .join(File, File.id == association_model.file_id)
        .where(
            owner_column.in_(owner_ids),
            File.user_id == user_id,
            File.deleted_at.is_(None),
        )
        .order_by(owner_column.asc(), association_model.position.asc())
    )
    rows: list[tuple[str, int, File]] = [
        (str(owner_id), cast(int, position), cast(File, file))
        for owner_id, position, file in result.all()
    ]
    files = await _file_records(db, user_id, [file for _, _, file in rows])
    attachments: dict[str, list[FileRecord]] = defaultdict(list)
    for owner_id, _, file in rows:
        attachments[owner_id].append(files[file.id])
    return attachments


async def attachments_for_notes(
    db: AsyncSession,
    user_id: str,
    note_ids: list[str],
) -> dict[str, list[FileRecord]]:
    return await _attachments_for(db, user_id, NoteFile, NoteFile.note_id, note_ids)


async def attachments_for_tasks(
    db: AsyncSession,
    user_id: str,
    task_ids: list[str],
) -> dict[str, list[FileRecord]]:
    return await _attachments_for(db, user_id, TaskFile, TaskFile.task_id, task_ids)


async def attachments_for_series(
    db: AsyncSession,
    user_id: str,
    series_ids: list[str],
) -> dict[str, list[FileRecord]]:
    return await _attachments_for(db, user_id, TaskSeriesFile, TaskSeriesFile.series_id, series_ids)


async def delete_note_attachments(db: AsyncSession, note_id: str) -> None:
    await db.execute(delete(NoteFile).where(NoteFile.note_id == note_id))


async def delete_task_attachments(db: AsyncSession, task_id: str) -> None:
    await db.execute(delete(TaskFile).where(TaskFile.task_id == task_id))
