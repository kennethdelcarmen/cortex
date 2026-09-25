"""HTTP adapters for the note service."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from ..attachments.errors import AttachmentError
from ..auth.service import CurrentAuth
from ..files.schemas import FileResponse
from ..files.service import FileRecord
from ..memory.errors import NoteError
from ..memory.schemas import (
    NoteCreateRequest,
    NoteListResponse,
    NoteResponse,
    NoteSummaryResponse,
    NoteTagSummaryResponse,
    NoteUpdateRequest,
)
from ..memory.service import (
    NoteListFilters,
    NoteRecord,
    create_note,
    delete_note,
    get_note,
    list_notes,
    restore_note,
    summarize_notes,
    update_note,
)
from ..storage import DatabaseStorage
from ..tags.errors import TagError
from .dependencies import get_current_auth, get_database_storage, require_csrf_auth

router = APIRouter(prefix="/api/v1/notes", tags=["notes"])


def _raise_http(error: NoteError | TagError | AttachmentError) -> None:
    detail: dict[str, object] = {"code": error.code, "message": error.message}
    for attribute in ("unknown_tags", "allowed_tags"):
        if hasattr(error, attribute):
            detail[attribute] = getattr(error, attribute)
    raise HTTPException(status_code=error.status_code, detail=detail) from error


def _file_response(record: FileRecord) -> FileResponse:
    return FileResponse(
        id=record.id,
        name=record.name,
        size_bytes=record.size_bytes,
        sha256=record.sha256,
        tags=record.tags,
        context_status=record.context_status,
        created_at=record.created_at,
        updated_at=record.updated_at,
        deleted_at=record.deleted_at,
    )


def _response(record: NoteRecord) -> NoteResponse:
    return NoteResponse(
        id=record.id,
        title=record.title,
        body=record.body,
        journal_date=record.journal_date,
        tags=record.tags,
        attachments=[_file_response(file) for file in record.attachments],
        created_at=record.created_at,
        updated_at=record.updated_at,
        deleted_at=record.deleted_at,
    )


@router.post("", response_model=NoteResponse, status_code=status.HTTP_201_CREATED)
async def create_note_route(
    payload: NoteCreateRequest,
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(require_csrf_auth)],
) -> NoteResponse:
    """Create one note for the authenticated owner."""

    try:
        record = await create_note(storage, auth.user.id, payload)
    except (NoteError, TagError, AttachmentError) as exc:
        _raise_http(exc)
    return _response(record)


@router.get("/summary", response_model=NoteSummaryResponse)
async def note_summary_route(
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(get_current_auth)],
) -> NoteSummaryResponse:
    """Return active note tag usage for the authenticated owner."""

    summary = await summarize_notes(storage, auth.user.id)
    return NoteSummaryResponse(
        tags=[
            NoteTagSummaryResponse(
                name=tag.name,
                count=tag.count,
                color=tag.color,
                active=tag.active,
            )
            for tag in summary.tags
        ]
    )


@router.get("", response_model=NoteListResponse)
async def list_notes_route(
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(get_current_auth)],
    tags: Annotated[list[str] | None, Query(alias="tag")] = None,
    search: Annotated[str | None, Query(max_length=200)] = None,
    journal_date_from: date | None = None,
    journal_date_to: date | None = None,
    include_deleted: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: str | None = None,
) -> NoteListResponse:
    """List owner-scoped notes with bounded cursor pagination."""

    try:
        page = await list_notes(
            storage,
            auth.user.id,
            NoteListFilters(
                tags=tuple(tags or ()),
                search=search,
                journal_date_from=journal_date_from,
                journal_date_to=journal_date_to,
                include_deleted=include_deleted,
                limit=limit,
                cursor=cursor,
            ),
        )
    except (NoteError, TagError, AttachmentError) as exc:
        _raise_http(exc)
    return NoteListResponse(
        items=[_response(record) for record in page.items],
        next_cursor=page.next_cursor,
    )


@router.get("/{note_id}", response_model=NoteResponse)
async def get_note_route(
    note_id: str,
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(get_current_auth)],
) -> NoteResponse:
    """Return one active note owned by the authenticated user."""

    try:
        record = await get_note(storage, auth.user.id, note_id)
    except (NoteError, TagError, AttachmentError) as exc:
        _raise_http(exc)
    return _response(record)


@router.patch("/{note_id}", response_model=NoteResponse)
async def update_note_route(
    note_id: str,
    payload: NoteUpdateRequest,
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(require_csrf_auth)],
) -> NoteResponse:
    """Apply a partial update to one active note."""

    try:
        record = await update_note(storage, auth.user.id, note_id, payload)
    except (NoteError, TagError, AttachmentError) as exc:
        _raise_http(exc)
    return _response(record)


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note_route(
    note_id: str,
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(require_csrf_auth)],
) -> Response:
    """Soft-delete one active note."""

    try:
        await delete_note(storage, auth.user.id, note_id)
    except (NoteError, TagError, AttachmentError) as exc:
        _raise_http(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{note_id}/restore", response_model=NoteResponse)
async def restore_note_route(
    note_id: str,
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(require_csrf_auth)],
) -> NoteResponse:
    """Restore one note, or return it unchanged when already active."""

    try:
        record = await restore_note(storage, auth.user.id, note_id)
    except (NoteError, TagError, AttachmentError) as exc:
        _raise_http(exc)
    return _response(record)
