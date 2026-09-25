"""HTTP adapters for the cross-domain recovery service."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth.service import CurrentAuth
from ..files.storage import FileBlobStore
from ..recovery.errors import RecoveryError
from ..recovery.schemas import (
    RecoveryBatchRequest,
    RecoveryItemResponse,
    RecoveryListResponse,
    RecoveryMutationResponse,
)
from ..recovery.service import RecoveryListFilters, list_recovery_items, mutate_recovery_items
from ..storage import DatabaseStorage
from .dependencies import (
    get_current_auth,
    get_database_storage,
    get_file_storage,
    require_csrf_auth,
)

router = APIRouter(prefix="/api/v1/recovery", tags=["recovery"])


def _raise_http(error: RecoveryError) -> None:
    raise HTTPException(
        status_code=error.status_code,
        detail={"code": error.code, "message": error.message},
    ) from error


@router.get("", response_model=RecoveryListResponse)
async def list_recovery_items_route(
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(get_current_auth)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: str | None = None,
) -> RecoveryListResponse:
    """List deleted and archived records across the owner-scoped domains."""

    try:
        page = await list_recovery_items(
            storage,
            auth.user.id,
            RecoveryListFilters(limit=limit, cursor=cursor),
        )
    except RecoveryError as exc:
        _raise_http(exc)
    return RecoveryListResponse(
        items=[
            RecoveryItemResponse(
                type=item.type,
                id=item.id,
                label=item.label,
                removed_at=item.removed_at,
                created_at=item.created_at,
            )
            for item in page.items
        ],
        next_cursor=page.next_cursor,
    )


@router.post("/restore", response_model=RecoveryMutationResponse)
async def restore_recovery_items_route(
    payload: RecoveryBatchRequest,
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    file_storage: Annotated[FileBlobStore, Depends(get_file_storage)],
    auth: Annotated[CurrentAuth, Depends(require_csrf_auth)],
) -> RecoveryMutationResponse:
    """Restore one or more deleted or archived records."""

    results = await mutate_recovery_items(
        storage,
        file_storage,
        auth.user.id,
        payload.items,
        permanent=False,
    )
    return RecoveryMutationResponse(results=results)


@router.post("/permanent-delete", response_model=RecoveryMutationResponse)
async def permanently_delete_recovery_items_route(
    payload: RecoveryBatchRequest,
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    file_storage: Annotated[FileBlobStore, Depends(get_file_storage)],
    auth: Annotated[CurrentAuth, Depends(require_csrf_auth)],
) -> RecoveryMutationResponse:
    """Permanently delete one or more deleted or archived records."""

    results = await mutate_recovery_items(
        storage,
        file_storage,
        auth.user.id,
        payload.items,
        permanent=True,
    )
    return RecoveryMutationResponse(results=results)
