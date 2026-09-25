"""Durable file-context processing and derived artifact generation."""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import signal
import tempfile
import zipfile
from collections.abc import AsyncIterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal
from uuid import uuid4
from xml.etree import ElementTree

from sqlalchemy import and_, or_, select

from ..config import Settings
from ..storage import DatabaseStorage
from .errors import FileError
from .models import FILE_CONTEXT_VERSION, File, FileArtifact, FileContextJob
from .service import (
    _IMAGE_EXTENSIONS,
    _OFFICE_EXTENSIONS,
    _RAW_TEXT_EXTENSIONS,
    _extension,
    _sync_file_search_for_source,
    _utc_now,
)
from .storage import FileBlobStore

logger = logging.getLogger(__name__)

MAX_DERIVED_BYTES = 100 * 1024 * 1024
DEFAULT_POLL_SECONDS = 1.0
DEFAULT_LEASE_SECONDS = 300
DEFAULT_MAX_ATTEMPTS = 3
MAX_DIAGNOSTIC_BYTES = 512
_CONVERTER_SEARCH_PATHS = (
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    "/opt/homebrew/bin/soffice",
    "/usr/local/bin/soffice",
    "/usr/bin/soffice",
)
_OCR_SEARCH_PATHS = (
    "/opt/homebrew/bin/tesseract",
    "/opt/local/bin/tesseract",
    "/usr/local/bin/tesseract",
    "/usr/bin/tesseract",
)
_ARCHIVE_OFFICE_EXTENSIONS = frozenset({"docx", "xlsx", "pptx", "odt", "ods", "odp"})
FileProcessingState = Literal["disabled", "starting", "healthy", "degraded", "stopped"]


class UnsupportedFileError(Exception):
    """The source format has no extractor in this pipeline."""


class ProcessingFailure(Exception):
    """A supported source could not be converted or extracted safely."""

    def __init__(self, code: str, *, retryable: bool = True) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


@dataclass
class FileProcessingHealth:
    """Mutable health snapshot owned by the application lifecycle."""

    enabled: bool
    state: FileProcessingState = "starting"
    last_success_at: datetime | None = None
    last_error: str | None = None
    warnings: tuple[str, ...] = ()
    worker_ready: bool = False

    def __post_init__(self) -> None:
        if not self.enabled:
            self.state = "disabled"

    @property
    def ready(self) -> bool:
        """Return whether the worker has completed at least one poll."""

        return not self.enabled or self.worker_ready

    def mark_started(self) -> None:
        """Mark the worker as running but not yet proven healthy."""

        if self.enabled:
            self.state = "starting"
            self.worker_ready = False

    def mark_success(self, warnings: tuple[str, ...] = ()) -> None:
        """Record a successful database/storage polling iteration."""

        if self.enabled:
            self.state = "degraded" if warnings else "healthy"
            self.worker_ready = True
            self.last_success_at = datetime.now(UTC)
            self.last_error = None
            self.warnings = warnings

    def mark_failure(self, error: BaseException) -> None:
        """Record an infrastructure failure without retaining exception details."""

        if self.enabled:
            self.state = "degraded"
            self.worker_ready = False
            self.last_error = type(error).__name__

    def mark_stopped(self) -> None:
        """Record an intentional worker shutdown."""

        if self.enabled:
            self.state = "stopped"
            self.worker_ready = False


def _resolve_executable(command: str, fallback_paths: tuple[str, ...]) -> str | None:
    """Resolve a configured executable without invoking a shell."""

    configured = Path(command).expanduser()
    if configured.is_absolute():
        return str(configured) if configured.is_file() and os.access(configured, os.X_OK) else None

    resolved = shutil.which(command)
    if resolved is not None:
        return resolved
    for candidate in fallback_paths:
        path = Path(candidate)
        if path.name != configured.name:
            continue
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    return None


def processing_warnings(settings: Settings) -> tuple[str, ...]:
    """Return stable capability warnings without exposing local paths."""

    warnings: list[str] = []
    if _resolve_executable(settings.file_converter_command, _CONVERTER_SEARCH_PATHS) is None:
        warnings.append("office_converter_unavailable")
    if _resolve_executable(settings.file_ocr_command, _OCR_SEARCH_PATHS) is None:
        warnings.append("ocr_unavailable")
    return tuple(warnings)


@dataclass(frozen=True)
class ClaimedJob:
    id: str
    user_id: str
    source_sha256: str
    attempts: int


@dataclass(frozen=True)
class ExtractedContext:
    text: bytes
    pdf: bytes | None = None


