"""Owner-scoped file use cases over database metadata and blob storage."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
from collections.abc import AsyncIterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..storage import DatabaseStorage
from .errors import (
    FileContentMissingError,
    FileContextNotReadyError,
    FileError,
    FileNotFoundError,
    FilePreviewUnavailableError,
    FileStorageUnavailableError,
    InvalidFileCursorError,
    InvalidFileNameError,
    InvalidFileQueryError,
)
from .models import FILE_CONTEXT_VERSION, File, FileArtifact, FileContextJob
from .schemas import FileContextStatus, FilePreviewKind
from .storage import FileBlobStore

DEFAULT_FILE_LIMIT = 50
MAX_FILE_LIMIT = 100
MAX_FILENAME_LENGTH = 255
MAX_CONTEXT_CHARACTERS = 100_000
DEFAULT_CONTEXT_CHARACTERS = 20_000
_RAW_TEXT_EXTENSIONS = frozenset(
    {"txt", "md", "markdown", "json", "csv", "tsv", "log", "yaml", "yml", "xml", "toml"}
)
_OFFICE_EXTENSIONS = frozenset({"doc", "docx", "xls", "xlsx", "ppt", "pptx", "odt", "ods", "odp"})
_IMAGE_EXTENSIONS = frozenset({"png", "jpg", "jpeg", "gif", "webp", "bmp", "tif", "tiff"})


@dataclass(frozen=True)
class FileRecord:
    """Transport-independent representation of one file metadata record."""

    id: str
    user_id: str
    name: str
    storage_key: str
    size_bytes: int
    sha256: str
    context_status: FileContextStatus
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


@dataclass(frozen=True)
class FileContextRecord:
    """Bounded context and preview information for a source file."""

    file_id: str
    name: str
    status: FileContextStatus
    text: str | None
    truncated: bool
    preview_kind: FilePreviewKind | None
    error: str | None
    processed_at: datetime | None


@dataclass(frozen=True)
class PreviewStream:
    """A derived or safe raw preview stream and its fixed response media type."""

    stream: AsyncIterable[bytes]
    media_type: str
    size_bytes: int


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _record(file: File, context_status: FileContextStatus = "pending") -> FileRecord:
    return FileRecord(
        id=file.id,
        user_id=file.user_id,
        name=file.original_name,
        storage_key=file.storage_key,
        size_bytes=file.size_bytes,
        sha256=file.sha256,
        context_status=context_status,
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


def _extension(name: str) -> str:
    basename = name.replace("\\", "/").rsplit("/", maxsplit=1)[-1]
    if "." not in basename:
        return ""
    return basename.rsplit(".", maxsplit=1)[-1].casefold()


def preview_kind_for_name(name: str) -> FilePreviewKind | None:
    """Infer only a safe rendering family from the immutable display name."""

    extension = _extension(name)
    if extension in _RAW_TEXT_EXTENSIONS:
        return "text"
    if extension == "pdf" or extension in _OFFICE_EXTENSIONS:
        return "pdf"
    if extension in _IMAGE_EXTENSIONS:
        return "image"
    return None


async def _artifact_for(
    db: AsyncSession,
    user_id: str,
    source_sha256: str,
    kind: str,
) -> FileArtifact | None:
    return await db.scalar(
        select(FileArtifact).where(
            FileArtifact.user_id == user_id,
            FileArtifact.source_sha256 == source_sha256,
            FileArtifact.artifact_kind == kind,
            FileArtifact.extractor_version == FILE_CONTEXT_VERSION,
        )
    )


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


async def _context_job(
    db: AsyncSession,
    user_id: str,
    source_sha256: str,
) -> FileContextJob | None:
    statement = select(FileContextJob).where(
        FileContextJob.user_id == user_id,
        FileContextJob.source_sha256 == source_sha256,
        FileContextJob.extractor_version == FILE_CONTEXT_VERSION,
    )
    return await db.scalar(statement)


async def _context_status(
    db: AsyncSession,
    user_id: str,
    source_sha256: str,
) -> FileContextStatus:
    job = await _context_job(db, user_id, source_sha256)
    if job is None:
        return "pending"
    return cast(FileContextStatus, job.status)


async def create_file(
    storage: DatabaseStorage,
    blob_store: FileBlobStore,
    user_id: str,
    filename: str | None,
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
                    size_bytes=blob.size_bytes,
                    sha256=blob.sha256,
                    created_at=now,
                    updated_at=now,
                    deleted_at=None,
                )
                db.add(file)
                await db.flush()
                existing_job = await _context_job(db, user_id, blob.sha256)
                if existing_job is None:
                    now_job = _utc_now()
                    db.add(
                        FileContextJob(
                            id=str(uuid4()),
                            user_id=user_id,
                            source_sha256=blob.sha256,
                            status="pending",
                            attempts=0,
                            available_at=now_job,
                            lease_expires_at=None,
                            last_error=None,
                            extractor_version=FILE_CONTEXT_VERSION,
                            created_at=now_job,
                            updated_at=now_job,
                        )
                    )
                record = _record(file, "pending")
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
        file = await _get_file_row(db, user_id, file_id)
        return _record(file, await _context_status(db, user_id, file.sha256))


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
        status_by_hash: dict[str, FileContextStatus] = {}
        if page_files:
            jobs = await db.scalars(
                select(FileContextJob).where(
                    FileContextJob.user_id == user_id,
                    FileContextJob.extractor_version == FILE_CONTEXT_VERSION,
                    FileContextJob.source_sha256.in_({file.sha256 for file in page_files}),
                )
            )
            status_by_hash = {
                job.source_sha256: cast(FileContextStatus, job.status) for job in jobs
            }
        return FilePage(
            items=[
                _record(file, status_by_hash.get(file.sha256, "pending")) for file in page_files
            ],
            next_cursor=next_cursor,
        )


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
            return _record(file, await _context_status(db, user_id, file.sha256))


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


async def get_file_context(
    storage: DatabaseStorage,
    blob_store: FileBlobStore,
    user_id: str,
    file_id: str,
    max_characters: int = DEFAULT_CONTEXT_CHARACTERS,
) -> FileContextRecord:
    """Return bounded extracted context for an active source file."""

    if not 1 <= max_characters <= MAX_CONTEXT_CHARACTERS:
        raise InvalidFileQueryError()

    async with storage.session() as db:
        file = await _get_file_row(db, user_id, file_id)
        job = await _context_job(db, user_id, file.sha256)
        status: FileContextStatus = (
            "pending" if job is None else cast(FileContextStatus, job.status)
        )
        text_artifact = None
        pdf_artifact = None
        if job is not None and job.status == "ready":
            text_artifact = await _artifact_for(db, user_id, file.sha256, "text")
            if _extension(file.original_name) in _OFFICE_EXTENSIONS:
                pdf_artifact = await _artifact_for(db, user_id, file.sha256, "pdf")

        text = None
        truncated = False
        if text_artifact is not None:
            try:
                stream = await blob_store.stream(text_artifact.storage_key)
            except FileError:
                raise
            except Exception as exc:
                raise FileContentMissingError() from exc
            raw = bytearray()
            async for chunk in stream:
                raw.extend(chunk)
                if len(raw) > max_characters * 4:
                    break
            decoded = bytes(raw).decode("utf-8", errors="replace")
            text = decoded[:max_characters]
            truncated = len(decoded) > max_characters or len(raw) > max_characters * 4

        extension = _extension(file.original_name)
        if extension in _IMAGE_EXTENSIONS:
            preview_kind: FilePreviewKind | None = "image"
        elif status != "ready":
            preview_kind = None
        elif extension in _OFFICE_EXTENSIONS:
            preview_kind = "pdf" if pdf_artifact is not None else None
        else:
            preview_kind = preview_kind_for_name(file.original_name)

        return FileContextRecord(
            file_id=file.id,
            name=file.original_name,
            status=status,
            text=text,
            truncated=truncated,
            preview_kind=preview_kind,
            error=job.last_error if job is not None and status == "failed" else None,
            processed_at=_as_utc(job.updated_at) if job is not None and status == "ready" else None,
        )


async def stream_preview(
    storage: DatabaseStorage,
    blob_store: FileBlobStore,
    user_id: str,
    file_id: str,
) -> PreviewStream:
    """Stream a safe derived or natively previewable representation."""

    async with storage.session() as db:
        file = await _get_file_row(db, user_id, file_id)
        job = await _context_job(db, user_id, file.sha256)
        extension = _extension(file.original_name)
        artifact: FileArtifact | None = None
        artifact_kind: str | None = None
        media_type = "text/plain; charset=utf-8"

        if extension in _IMAGE_EXTENSIONS:
            storage_key = file.storage_key
            media_type = {
                "jpg": "image/jpeg",
                "jpeg": "image/jpeg",
                "png": "image/png",
                "gif": "image/gif",
                "webp": "image/webp",
                "bmp": "image/bmp",
                "tif": "image/tiff",
                "tiff": "image/tiff",
            }[extension]
            size_bytes = file.size_bytes
        else:
            if job is None or job.status != "ready":
                raise FileContextNotReadyError()
            if extension in _OFFICE_EXTENSIONS:
                artifact = await _artifact_for(db, user_id, file.sha256, "pdf")
                if artifact is None:
                    raise FilePreviewUnavailableError()
                artifact_kind = "pdf"
            elif extension in _RAW_TEXT_EXTENSIONS:
                artifact = await _artifact_for(db, user_id, file.sha256, "text")
                artifact_kind = "text"

            if artifact is None and extension not in {"pdf"}:
                raise FileContextNotReadyError()
            storage_key = artifact.storage_key if artifact is not None else file.storage_key
            if artifact_kind == "pdf" or extension == "pdf":
                media_type = "application/pdf"
            size_bytes = artifact.size_bytes if artifact is not None else file.size_bytes

        try:
            stream = await blob_store.stream(storage_key)
        except FileContentMissingError:
            raise
        except FileError:
            raise
        except Exception as exc:
            raise FileContentMissingError() from exc

        return PreviewStream(
            stream=stream,
            media_type=media_type,
            size_bytes=size_bytes,
        )


async def retry_file_context(
    storage: DatabaseStorage,
    user_id: str,
    file_id: str,
) -> FileRecord:
    """Make a failed context job available for another processing attempt."""

    async with storage.session() as db:
        async with db.begin():
            file = await _get_file_row(db, user_id, file_id)
            job = await _context_job(db, user_id, file.sha256)
            if job is None:
                raise FileContextNotReadyError()
            job.status = "pending"
            job.attempts = 0
            job.available_at = _utc_now()
            job.lease_expires_at = None
            job.last_error = None
            job.updated_at = _utc_now()
            await db.flush()
            return _record(file, "pending")
