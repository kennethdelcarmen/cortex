"""Owner-scoped file use cases over database metadata and blob storage."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from collections import defaultdict
from collections.abc import AsyncIterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

from sqlalchemy import and_, delete, exists, not_, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..storage import DatabaseStorage
from ..tags.service import existing_tag_names, resolve_tag_names
from ..tasks.models import Tag
from .errors import (
    FileContentMissingError,
    FileContextNotReadyError,
    FileError,
    FileMustBeDeletedError,
    FileNotFoundError,
    FilePreviewUnavailableError,
    FileStorageUnavailableError,
    InvalidFileCursorError,
    InvalidFileNameError,
    InvalidFileQueryError,
    InvalidFileTagError,
)
from .models import FILE_CONTEXT_VERSION, File, FileArtifact, FileContextJob, FileTag
from .schemas import FileContextStatus, FilePreviewKind, FileUpdateRequest
from .storage import FileBlobStore

DEFAULT_FILE_LIMIT = 50
MAX_FILE_LIMIT = 100
MAX_FILENAME_LENGTH = 255
MAX_CONTEXT_CHARACTERS = 100_000
DEFAULT_CONTEXT_CHARACTERS = 20_000
MAX_SEARCH_LENGTH = 200
MAX_FILE_TAGS = 20
_FILE_CONTEXT_STATUSES = frozenset({"pending", "processing", "ready", "unsupported", "failed"})
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
    tags: list[str]
    context_status: FileContextStatus
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


@dataclass(frozen=True)
class FileListFilters:
    """Filters for a bounded newest-first file query."""

    include_deleted: bool = False
    tags: tuple[str, ...] = ()
    search: str | None = None
    context_statuses: tuple[FileContextStatus, ...] = ()
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


def _record(
    file: File,
    context_status: FileContextStatus = "pending",
    tags: list[str] | None = None,
) -> FileRecord:
    return FileRecord(
        id=file.id,
        user_id=file.user_id,
        name=file.original_name,
        storage_key=file.storage_key,
        size_bytes=file.size_bytes,
        sha256=file.sha256,
        tags=tags or [],
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
        {
            "include_deleted": filters.include_deleted,
            "tags": list(filters.tags),
            "search": filters.search,
            "context_statuses": list(filters.context_statuses),
        },
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
    tags: dict[str, None] = {}
    for value in filters.tags:
        normalized = value.strip().casefold()
        if not normalized or len(normalized) > 64:
            raise InvalidFileQueryError()
        tags[normalized] = None

    search = None
    if filters.search is not None:
        search = " ".join(filters.search.strip().casefold().split())
        if not search:
            search = None
        elif len(search) > MAX_SEARCH_LENGTH:
            raise InvalidFileQueryError()

    statuses = tuple(dict.fromkeys(filters.context_statuses))
    if any(status not in _FILE_CONTEXT_STATUSES for status in statuses):
        raise InvalidFileQueryError()

    return FileListFilters(
        include_deleted=filters.include_deleted,
        tags=tuple(tags),
        search=search,
        context_statuses=statuses,
        limit=filters.limit,
        cursor=filters.cursor,
    )


def _fts_query(value: str | None) -> str | None:
    if value is None:
        return None
    tokens = re.findall(r"\w+", value, flags=re.UNICODE)
    if not tokens:
        return None
    return " AND ".join(f'"{token.replace(chr(34), chr(34) * 2)}"' for token in tokens)


async def _tags_for_files(db: AsyncSession, file_ids: list[str]) -> dict[str, list[str]]:
    if not file_ids:
        return {}
    result = await db.execute(
        select(FileTag.file_id, Tag.name)
        .join(Tag, Tag.id == FileTag.tag_id)
        .where(FileTag.file_id.in_(file_ids))
        .order_by(Tag.name.asc())
    )
    tags: dict[str, list[str]] = defaultdict(list)
    for file_id, name in result.all():
        tags[file_id].append(name)
    return tags


def _normalize_file_tag_names(values: list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
    if values is None:
        return ()
    normalized: dict[str, None] = {}
    for value in values:
        name = value.strip().casefold()
        if not name or len(name) > 64:
            raise InvalidFileTagError()
        normalized[name] = None
    if len(normalized) > MAX_FILE_TAGS:
        raise InvalidFileTagError()
    return tuple(normalized)


async def _replace_file_tags(
    db: AsyncSession,
    file_id: str,
    user_id: str,
    tag_names: list[str] | tuple[str, ...] | None,
) -> None:
    normalized_names = _normalize_file_tag_names(tag_names)
    retained_names = await existing_tag_names(db, FileTag, file_id)
    resolved = await resolve_tag_names(
        db,
        user_id,
        normalized_names,
        retain_inactive=retained_names,
    )
    await db.execute(delete(FileTag).where(FileTag.file_id == file_id))
    for name in normalized_names:
        db.add(FileTag(file_id=file_id, tag_id=resolved[name].id))
    await db.flush()


async def _sync_file_search_for_file(
    db: AsyncSession,
    file: File,
    *,
    content: str | None = None,
) -> None:
    """Refresh one file's FTS row while preserving existing extracted content by default."""

    if content is None:
        content = await db.scalar(
            text("SELECT content FROM files_fts WHERE file_id = :file_id"),
            {"file_id": file.id},
        )
        if content is None:
            content = ""
    tags = (await _tags_for_files(db, [file.id])).get(file.id, [])
    await db.execute(
        text("DELETE FROM files_fts WHERE file_id = :file_id"),
        {"file_id": file.id},
    )
    await db.execute(
        text(
            "INSERT INTO files_fts (file_id, name, content, tags) "
            "VALUES (:file_id, :name, :content, :tags)"
        ),
        {
            "file_id": file.id,
            "name": file.original_name,
            "content": content,
            "tags": " ".join(tags),
        },
    )