async def _bytes_chunks(value: bytes) -> AsyncIterable[bytes]:
    """Yield one bounded in-memory artifact payload."""

    yield value


async def _copy_chunks(path: Path) -> AsyncIterable[bytes]:
    """Yield a derived file in bounded chunks for atomic blob storage."""

    handle = await asyncio.to_thread(path.open, "rb")
    try:
        while True:
            chunk = await asyncio.to_thread(handle.read, 1024 * 1024)
            if not chunk:
                break
            yield chunk
    finally:
        await asyncio.to_thread(handle.close)


async def _materialize(
    blob_store: FileBlobStore,
    storage_key: str,
    directory: Path,
    suffix: str,
) -> Path:
    """Copy one source blob to a private temporary path."""

    path = directory / f"source{suffix}"
    stream = await blob_store.stream(storage_key)
    handle = await asyncio.to_thread(path.open, "wb")
    try:
        async for chunk in stream:
            await asyncio.to_thread(handle.write, chunk)
    finally:
        await asyncio.to_thread(handle.close)
    return path


async def _run_command(
    command: list[str],
    timeout_seconds: float,
    failure_code: str,
    *,
    missing_code: str,
) -> tuple[bytes, bytes]:
    """Run an extractor without a shell and with a hard timeout."""

    executable = _resolve_executable(command[0], ())
    if executable is None:
        logger.warning(
            "File processing executable unavailable",
            extra={"error_code": missing_code, "executable": Path(command[0]).name},
        )
        raise ProcessingFailure(missing_code, retryable=False)

    resolved_command = [executable, *command[1:]]
    process: asyncio.subprocess.Process | None = None
    try:
        process = await asyncio.create_subprocess_exec(
            *resolved_command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=os.name != "nt",
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout_seconds)
    except TimeoutError as exc:
        if process is not None and process.returncode is None:
            if os.name != "nt":
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            else:
                process.kill()
            await process.communicate()
        logger.warning(
            "File processing executable timed out",
            extra={"error_code": failure_code, "executable": Path(executable).name},
        )
        raise ProcessingFailure(failure_code) from exc
    except (FileNotFoundError, OSError) as exc:
        if process is not None and process.returncode is None:
            process.kill()
            await process.communicate()
        logger.warning(
            "File processing executable could not start",
            extra={"error_code": missing_code, "executable": Path(executable).name},
        )
        raise ProcessingFailure(missing_code, retryable=False) from exc
    if process.returncode != 0:
        diagnostic = stderr.decode("utf-8", errors="replace").strip()
        logger.warning(
            "File processing executable failed",
            extra={
                "error_code": failure_code,
                "executable": Path(executable).name,
                "return_code": process.returncode,
                "stderr": diagnostic[:MAX_DIAGNOSTIC_BYTES],
            },
        )
        raise ProcessingFailure(failure_code)
    return stdout, stderr


def _normalize_text(value: str) -> bytes:
    """Normalize extracted text to a stable UTF-8 representation."""

    return value.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def _xml_text(path: str, names: set[str] | None = None) -> list[str]:
    """Read text nodes from one XML document while preserving document order."""

    root = ElementTree.fromstring(path)
    values: list[str] = []
    for element in root.iter():
        local_name = element.tag.rsplit("}", maxsplit=1)[-1]
        if names is not None and local_name not in names:
            continue
        if element.text and element.text.strip():
            values.append(element.text.strip())
    return values


def _archive_member(archive: zipfile.ZipFile, name: str) -> str:
    """Decode one bounded XML member from an Office archive."""

    return archive.read(name).decode("utf-8", errors="replace")


def _extract_docx_text(archive: zipfile.ZipFile) -> str:
    members = sorted(
        name
        for name in archive.namelist()
        if name.startswith("word/")
        and name.endswith(".xml")
        and "/_rels/" not in name
        and not name.startswith("word/theme/")
        and not name.startswith("word/styles")
    )
    values: list[str] = []
    for name in members:
        values.extend(_xml_text(_archive_member(archive, name), {"t"}))
    return "\n".join(values)


