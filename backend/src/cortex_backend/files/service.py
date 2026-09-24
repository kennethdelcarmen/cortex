"""Owner-scoped file use cases over database metadata and blob storage."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from collections.abc import AsyncIterable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..storage import DatabaseStorage
from .errors import (
    FileContentMissingError,
    FileError,
    FileNotFoundError,
    FileStorageUnavailableError,
    InvalidFileCursorError,
    InvalidFileNameError,
    InvalidFileQueryError,
)
from .models import File
from .schemas import FileRenameRequest
from .storage import FileBlobStore

DEFAULT_FILE_LIMIT = 50
MAX_FILE_LIMIT = 100
MAX_FILENAME_LENGTH = 255
MAX_MEDIA_TYPE_LENGTH = 127
DEFAULT_MEDIA_TYPE = "application/octet-stream"
_MEDIA_TYPE = re.compile(r"^[a-z0-9!#$&^_.+-]+/[a-z0-9!#$&^_.+-]+$")


@dataclass(frozen=True)
class FileRecord:
    """Transport-independent representation of one file metadata record."""

    id: str
    user_id: str
    name: str
    storage_key: str
    media_type: str
    size_bytes: int
    sha256: str
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


@dataclass(frozen=True)
class FileListFilters:
    """Filters for a bounded newest-first file query."""

    include_deleted: bool = False
    limit: int = DEFAULT_FILE_LIMIT
    cursor: str | None = None


@dataclass(frozen=True)
class FilePage:
    """A bounded file page and an optional continuation cursor."""

    items: list[FileRecord]
    next_cursor: str | None


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _record(file: File) -> FileRecord:
    return FileRecord(
        id=file.id,
        user_id=file.user_id,
        name=file.original_name,
        storage_key=file.storage_key,
        media_type=file.media_type,
        size_bytes=file.size_bytes,
        sha256=file.sha256,
        created_at=_as_utc(file.created_at),
        updated_at=_as_utc(file.updated_at),
        deleted_at=_as_utc(file.deleted_at) if file.deleted_at is not None else None,
    )


def normalize_filename(value: str | None) -> str:
    """Return a safe display name without allowing path traversal or controls."""

    if value is None:
        raise InvalidFileNameError()
    normalized = value.replace("\\", "/").rsplit("/", maxsplit=1)[-1].strip()
    if (
        not normalized
        or len(normalized) > MAX_FILENAME_LENGTH
        or any(ord(character) < 32 or ord(character) == 127 for character in normalized)
    ):
        raise InvalidFileNameError()
    return normalized


def normalize_media_type(value: str | None) -> str:
    """Keep a safe declared media type, falling back for missing or malformed input."""

    if value is None:
        return DEFAULT_MEDIA_TYPE
    normalized = value.strip().casefold()
    if len(normalized) > MAX_MEDIA_TYPE_LENGTH or not _MEDIA_TYPE.fullmatch(normalized):
        return DEFAULT_MEDIA_TYPE
    return normalized


def _filter_fingerprint(filters: FileListFilters) -> str:
    serialized = json.dumps(
        {"include_deleted": filters.include_deleted},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _encode_cursor(file: File, fingerprint: str) -> str:
    payload = {
        "v": 1,
        "f": fingerprint,
        "created_at": _as_utc(file.created_at).isoformat(),
        "id": file.id,
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
        file_id = payload["id"]
        if created_at.tzinfo is None or not isinstance(file_id, str) or not file_id:
            raise ValueError
        return _as_utc(created_at), file_id
    except (binascii.Error, ValueError, KeyError, TypeError, json.JSONDecodeError):
        raise InvalidFileCursorError() from None


def _normalized_filters(filters: FileListFilters) -> FileListFilters:
    if not 1 <= filters.limit <= MAX_FILE_LIMIT:
        raise InvalidFileQueryError()
    return filters


async def _get_file_row(
    db: AsyncSession,
    user_id: str,
    file_id: str,
    *,
    include_deleted: bool = False,
) -> File:
    statement = select(File).where(File.id == file_id, File.user_id == user_id).limit(1)
    if not include_deleted:
        statement = statement.where(File.deleted_at.is_(None))
    file = await db.scalar(statement)
    if file is None:
        raise FileNotFoundError()
    return file


async def create_file(
    storage: DatabaseStorage,
    blob_store: FileBlobStore,
    user_id: str,
    filename: str | None,
    media_type: str | None,
    chunks: AsyncIterable[bytes],
    max_bytes: int,
) -> FileRecord:
    """Stream one owner-scoped file and persist its metadata."""

    original_name = normalize_filename(filename)
    object_key = f"{uuid4().hex}.blob"
    try:
        blob = await blob_store.write(object_key, chunks, max_bytes)
    except FileError:
        raise
    except Exception as exc:
        raise FileStorageUnavailableError() from exc

    now = _utc_now()
    try:
        async with storage.session() as db:
            async with db.begin():
                file = File(
                    id=str(uuid4()),
                    user_id=user_id,
                    original_name=original_name,
                    storage_key=blob.storage_key,
                    media_type=normalize_media_type(media_type),
                    size_bytes=blob.size_bytes,
                    sha256=blob.sha256,
                    created_at=now,
                    updated_at=now,
                    deleted_at=None,
                )
                db.add(file)
                await db.flush()
                record = _record(file)
    except Exception:
        try:
            await blob_store.delete(blob.storage_key)
        except Exception:
            pass
        raise
    return record


async def get_file(storage: DatabaseStorage, user_id: str, file_id: str) -> FileRecord:
    """Return one active file owned by the authenticated user."""

    async with storage.session() as db:
        return _record(await _get_file_row(db, user_id, file_id))


async def list_files(
    storage: DatabaseStorage,
    user_id: str,
    filters: FileListFilters | None = None,
) -> FilePage:
    """Return a bounded newest-first page of owner-scoped files."""

    normalized = _normalized_filters(filters or FileListFilters())
    fingerprint = _filter_fingerprint(normalized)
    async with storage.session() as db:
        statement = select(File).where(File.user_id == user_id)
        if not normalized.include_deleted:
            statement = statement.where(File.deleted_at.is_(None))
        if normalized.cursor:
            cursor_created_at, cursor_id = _decode_cursor(normalized.cursor, fingerprint)
            statement = statement.where(
                or_(
                    File.created_at < cursor_created_at,
                    and_(File.created_at == cursor_created_at, File.id < cursor_id),
                )
            )
        statement = statement.order_by(File.created_at.desc(), File.id.desc()).limit(
            normalized.limit + 1
        )
        files = list((await db.scalars(statement)).all())
        page_files = files[: normalized.limit]
        next_cursor = (
            _encode_cursor(page_files[-1], fingerprint) if len(files) > normalized.limit else None
        )
        return FilePage(items=[_record(file) for file in page_files], next_cursor=next_cursor)


async def rename_file(
    storage: DatabaseStorage,
    user_id: str,
    file_id: str,
    payload: FileRenameRequest,
) -> FileRecord:
    """Rename an active file without changing its stored bytes."""

    name = normalize_filename(payload.name)
    async with storage.session() as db:
        async with db.begin():
            file = await _get_file_row(db, user_id, file_id)
            file.original_name = name
            file.updated_at = _utc_now()
            await db.flush()
            return _record(file)


async def delete_file(storage: DatabaseStorage, user_id: str, file_id: str) -> None:
    """Soft-delete one active file while retaining bytes for recovery."""

    async with storage.session() as db:
        async with db.begin():
            file = await _get_file_row(db, user_id, file_id)
            now = _utc_now()
            file.deleted_at = now
            file.updated_at = now
            await db.flush()


async def restore_file(
    storage: DatabaseStorage,
    user_id: str,
    file_id: str,
) -> FileRecord:
    """Restore a deleted file, returning active files unchanged for retry safety."""

    async with storage.session() as db:
        async with db.begin():
            file = await _get_file_row(db, user_id, file_id, include_deleted=True)
            if file.deleted_at is not None:
                file.deleted_at = None
                file.updated_at = _utc_now()
                await db.flush()
            return _record(file)


async def stream_file(
    storage: DatabaseStorage,
    blob_store: FileBlobStore,
    user_id: str,
    file_id: str,
) -> tuple[FileRecord, AsyncIterable[bytes]]:
    """Resolve metadata and prepare a bounded-memory content stream."""

    record = await get_file(storage, user_id, file_id)
    try:
        stream = await blob_store.stream(record.storage_key)
    except FileContentMissingError:
        raise
    except FileError:
        raise
    except Exception as exc:
        raise FileContentMissingError() from exc
    return record, stream
