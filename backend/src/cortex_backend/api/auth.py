"""HTTP adapters for the authentication service."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from ..auth.errors import AuthError
from ..auth.security import (
    CSRF_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    validate_request_origin,
)
from ..auth.service import (
    AuthResult,
    CurrentAuth,
    McpApiKeyRecord,
    UserRecord,
    change_password,
    get_mcp_api_key,
    login,
    logout,
    refresh_csrf_token,
    replace_mcp_api_key,
    revoke_mcp_api_key,
    setup_owner,
    validate_setup_secret,
)
from ..auth.throttling import LoginThrottle
from ..config import Settings
from ..storage import DatabaseStorage
from .dependencies import (
    get_current_auth,
    get_database_storage,
    get_login_throttle,
    get_settings,
    require_csrf_auth,
)
from .schemas import (
    ChangePasswordRequest,
    CsrfResponse,
    LoginRequest,
    McpApiKeyResponse,
    McpApiKeyUpdateRequest,
    SetupRequest,
    UserResponse,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _raise_http(error: AuthError) -> None:
    raise HTTPException(
        status_code=error.status_code,
        detail={"code": error.code, "message": error.message},
    ) from error


def _user_response(user: UserRecord) -> UserResponse:
    return UserResponse(id=user.id, email=user.email, created_at=user.created_at)


def _set_auth_cookies(response: Response, result: AuthResult, settings: Settings) -> None:
    """Set the opaque session and readable CSRF cookies with safe defaults."""

    now = datetime.now(UTC)
    absolute = result.absolute_expires_at.replace(tzinfo=UTC)
    max_age = max(0, int((absolute - now).total_seconds()))
    secure = settings.environment == "production"
    response.set_cookie(
        SESSION_COOKIE_NAME,
        result.session_token,
        max_age=max_age,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE_NAME,
        result.csrf_token,
        max_age=max_age,
        httponly=False,
        secure=secure,
        samesite="lax",
        path="/",
    )


def _clear_auth_cookies(response: Response, settings: Settings) -> None:
    secure = settings.environment == "production"
    response.delete_cookie(SESSION_COOKIE_NAME, secure=secure, samesite="lax", path="/")
    response.delete_cookie(CSRF_COOKIE_NAME, secure=secure, samesite="lax", path="/")


def _mcp_api_key_response(record: McpApiKeyRecord | None) -> McpApiKeyResponse:
    if record is None:
        return McpApiKeyResponse(
            configured=False,
            revoked=False,
            created_at=None,
            updated_at=None,
            revoked_at=None,
        )
    return McpApiKeyResponse(
        configured=True,
        revoked=record.revoked_at is not None,
        created_at=record.created_at,
        updated_at=record.updated_at,
        revoked_at=record.revoked_at,
    )


def _validate_public_origin(request: Request, settings: Settings) -> None:
    """Translate invalid origins into the same stable CSRF response as protected routes."""

    try:
        validate_request_origin(request, settings, required=False)
    except AuthError as exc:
        _raise_http(exc)


@router.post("/setup/verify", status_code=status.HTTP_204_NO_CONTENT)
async def verify_setup_secret_route(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    """Verify the installation setup secret without creating an owner or session."""

    _validate_public_origin(request, settings)
    try:
        validate_setup_secret(settings, request.headers.get("x-setup-secret"))
    except AuthError as exc:
        _raise_http(exc)


@router.post("/setup", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def setup(
    request: Request,
    response: Response,
    payload: SetupRequest,
    settings: Annotated[Settings, Depends(get_settings)],
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
) -> UserResponse:
    """Create the first owner when the deployment setup secret is supplied."""

    _validate_public_origin(request, settings)
    try:
        result = await setup_owner(
            storage,
            settings,
            str(payload.email),
            payload.password,
            request.headers.get("x-setup-secret"),
            payload.mcp_api_key,
            payload.use_setup_secret_as_mcp_key,
        )
    except AuthError as exc:
        _raise_http(exc)
    _set_auth_cookies(response, result, settings)
    return _user_response(result.user)


@router.post("/login", response_model=UserResponse)
async def login_route(
    request: Request,
    response: Response,
    payload: LoginRequest,
    settings: Annotated[Settings, Depends(get_settings)],
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    throttle: Annotated[LoginThrottle, Depends(get_login_throttle)],
) -> UserResponse:
    """Authenticate with email and password and issue a fresh session."""

    _validate_public_origin(request, settings)
    client_host = request.client.host if request.client is not None else "unknown"
    try:
        result = await login(storage, throttle, payload.email, payload.password, client_host)
    except AuthError as exc:
        _raise_http(exc)
    _set_auth_cookies(response, result, settings)
    return _user_response(result.user)


@router.get("/me", response_model=UserResponse)
async def current_user(
    auth: Annotated[CurrentAuth, Depends(get_current_auth)],
) -> UserResponse:
    """Return the authenticated owner without exposing credential data."""

    return _user_response(auth.user)


@router.get("/csrf", response_model=CsrfResponse)
async def csrf_token(
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(get_current_auth)],
) -> CsrfResponse:
    """Rotate and return the readable CSRF token for the current session."""

    try:
        token = await refresh_csrf_token(storage, auth)
    except AuthError as exc:
        _raise_http(exc)
    response.set_cookie(
        CSRF_COOKIE_NAME,
        token,
        httponly=False,
        secure=settings.environment == "production",
        samesite="lax",
        path="/",
    )
    return CsrfResponse(csrf_token=token)


@router.get("/mcp-key", response_model=McpApiKeyResponse)
async def mcp_key_status(
    auth: Annotated[CurrentAuth, Depends(get_current_auth)],
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
) -> McpApiKeyResponse:
    """Return MCP key lifecycle metadata without exposing the key."""

    return _mcp_api_key_response(await get_mcp_api_key(storage, auth.user.id))


@router.put("/mcp-key", response_model=McpApiKeyResponse)
async def update_mcp_key(
    payload: McpApiKeyUpdateRequest,
    auth: Annotated[CurrentAuth, Depends(require_csrf_auth)],
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
) -> McpApiKeyResponse:
    """Create or rotate the static MCP bearer key."""

    try:
        record = await replace_mcp_api_key(storage, auth.user.id, payload.key)
    except AuthError as exc:
        _raise_http(exc)
    return _mcp_api_key_response(record)


@router.delete("/mcp-key", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mcp_key(
    auth: Annotated[CurrentAuth, Depends(require_csrf_auth)],
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
) -> None:
    """Revoke the static MCP bearer key without revoking browser sessions."""

    await revoke_mcp_api_key(storage, auth.user.id)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout_route(
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(require_csrf_auth)],
) -> None:
    """Revoke the current session and clear both browser cookies."""

    await logout(storage, auth)
    _clear_auth_cookies(response, settings)


@router.post("/password", response_model=UserResponse)
async def password_change(
    request: Request,
    response: Response,
    payload: ChangePasswordRequest,
    settings: Annotated[Settings, Depends(get_settings)],
    storage: Annotated[DatabaseStorage, Depends(get_database_storage)],
    auth: Annotated[CurrentAuth, Depends(require_csrf_auth)],
) -> UserResponse:
    """Change the password and rotate every session."""

    try:
        result = await change_password(
            storage,
            auth,
            payload.current_password,
            payload.new_password,
        )
    except AuthError as exc:
        _raise_http(exc)
    _set_auth_cookies(response, result, settings)
    return _user_response(result.user)
