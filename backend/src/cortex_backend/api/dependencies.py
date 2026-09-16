"""FastAPI dependency adapters for application-owned components."""

from fastapi import Request

from ..config import Settings
from ..storage import Storage


def get_settings(request: Request) -> Settings:
    """Return settings from the application composition root."""

    return request.app.state.settings


def get_storage(request: Request) -> Storage:
    """Return storage from the application composition root."""

    return request.app.state.storage
