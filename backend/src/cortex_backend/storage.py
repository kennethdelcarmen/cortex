"""Persistence contracts and the deterministic bootstrap adapter."""

from typing import Protocol


class Storage(Protocol):
    """Minimal persistence boundary required by the application scaffold."""

    async def check_ready(self) -> None:
        """Raise when the backing store cannot serve requests."""


class InMemoryStorage:
    """No-op storage adapter used until the first persisted domain feature."""

    async def check_ready(self) -> None:
        """Report the in-memory adapter as ready."""
