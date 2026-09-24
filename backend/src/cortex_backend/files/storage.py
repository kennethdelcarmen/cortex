"""Filesystem blob storage for the owner-scoped file domain."""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import tempfile
import time
from collections.abc import AsyncIterable, AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from .errors import FileContentMissingError, FileStorageUnavailableError, FileTooLargeError

CHUNK_SIZE = 1024 * 1024
_RAW_STORAGE_KEY = re.compile(r"^[0-9a-f]{32}\.blob$")
_ARTIFACT_STORAGE_KEY = re.compile(r"^artifacts/[0-9a-f]{64}/[a-z0-9_-]+\.artifact$")


@dataclass(frozen=True)
class StoredBlob:
    """Integrity metadata calculated while bytes are written."""

    storage_key: str
    size_bytes: int
    sha256: str


@runtime_checkable
class FileBlobStore(Protocol):
    """Async boundary between file-domain metadata and byte storage."""

    async def check_ready(self) -> None:
        """Create the configured root and verify that it is writable."""

    async def write(
        self,
        storage_key: str,
        chunks: AsyncIterable[bytes],
        max_bytes: int,
    ) -> StoredBlob:
        """Write a bounded stream and atomically publish the object."""

    async def delete(self, storage_key: str) -> None:
        """Delete one object, treating an already-missing object as success."""

    async def stream(self, storage_key: str) -> AsyncIterator[bytes]:
        """Return a bounded-memory async iterator over one object."""


class LocalFileBlobStore:
    """Store opaque objects below one configured local application directory."""

    def __init__(self, root: Path) -> None:
        self._root = root

    @property
    def root(self) -> Path:
        """Return the configured object root for diagnostics and tests."""

        return self._root

    def _path(self, storage_key: str) -> Path:
        if not (
            _RAW_STORAGE_KEY.fullmatch(storage_key) or _ARTIFACT_STORAGE_KEY.fullmatch(storage_key)
        ):
            raise FileStorageUnavailableError()
        return self._root / storage_key

    async def check_ready(self) -> None:
        """Create the root, verify a write, and remove stale upload temporaries."""

        try:
            await asyncio.to_thread(self._check_ready_sync)
        except OSError as exc:
            raise FileStorageUnavailableError() from exc

    def _check_ready_sync(self) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        now = time.time()
        for temporary in self._root.glob(".upload-*"):
            try:
                if now - temporary.stat().st_mtime > 3600:
                    temporary.unlink(missing_ok=True)
            except FileNotFoundError:
                continue

        with tempfile.NamedTemporaryFile(dir=self._root, prefix=".ready-", delete=True) as handle:
            handle.write(b"ok")
            handle.flush()

    async def write(
        self,
        storage_key: str,
        chunks: AsyncIterable[bytes],
        max_bytes: int,
    ) -> StoredBlob:
        """Stream to a temporary object before atomically publishing the final key."""

        final_path = self._path(storage_key)
        final_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        size_bytes = 0
        digest = hashlib.sha256()
        handle = None

        try:
            temporary_file = tempfile.NamedTemporaryFile(
                dir=self._root,
                prefix=".upload-",
                suffix=".tmp",
                delete=False,
            )
            temporary_path = Path(temporary_file.name)
            handle = temporary_file
            async for chunk in chunks:
                if not chunk:
                    continue
                size_bytes += len(chunk)
                if size_bytes > max_bytes:
                    raise FileTooLargeError()
                digest.update(chunk)
                await asyncio.to_thread(handle.write, chunk)
            await asyncio.to_thread(handle.flush)
            await asyncio.to_thread(os.fsync, handle.fileno())
            await asyncio.to_thread(handle.close)
            handle = None
            await asyncio.to_thread(os.replace, temporary_path, final_path)
            temporary_path = None
            return StoredBlob(
                storage_key=storage_key,
                size_bytes=size_bytes,
                sha256=digest.hexdigest(),
            )
        except FileTooLargeError:
            raise
        except OSError as exc:
            raise FileStorageUnavailableError() from exc
        finally:
            if handle is not None:
                await asyncio.to_thread(handle.close)
            if temporary_path is not None:
                try:
                    await asyncio.to_thread(temporary_path.unlink, missing_ok=True)
                except FileNotFoundError:
                    pass

    async def delete(self, storage_key: str) -> None:
        """Remove an object without failing if it has already disappeared."""

        path = self._path(storage_key)
        try:
            await asyncio.to_thread(path.unlink)
        except FileNotFoundError:
            return
        except OSError as exc:
            raise FileStorageUnavailableError() from exc

    async def stream(self, storage_key: str) -> AsyncIterator[bytes]:
        """Open an object after checking it exists and stream it in chunks."""

        path = self._path(storage_key)
        try:
            await asyncio.to_thread(path.stat)
        except FileNotFoundError as exc:
            raise FileContentMissingError() from exc
        except OSError as exc:
            raise FileStorageUnavailableError() from exc

        async def iterator() -> AsyncIterator[bytes]:
            handle = None
            try:
                handle = await asyncio.to_thread(path.open, "rb")
                while True:
                    chunk = await asyncio.to_thread(handle.read, CHUNK_SIZE)
                    if not chunk:
                        break
                    yield chunk
            except FileNotFoundError as exc:
                raise FileContentMissingError() from exc
            except OSError as exc:
                raise FileStorageUnavailableError() from exc
            finally:
                if handle is not None:
                    await asyncio.to_thread(handle.close)

        return iterator()
