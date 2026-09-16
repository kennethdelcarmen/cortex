"""MCP transport placeholder route."""

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

router = APIRouter(tags=["mcp"])


@router.get("/mcp", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def mcp_placeholder() -> JSONResponse:
    """Make the deferred MCP transport state explicit to clients."""

    return JSONResponse(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        content={
            "code": "mcp_transport_not_configured",
            "message": "MCP transport is not configured yet.",
        },
    )