def _extract_xlsx_text(archive: zipfile.ZipFile) -> str:
    shared: list[str] = []
    if "xl/sharedStrings.xml" in archive.namelist():
        shared = _xml_text(_archive_member(archive, "xl/sharedStrings.xml"), {"t"})

    rows: list[str] = []
    for name in sorted(archive.namelist()):
        if not name.startswith("xl/worksheets/sheet") or not name.endswith(".xml"):
            continue
        root = ElementTree.fromstring(_archive_member(archive, name))
        for row in root.iter():
            if row.tag.rsplit("}", maxsplit=1)[-1] != "row":
                continue
            cells: list[str] = []
            for cell in row:
                if cell.tag.rsplit("}", maxsplit=1)[-1] != "c":
                    continue
                cell_type = cell.attrib.get("t")
                value = next(
                    (
                        child.text
                        for child in cell.iter()
                        if child is not cell
                        if child.tag.rsplit("}", maxsplit=1)[-1] in {"v", "t"} and child.text
                    ),
                    "",
                )
                if cell_type == "s" and value.isdigit():
                    index = int(value)
                    value = shared[index] if index < len(shared) else ""
                cells.append(value.strip())
            if any(cells):
                rows.append("\t".join(cells))
    return "\n".join(rows)


def _extract_pptx_text(archive: zipfile.ZipFile) -> str:
    values: list[str] = []
    for name in sorted(archive.namelist()):
        if name.startswith("ppt/slides/slide") and name.endswith(".xml"):
            values.extend(_xml_text(_archive_member(archive, name), {"t"}))
    return "\n".join(values)


def _extract_odf_text(archive: zipfile.ZipFile) -> str:
    if "content.xml" not in archive.namelist():
        raise ProcessingFailure("office_text_extraction_failed", retryable=False)
    values = _xml_text(_archive_member(archive, "content.xml"))
    return "\n".join(values)


def _extract_office_text_sync(source: Path, extension: str) -> bytes:
    """Extract text from archive-based Office formats without LibreOffice."""

    if extension not in _ARCHIVE_OFFICE_EXTENSIONS:
        raise ProcessingFailure("office_text_fallback_unavailable", retryable=False)
    try:
        with zipfile.ZipFile(source) as archive:
            text = {
                "docx": _extract_docx_text,
                "xlsx": _extract_xlsx_text,
                "pptx": _extract_pptx_text,
                "odt": _extract_odf_text,
                "ods": _extract_odf_text,
                "odp": _extract_odf_text,
            }[extension](archive)
    except ProcessingFailure:
        raise
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
        raise ProcessingFailure("office_text_extraction_failed", retryable=False) from exc
    return _normalize_text(text)


async def _extract_pdf_text(path: Path) -> bytes:
    """Extract text from a PDF using the backend's PDF parser."""

    try:
        from pypdf import PdfReader

        reader = await asyncio.to_thread(PdfReader, str(path))
        pages = await asyncio.gather(
            *(asyncio.to_thread(page.extract_text) for page in reader.pages)
        )
    except Exception as exc:
        raise ProcessingFailure("pdf_text_extraction_failed") from exc
    return _normalize_text("\n\n".join(page or "" for page in pages))


async def _convert_office_to_pdf(path: Path, directory: Path, settings: Settings) -> Path:
    """Convert an Office-family source to an isolated PDF artifact."""

    executable = _resolve_executable(settings.file_converter_command, _CONVERTER_SEARCH_PATHS)
    if executable is None:
        raise ProcessingFailure("office_converter_unavailable", retryable=False)
    output_dir = directory / "converted"
    output_dir.mkdir()
    profile_dir = directory / "libreoffice-profile"
    profile_dir.mkdir()
    await _run_command(
        [
            executable,
            "--headless",
            "--nologo",
            "--nodefault",
            "--nolockcheck",
            "--norestore",
            f"-env:UserInstallation={profile_dir.as_uri()}",
            "--convert-to",
            "pdf",
            "--outdir",
            str(output_dir),
            str(path),
        ],
        settings.file_processing_timeout_seconds,
        "office_conversion_failed",
        missing_code="office_converter_unavailable",
    )
    converted = output_dir / f"{path.stem}.pdf"
    if not converted.is_file():
        raise ProcessingFailure("office_conversion_failed")
    return converted


