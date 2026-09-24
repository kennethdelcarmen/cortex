"""HTTP adapters for the owner-scoped file storage service."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated
from urllib.parse import quote

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from fastapi import File as UploadFileField
from fastapi.responses import StreamingResponse

from ..auth.service import CurrentAuth
from ..config import Settings
from ..files.errors import FileError
from ..files.schemas import FileContextResponse, FileListResponse, FileResponse
from ..files.service import (
    FileContextRecord,
    FileListFilters,
    FileRecord,
    create_file,
    delete_file,
    get_file,
    get_file_context,
    list_files,
    restore_file,
    retry_file_context,
    stream_file,
    stream_preview,
)
from ..files.storage import FileBlobStore
from ..storage import DatabaseStorage
from .dependencies import (
    get_current_auth,
    get_database_storage,
    get_file_storage,
    get_settings,
    require_csrf_auth,
)

router = APIRouter(prefix="/api/v1/files", tags=["files"])


def _raise_http(error: FileError) -> None:
    raise HTTPException(
        status_code=error.status_code,
        detail={"code": error.code, "message": error.message},
    ) from error


def _response(record: FileRecord) -> FileResponse:
    return FileResponse(
        id=record.id,
        name=record.name,
        size_bytes=record.size_bytes,
        sha256=record.sha256,
        context_status=record.context_status,
        created_at=record.created_at,
        updated_at=record.updated_at,
        deleted_at=record.deleted_at,
    )


def _context_response(record: FileContextRecord) -> FileContextResponse:
    return FileContextResponse(
        file_id=record.file_id,
        name=record.name,
        status=record.status,
        text=record.text,
        truncated=record.truncated,
        preview_kind=record.preview_kind,
        error=record.error,
        processed_at=record.processed_at,
    )


async def _upload_chunks(upload: UploadFile) -> AsyncIterator[bytes]:
    """Read multipart content incrementally so the service can enforce its limit."""

    while True:
        chunk = await upload.read(1024 * 1024)
        if not chunk:
            return
        yield chunk


def _content_disposition(filename: str, *, inline: bool = False) -> str:
    """Build a safe attachment header with an ASCII fallback and UTF-8 name."""

    fallback = "".join(
        character if 32 <= ord(character) < 127 and character not in {'"', "\\"} else "_"
        for character in filename
    )
    disposition = "inline" if inline else "attachment"
    return f"{disposition}; filename=\"{fallback}\"; filename*=UTF-8''{quote(filename, safe='')}"


@router.post("", response_model=FileResponse, status_code=status.HTTP_201_CREATED)
async def upload_file_route(
    file: Annotated[UploadFile, UploadFileField(...)],
    settings: Annotated[Settings, Depends(get_settings)],
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    file_storage: Annotated[FileBlobStore, Depends(get_file_storage)],
    auth: Annotated[CurrentAuth, Depends(require_csrf_auth)],
) -> FileResponse:
    """Upload one opaque file for the authenticated owner."""

    try:
        record = await create_file(
            storage,
            file_storage,
            auth.user.id,
            file.filename,
            _upload_chunks(file),
            settings.file_max_size_bytes,
        )
    except FileError as exc:
        _raise_http(exc)
    finally:
        await file.close()
    return _response(record)


@router.get("", response_model=FileListResponse)
async def list_files_route(
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(get_current_auth)],
    include_deleted: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: str | None = None,
) -> FileListResponse:
    """List owner-scoped files with bounded cursor pagination."""

    try:
        page = await list_files(
            storage,
            auth.user.id,
            FileListFilters(include_deleted=include_deleted, limit=limit, cursor=cursor),
        )
    except FileError as exc:
        _raise_http(exc)
    return FileListResponse(
        items=[_response(record) for record in page.items],
        next_cursor=page.next_cursor,
    )


@router.get("/{file_id}/content")
async def download_file_route(
    file_id: str,
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    file_storage: Annotated[FileBlobStore, Depends(get_file_storage)],
    auth: Annotated[CurrentAuth, Depends(get_current_auth)],
) -> StreamingResponse:
    """Stream one active file as an attachment."""

    try:
        record, stream = await stream_file(storage, file_storage, auth.user.id, file_id)
    except FileError as exc:
        _raise_http(exc)
    return StreamingResponse(
        stream,
        media_type="application/octet-stream",
        headers={
            "Content-Length": str(record.size_bytes),
            "Content-Disposition": _content_disposition(record.name),
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/{file_id}/preview", response_model=FileContextResponse)
async def preview_file_route(
    file_id: str,
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    file_storage: Annotated[FileBlobStore, Depends(get_file_storage)],
    auth: Annotated[CurrentAuth, Depends(get_current_auth)],
    max_characters: Annotated[int, Query(ge=1, le=100_000)] = 20_000,
) -> FileContextResponse:
    """Return bounded derived context and preview state."""

    try:
        record = await get_file_context(
            storage,
            file_storage,
            auth.user.id,
            file_id,
            max_characters,
        )
    except FileError as exc:
        _raise_http(exc)
    return _context_response(record)


@router.get("/{file_id}/preview/content")
async def preview_content_route(
    file_id: str,
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    file_storage: Annotated[FileBlobStore, Depends(get_file_storage)],
    auth: Annotated[CurrentAuth, Depends(get_current_auth)],
) -> StreamingResponse:
    """Stream a safe derived preview representation."""

    try:
        preview = await stream_preview(storage, file_storage, auth.user.id, file_id)
        record = await get_file(storage, auth.user.id, file_id)
    except FileError as exc:
        _raise_http(exc)
    return StreamingResponse(
        preview.stream,
        media_type=preview.media_type,
        headers={
            "Content-Length": str(preview.size_bytes),
            "Content-Disposition": _content_disposition(record.name, inline=True),
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/{file_id}", response_model=FileResponse)
async def get_file_route(
    file_id: str,
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(get_current_auth)],
) -> FileResponse:
    """Return one active file's metadata."""

    try:
        record = await get_file(storage, auth.user.id, file_id)
    except FileError as exc:
        _raise_http(exc)
    return _response(record)


@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_file_route(
    file_id: str,
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(require_csrf_auth)],
) -> Response:
    """Soft-delete one active file."""

    try:
        await delete_file(storage, auth.user.id, file_id)
    except FileError as exc:
        _raise_http(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{file_id}/restore", response_model=FileResponse)
async def restore_file_route(
    file_id: str,
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(require_csrf_auth)],
) -> FileResponse:
    """Restore one deleted file."""

    try:
        record = await restore_file(storage, auth.user.id, file_id)
    except FileError as exc:
        _raise_http(exc)
    return _response(record)


@router.post("/{file_id}/processing/retry", response_model=FileResponse)
async def retry_file_processing_route(
    file_id: str,
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(require_csrf_auth)],
) -> FileResponse:
    """Retry processing for one active source."""

    try:
        record = await retry_file_context(storage, auth.user.id, file_id)
    except FileError as exc:
        _raise_http(exc)
    return _response(record)