async def _sync_file_search_for_source(
    db: AsyncSession,
    user_id: str,
    source_sha256: str,
    content: str,
) -> None:
    files = list(
        (
            await db.scalars(
                select(File).where(File.user_id == user_id, File.sha256 == source_sha256)
            )
        ).all()
    )
    for file in files:
        await _sync_file_search_for_file(db, file, content=content)


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
                await _sync_file_search_for_file(db, file, content="")
                record = _record(file, "pending", [])
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
        tags = (await _tags_for_files(db, [file.id])).get(file.id, [])
        return _record(file, await _context_status(db, user_id, file.sha256), tags)


async def update_file(
    storage: DatabaseStorage,
    user_id: str,
    file_id: str,
    payload: FileUpdateRequest,
) -> FileRecord:
    """Replace one active file's shared catalog tags."""

    async with storage.session() as db:
        async with db.begin():
            file = await _get_file_row(db, user_id, file_id)
            await _replace_file_tags(db, file.id, user_id, payload.tags)
            await _sync_file_search_for_file(db, file)
            tags = (await _tags_for_files(db, [file.id])).get(file.id, [])
            return _record(file, await _context_status(db, user_id, file.sha256), tags)


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
        for tag_name in normalized.tags:
            statement = statement.where(
                exists(
                    select(FileTag.file_id)
                    .join(Tag, Tag.id == FileTag.tag_id)
                    .where(
                        FileTag.file_id == File.id,
                        Tag.user_id == user_id,
                        Tag.name == tag_name,
                    )
                )
            )
        if normalized.context_statuses:
            status_values = set(normalized.context_statuses)
            status_match = exists(
                select(FileContextJob.id).where(
                    FileContextJob.user_id == user_id,
                    FileContextJob.source_sha256 == File.sha256,
                    FileContextJob.extractor_version == FILE_CONTEXT_VERSION,
                    FileContextJob.status.in_(status_values),
                )
            )
            if "pending" in status_values:
                missing_job = not_(
                    exists(
                        select(FileContextJob.id).where(
                            FileContextJob.user_id == user_id,
                            FileContextJob.source_sha256 == File.sha256,
                            FileContextJob.extractor_version == FILE_CONTEXT_VERSION,
                        )
                    )
                )
                statement = statement.where(or_(status_match, missing_job))
            else:
                statement = statement.where(status_match)
        fts_query = _fts_query(normalized.search)
        if fts_query is not None:
            statement = statement.where(
                text(
                    "EXISTS (SELECT 1 FROM files_fts "
                    "WHERE files_fts.file_id = files.id "
                    "AND files_fts MATCH :fts_query)"
                ).bindparams(fts_query=fts_query)
            )
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
        tags_by_file = await _tags_for_files(db, [file.id for file in page_files])
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
                _record(
                    file,
                    status_by_hash.get(file.sha256, "pending"),
                    tags_by_file.get(file.id, []),
                )
                for file in page_files
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
            tags = (await _tags_for_files(db, [file.id])).get(file.id, [])
            return _record(file, await _context_status(db, user_id, file.sha256), tags)


async def permanently_delete_file(
    storage: DatabaseStorage,
    blob_store: FileBlobStore,
    user_id: str,
    file_id: str,
) -> None:
    """Permanently delete one deleted file and unreferenced derived objects."""

    async with storage.session() as db:
        async with db.begin():
            file = await _get_file_row(db, user_id, file_id, include_deleted=True)
            if file.deleted_at is None:
                raise FileMustBeDeletedError()

            other_reference = await db.scalar(
                select(File.id)
                .where(
                    File.user_id == user_id,
                    File.sha256 == file.sha256,
                    File.id != file.id,
                )
                .limit(1)
            )
            artifact_rows = []
            if other_reference is None:
                artifact_rows = list(
                    (
                        await db.scalars(
                            select(FileArtifact).where(
                                FileArtifact.user_id == user_id,
                                FileArtifact.source_sha256 == file.sha256,
                            )
                        )
                    ).all()
                )

            storage_keys = [file.storage_key]
            if other_reference is None:
                storage_keys.extend(artifact.storage_key for artifact in artifact_rows)
            for storage_key in storage_keys:
                await blob_store.delete(storage_key)

            if other_reference is None:
                await db.execute(
                    delete(FileArtifact).where(
                        FileArtifact.user_id == user_id,
                        FileArtifact.source_sha256 == file.sha256,
                    )
                )
                await db.execute(
                    delete(FileContextJob).where(
                        FileContextJob.user_id == user_id,
                        FileContextJob.source_sha256 == file.sha256,
                    )
                )
            await db.execute(
                text("DELETE FROM files_fts WHERE file_id = :file_id"),
                {"file_id": file.id},
            )
            await db.execute(delete(FileTag).where(FileTag.file_id == file.id))
            await db.delete(file)
            await db.flush()


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
            tags = (await _tags_for_files(db, [file.id])).get(file.id, [])
            return _record(file, "pending", tags)