async def _extract_source(
    source: Path,
    extension: str,
    directory: Path,
    settings: Settings,
) -> ExtractedContext:
    """Select an extractor from the immutable filename extension."""

    if extension in _RAW_TEXT_EXTENSIONS:
        content = await asyncio.to_thread(source.read_bytes)
        return ExtractedContext(text=_normalize_text(content.decode("utf-8", errors="replace")))

    if extension == "pdf":
        return ExtractedContext(text=await _extract_pdf_text(source))

    if extension in _OFFICE_EXTENSIONS:
        try:
            pdf = await _convert_office_to_pdf(source, directory, settings)
            return ExtractedContext(
                text=await _extract_pdf_text(pdf),
                pdf=await asyncio.to_thread(pdf.read_bytes),
            )
        except ProcessingFailure as conversion_error:
            if extension not in _ARCHIVE_OFFICE_EXTENSIONS:
                raise
            try:
                text = await asyncio.to_thread(_extract_office_text_sync, source, extension)
            except ProcessingFailure as fallback_error:
                raise conversion_error from fallback_error
            logger.warning(
                "Office PDF preview unavailable; using text fallback",
                extra={"extension": extension, "error_code": conversion_error.code},
            )
            return ExtractedContext(text=text)

    if extension in _IMAGE_EXTENSIONS:
        executable = _resolve_executable(settings.file_ocr_command, _OCR_SEARCH_PATHS)
        if executable is None:
            raise ProcessingFailure("ocr_unavailable", retryable=False)
        stdout, _ = await _run_command(
            [executable, str(source), "stdout", "-l", settings.file_ocr_language],
            settings.file_processing_timeout_seconds,
            "image_ocr_failed",
            missing_code="ocr_unavailable",
        )
        return ExtractedContext(text=_normalize_text(stdout.decode("utf-8", errors="replace")))

    raise UnsupportedFileError()


async def _claim_job(
    storage: DatabaseStorage,
    lease_seconds: int,
) -> ClaimedJob | None:
    """Claim one ready or abandoned job using a short database transaction."""

    now = _utc_now()
    async with storage.session() as db:
        async with db.begin():
            statement = (
                select(FileContextJob)
                .where(
                    or_(
                        and_(
                            FileContextJob.status == "pending",
                            FileContextJob.available_at <= now,
                        ),
                        and_(
                            FileContextJob.status == "processing",
                            FileContextJob.lease_expires_at.is_not(None),
                            FileContextJob.lease_expires_at < now,
                        ),
                    )
                )
                .order_by(FileContextJob.available_at.asc(), FileContextJob.created_at.asc())
                .limit(1)
            )
            job = await db.scalar(statement)
            if job is None:
                return None
            job.status = "processing"
            job.attempts += 1
            job.lease_expires_at = now + timedelta(seconds=lease_seconds)
            job.updated_at = now
            await db.flush()
            logger.info(
                "File context job claimed",
                extra={"job_id": job.id, "attempt": job.attempts},
            )
            return ClaimedJob(job.id, job.user_id, job.source_sha256, job.attempts)


async def _source_for_job(
    storage: DatabaseStorage,
    job: ClaimedJob,
) -> File | None:
    async with storage.session() as db:
        return await db.scalar(
            select(File)
            .where(File.user_id == job.user_id, File.sha256 == job.source_sha256)
            .order_by(File.deleted_at.is_(None).desc(), File.created_at.asc())
            .limit(1)
        )


async def _write_artifact(
    blob_store: FileBlobStore,
    user_id: str,
    source_sha256: str,
    kind: str,
    payload: bytes | Path,
    max_bytes: int,
) -> tuple[str, int, str]:
    """Atomically write one content-addressed derived artifact."""

    storage_key = f"artifacts/{source_sha256}/{kind}-{FILE_CONTEXT_VERSION}.artifact"
    chunks = _bytes_chunks(payload) if isinstance(payload, bytes) else _copy_chunks(payload)
    stored = await blob_store.write(storage_key, chunks, max_bytes)
    return stored.storage_key, stored.size_bytes, stored.sha256


async def _finish_job(
    storage: DatabaseStorage,
    job: ClaimedJob,
    extracted: ExtractedContext,
    blob_store: FileBlobStore,
    max_bytes: int,
) -> None:
    artifacts: list[tuple[str, str, int, str]] = []
    text_key, text_size, text_hash = await _write_artifact(
        blob_store,
        job.user_id,
        job.source_sha256,
        "text",
        extracted.text,
        max_bytes,
    )
    artifacts.append(("text", text_key, text_size, text_hash))
    if extracted.pdf is not None:
        pdf_key, pdf_size, pdf_hash = await _write_artifact(
            blob_store,
            job.user_id,
            job.source_sha256,
            "pdf",
            extracted.pdf,
            max_bytes,
        )
        artifacts.append(("pdf", pdf_key, pdf_size, pdf_hash))

    now = _utc_now()
    async with storage.session() as db:
        async with db.begin():
            for kind, key, size, digest in artifacts:
                existing = await db.scalar(
                    select(FileArtifact).where(
                        FileArtifact.user_id == job.user_id,
                        FileArtifact.source_sha256 == job.source_sha256,
                        FileArtifact.artifact_kind == kind,
                        FileArtifact.extractor_version == FILE_CONTEXT_VERSION,
                    )
                )
                if existing is None:
                    db.add(
                        FileArtifact(
                            id=str(uuid4()),
                            user_id=job.user_id,
                            source_sha256=job.source_sha256,
                            artifact_kind=kind,
                            storage_key=key,
                            size_bytes=size,
                            sha256=digest,
                            extractor_version=FILE_CONTEXT_VERSION,
                            created_at=now,
                        )
                    )
            stored_job = await db.scalar(
                select(FileContextJob).where(FileContextJob.id == job.id).limit(1)
            )
            if stored_job is not None:
                stored_job.status = "ready"
                stored_job.lease_expires_at = None
                stored_job.last_error = None
                stored_job.updated_at = now
            await db.flush()
            await _sync_file_search_for_source(
                db,
                job.user_id,
                job.source_sha256,
                extracted.text.decode("utf-8", errors="replace"),
            )


