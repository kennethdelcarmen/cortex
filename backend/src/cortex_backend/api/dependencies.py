"""FastAPI dependency adapters for application-owned components."""

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from ..auth.errors import AuthError
from ..auth.security import validate_csrf, validate_request_origin
from ..auth.service import CurrentAuth, authenticate_session
from ..auth.throttling import LoginThrottle
from ..config import Settings
from ..files.storage import FileBlobStore
from ..storage import DatabaseStorage, Storage


def get_settings(request: Request) -> Settings:
    """Return settings from the application composition root."""

    return request.app.state.settings


def get_storage(request: Request) -> Storage:
    """Return storage from the application composition root."""

    return request.app.state.storage


def get_file_storage(request: Request) -> FileBlobStore:
    """Return the application-owned file byte store."""

    return request.app.state.file_storage


def get_database_storage(request: Request) -> DatabaseStorage:
    """Return the SQL-capable storage or a stable service-unavailable error."""

    storage = request.app.state.storage
    if not isinstance(storage, DatabaseStorage):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "database_storage_required",
                "message": "This operation requires persistent database storage.",
            },
        )
    return storage


def get_login_throttle(request: Request) -> LoginThrottle:
    """Return the process-local bounded login throttle."""

    return request.app.state.login_throttle


async def get_current_auth(
    request: Request,
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
) -> CurrentAuth:
    """Authenticate the opaque session cookie and refresh its idle expiry."""

    raw_token = request.cookies.get("cortex_session")
    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "unauthenticated", "message": "Authentication is required."},
        )

    try:
        return await authenticate_session(storage, raw_token)
    except AuthError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc


async def require_csrf_auth(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    auth: Annotated[CurrentAuth, Depends(get_current_auth)],
) -> CurrentAuth:
    """Require an authenticated browser request with valid origin and CSRF proof."""

    try:
        validate_request_origin(request, settings, required=True)
        validate_csrf(request, auth.csrf_token_hash)
    except AuthError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    return auth
