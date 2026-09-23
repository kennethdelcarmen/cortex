"""HTTP adapters for the shared tag catalog."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..auth.service import CurrentAuth
from ..storage import DatabaseStorage
from ..tags.errors import TagError
from ..tags.schemas import TagCreateRequest, TagListResponse, TagResponse, TagUpdateRequest
from ..tags.service import (
    TagRecord,
    archive_tag,
    create_tag,
    list_tags,
    permanently_delete_tag,
    restore_tag,
    update_tag,
)
from .dependencies import get_current_auth, get_database_storage, require_csrf_auth

router = APIRouter(prefix="/api/v1/tags", tags=["tags"])


def _raise_http(error: TagError) -> None:
    detail: dict[str, object] = {"code": error.code, "message": error.message}
    for attribute in ("unknown_tags", "allowed_tags"):
        if hasattr(error, attribute):
            detail[attribute] = getattr(error, attribute)
    raise HTTPException(status_code=error.status_code, detail=detail) from error


def _response(record: TagRecord) -> TagResponse:
    return TagResponse(
        id=record.id,
        name=record.name,
        color=record.color,
        active=record.active,
        created_at=record.created_at,
        archived_at=record.archived_at,
    )


@router.get("", response_model=TagListResponse)
async def list_tags_route(
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(get_current_auth)],
    include_inactive: Annotated[bool, Query()] = False,
) -> TagListResponse:
    records = await list_tags(storage, auth.user.id, include_inactive=include_inactive)
    return TagListResponse(items=[_response(record) for record in records])


@router.post("", response_model=TagResponse, status_code=status.HTTP_201_CREATED)
async def create_tag_route(
    payload: TagCreateRequest,
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(require_csrf_auth)],
) -> TagResponse:
    try:
        record = await create_tag(storage, auth.user.id, payload)
    except TagError as exc:
        _raise_http(exc)
    return _response(record)


@router.patch("/{tag_id}", response_model=TagResponse)
async def update_tag_route(
    tag_id: str,
    payload: TagUpdateRequest,
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(require_csrf_auth)],
) -> TagResponse:
    try:
        record = await update_tag(storage, auth.user.id, tag_id, payload)
    except TagError as exc:
        _raise_http(exc)
    return _response(record)


@router.delete("/{tag_id}/permanent", status_code=status.HTTP_204_NO_CONTENT)
async def permanently_delete_tag_route(
    tag_id: str,
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(require_csrf_auth)],
) -> None:
    try:
        await permanently_delete_tag(storage, auth.user.id, tag_id)
    except TagError as exc:
        _raise_http(exc)


@router.delete("/{tag_id}", response_model=TagResponse)
async def archive_tag_route(
    tag_id: str,
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(require_csrf_auth)],
) -> TagResponse:
    try:
        record = await archive_tag(storage, auth.user.id, tag_id)
    except TagError as exc:
        _raise_http(exc)
    return _response(record)


@router.post("/{tag_id}/restore", response_model=TagResponse)
async def restore_tag_route(
    tag_id: str,
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(require_csrf_auth)],
) -> TagResponse:
    try:
        record = await restore_tag(storage, auth.user.id, tag_id)
    except TagError as exc:
        _raise_http(exc)
    return _response(record)