async def _mark_job(
    storage: DatabaseStorage,
    job: ClaimedJob,
    status: str,
    error: str | None,
    max_attempts: int,
    *,
    retryable: bool = True,
) -> None:
    now = _utc_now()
    async with storage.session() as db:
        async with db.begin():
            stored_job = await db.scalar(
                select(FileContextJob).where(FileContextJob.id == job.id).limit(1)
            )
            if stored_job is None:
                return
            stored_job.lease_expires_at = None
            stored_job.last_error = error
            if status == "failed" and retryable and stored_job.attempts < max_attempts:
                stored_job.status = "pending"
                stored_job.available_at = now + timedelta(seconds=min(60, 2**stored_job.attempts))
            else:
                stored_job.status = status
                stored_job.available_at = now
            stored_job.updated_at = now
            await db.flush()


async def process_file_context_once(
    storage: DatabaseStorage,
    blob_store: FileBlobStore,
    settings: Settings,
) -> bool:
    """Process at most one queued context job."""

    job = await _claim_job(storage, settings.file_processing_lease_seconds)
    if job is None:
        return False
    source = await _source_for_job(storage, job)
    if source is None:
        await _mark_job(
            storage,
            job,
            "failed",
            "source_missing",
            settings.file_processing_max_attempts,
        )
        return True

    extension = _extension(source.original_name)
    try:
        with tempfile.TemporaryDirectory(prefix="cortex-file-") as temporary:
            directory = Path(temporary)
            source_path = await _materialize(
                blob_store,
                source.storage_key,
                directory,
                f".{extension}" if extension else ".bin",
            )
            extracted = await _extract_source(source_path, extension, directory, settings)
            if len(extracted.text) > MAX_DERIVED_BYTES:
                raise ProcessingFailure("derived_context_too_large")
            if extracted.pdf is not None and len(extracted.pdf) > MAX_DERIVED_BYTES:
                raise ProcessingFailure("derived_preview_too_large")
            await _finish_job(
                storage,
                job,
                extracted,
                blob_store,
                MAX_DERIVED_BYTES,
            )
    except UnsupportedFileError:
        await _mark_job(
            storage,
            job,
            "unsupported",
            "unsupported_file_type",
            settings.file_processing_max_attempts,
        )
    except (ProcessingFailure, FileError) as exc:
        error = exc.code if isinstance(exc, ProcessingFailure) else exc.code
        await _mark_job(
            storage,
            job,
            "failed",
            error,
            settings.file_processing_max_attempts,
            retryable=not isinstance(exc, ProcessingFailure) or exc.retryable,
        )
    except Exception:
        logger.exception("Unexpected file context processing failure")
        await _mark_job(
            storage,
            job,
            "failed",
            "processing_failed",
            settings.file_processing_max_attempts,
        )
    logger.info("File context job processed", extra={"job_id": job.id})
    return True


async def run_file_processing_loop(
    storage: DatabaseStorage,
    blob_store: FileBlobStore,
    settings: Settings,
    health: FileProcessingHealth | None = None,
) -> None:
    """Run the restart-safe local worker until application shutdown."""

    if health is not None:
        health.mark_started()
    logger.info("File context worker started")
    try:
        while True:
            try:
                processed = await process_file_context_once(storage, blob_store, settings)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if health is not None:
                    health.mark_failure(exc)
                logger.exception("File context worker poll failed; retrying")
                await asyncio.sleep(settings.file_processing_poll_seconds)
                continue

            if health is not None:
                health.mark_success(processing_warnings(settings))
            logger.debug("File context worker poll succeeded", extra={"processed": processed})
            if not processed:
                await asyncio.sleep(settings.file_processing_poll_seconds)
    except asyncio.CancelledError:
        if health is not None:
            health.mark_stopped()
        logger.info("File context worker stopped")
        raise
