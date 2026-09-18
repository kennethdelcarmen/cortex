"""Authentication middleware for the mounted MCP transport."""

from contextvars import ContextVar

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from ..auth.errors import AuthError
from ..auth.service import CurrentAuth, authenticate_session
from ..storage import DatabaseStorage, Storage

_current_mcp_auth: ContextVar[CurrentAuth] = ContextVar("current_mcp_auth")


def get_mcp_auth() -> CurrentAuth:
    """Return the owner authenticated by the current MCP HTTP request."""

    try:
        return _current_mcp_auth.get()
    except LookupError as exc:
        raise RuntimeError("MCP authentication context is unavailable") from exc


class MCPAuthMiddleware:
    """Require an existing Cortex session token on every MCP HTTP request."""

    def __init__(self, app: ASGIApp, storage: Storage) -> None:
        self.app = app
        self.storage = storage

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        if not isinstance(self.storage, DatabaseStorage):
            await JSONResponse(
                status_code=503,
                content={
                    "code": "database_storage_required",
                    "message": "This operation requires persistent database storage.",
                },
            )(scope, receive, send)
            return

        request = Request(scope, receive)
        authorization = request.headers.get("authorization", "")
        scheme, _, token = authorization.partition(" ")
        if scheme.casefold() != "bearer" or not token:
            await JSONResponse(
                status_code=401,
                content={
                    "code": "unauthenticated",
                    "message": "Authentication is required.",
                },
            )(scope, receive, send)
            return

        try:
            auth = await authenticate_session(self.storage, token)
        except AuthError as exc:
            await JSONResponse(
                status_code=exc.status_code,
                content={"code": exc.code, "message": exc.message},
            )(scope, receive, send)
            return

        token_context = _current_mcp_auth.set(auth)
        try:
            await self.app(scope, receive, send)
        finally:
            _current_mcp_auth.reset(token_context)


def database_storage(storage: Storage | None) -> DatabaseStorage:
    """Narrow a generic storage dependency for MCP tools."""

    if not isinstance(storage, DatabaseStorage):
        raise RuntimeError("MCP tasks require persistent database storage")
    return storage
