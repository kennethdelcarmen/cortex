"""Resumable command-line backfill for existing source chunks."""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings
from ..files.models import FILE_CONTEXT_VERSION, FileArtifact, FileContextJob
from ..files.storage import FileBlobStore, LocalFileBlobStore
from ..memory.models import Note
from ..storage import SQLiteStorage
from ..tasks.models import Task
from .service import ChunkSource, replace_source_chunks, source_version
from .text import html_to_chunk_text, normalize_source_text

BackfillSource = Literal["notes", "tasks", "files"]


@dataclass(frozen=True)
class BackfillProgress:
    """Committed backfill progress across each source family."""

    source: BackfillSource | None
    source_processed: int
    source_total: int
    processed_total: int
    total: int
    notes_processed: int
    notes_total: int
    tasks_processed: int
    tasks_total: int
    files_processed: int
    files_total: int

    @property
    def percentage(self) -> float:
        """Return aggregate completion percentage, including an empty run."""

        if self.total == 0:
            return 100.0
        return self.processed_total / self.total * 100


ProgressCallback = Callable[[BackfillProgress], None]


@dataclass
class _BackfillProgressReporter:
    totals: dict[BackfillSource, int]
    callback: ProgressCallback | None
    processed: dict[BackfillSource, int]

    @classmethod
    def create(
        cls,
        totals: dict[BackfillSource, int],
        callback: ProgressCallback | None,
    ) -> _BackfillProgressReporter:
        return cls(totals, callback, {source: 0 for source in totals})

    def emit(self, source: BackfillSource | None = None) -> None:
        if self.callback is None:
            return
        processed_total = sum(self.processed.values())
        total = sum(self.totals.values())
        source_processed = self.processed[source] if source is not None else 0
        source_total = self.totals[source] if source is not None else 0
        self.callback(
            BackfillProgress(
                source=source,
                source_processed=source_processed,
                source_total=source_total,
                processed_total=processed_total,
                total=total,
                notes_processed=self.processed["notes"],
                notes_total=self.totals["notes"],
                tasks_processed=self.processed["tasks"],
                tasks_total=self.totals["tasks"],
                files_processed=self.processed["files"],
                files_total=self.totals["files"],
            )
        )

    def add(self, source: BackfillSource, count: int) -> None:
        self.processed[source] += count
        self.emit(source)


async def _source_is_current(db: AsyncSession, source: ChunkSource) -> bool:
    """Return whether at least one row already represents this source version."""

    normalized = normalize_source_text(source.text)
    version = source_version(source, normalized)
    row = await db.scalar(
        text(
            "SELECT 1 FROM content_chunks "
            "WHERE user_id = :user_id AND source_type = :source_type "
            "AND source_id = :source_id AND source_version = :source_version "
            "LIMIT 1"
        ),
        {
            "user_id": source.user_id,
            "source_type": source.source_type,
            "source_id": source.source_id,
            "source_version": version,
        },
    )
    return bool(row)


async def _read_text_artifact(
    blob_store: FileBlobStore,
    storage_key: str,
) -> str:
    stream = await blob_store.stream(storage_key)
    raw = bytearray()
    async for chunk in stream:
        raw.extend(chunk)
    return bytes(raw).decode("utf-8", errors="replace")


async def _backfill_notes(
    storage: SQLiteStorage,
    batch_size: int,
    reporter: _BackfillProgressReporter,
) -> int:
    last_id = ""
    processed = 0
    while True:
        batch_count = 0
        async with storage.session() as db:
            async with db.begin():
                notes = list(
                    (
                        await db.scalars(
                            select(Note)
                            .where(Note.id > last_id)
                            .order_by(Note.id.asc())
                            .limit(batch_size)
                        )
                    ).all()
                )
                if not notes:
                    break
                for note in notes:
                    source = ChunkSource(
                        user_id=note.user_id,
                        source_type="note",
                        source_id=note.id,
                        title=note.title,
                        text="\n\n".join(
                            part
                            for part in (note.title or "", html_to_chunk_text(note.body))
                            if part
                        ),
                    )
                    if not await _source_is_current(db, source):
                        await replace_source_chunks(db, source)
                batch_count = len(notes)
                last_id = notes[-1].id
        processed += batch_count
        reporter.add("notes", batch_count)
    return processed


async def _backfill_tasks(
    storage: SQLiteStorage,
    batch_size: int,
    reporter: _BackfillProgressReporter,
) -> int:
    last_id = ""
    processed = 0
    while True:
        batch_count = 0
        async with storage.session() as db:
            async with db.begin():
                tasks = list(
                    (
                        await db.scalars(
                            select(Task)
                            .where(Task.id > last_id)
                            .order_by(Task.id.asc())
                            .limit(batch_size)
                        )
                    ).all()
                )
                if not tasks:
                    break
                for task in tasks:
                    source = ChunkSource(
                        user_id=task.user_id,
                        source_type="task",
                        source_id=task.id,
                        title=task.title,
                        text="\n\n".join(
                            part for part in (task.title, task.description or "") if part
                        ),
                    )
                    if not await _source_is_current(db, source):
                        await replace_source_chunks(db, source)
                batch_count = len(tasks)
                last_id = tasks[-1].id
        processed += batch_count
        reporter.add("tasks", batch_count)
    return processed


async def _backfill_files(
    storage: SQLiteStorage,
    blob_store: FileBlobStore,
    batch_size: int,
    reporter: _BackfillProgressReporter,
) -> int:
    last_user_id = ""
    last_source_hash = ""
    processed = 0
    while True:
        batch_count = 0
        async with storage.session() as db:
            async with db.begin():
                statement = select(FileContextJob).where(
                    FileContextJob.status == "ready",
                    FileContextJob.extractor_version == FILE_CONTEXT_VERSION,
                )
                if last_user_id:
                    statement = statement.where(
                        or_(
                            FileContextJob.user_id > last_user_id,
                            and_(
                                FileContextJob.user_id == last_user_id,
                                FileContextJob.source_sha256 > last_source_hash,
                            ),
                        )
                    )
                jobs = list(
                    (
                        await db.scalars(
                            statement.order_by(
                                FileContextJob.user_id.asc(),
                                FileContextJob.source_sha256.asc(),
                            ).limit(batch_size)
                        )
                    ).all()
                )
                if not jobs:
                    break
                for job in jobs:
                    artifact = await db.scalar(
                        select(FileArtifact).where(
                            FileArtifact.user_id == job.user_id,
                            FileArtifact.source_sha256 == job.source_sha256,
                            FileArtifact.artifact_kind == "text",
                            FileArtifact.extractor_version == job.extractor_version,
                        )
                    )
                    if artifact is not None:
                        source = ChunkSource(
                            user_id=job.user_id,
                            source_type="file",
                            source_id=job.source_sha256,
                            text=await _read_text_artifact(blob_store, artifact.storage_key),
                            version_salt=job.extractor_version,
                        )
                        if not await _source_is_current(db, source):
                            await replace_source_chunks(db, source)
                batch_count = len(jobs)
                last_user_id = jobs[-1].user_id
                last_source_hash = jobs[-1].source_sha256
        processed += batch_count
        reporter.add("files", batch_count)
    return processed


async def _backfill_totals(storage: SQLiteStorage) -> dict[BackfillSource, int]:
    async with storage.session() as db:
        return {
            "notes": int((await db.scalar(select(func.count()).select_from(Note))) or 0),
            "tasks": int((await db.scalar(select(func.count()).select_from(Task))) or 0),
            "files": int(
                (
                    await db.scalar(
                        select(func.count())
                        .select_from(FileContextJob)
                        .where(
                            FileContextJob.status == "ready",
                            FileContextJob.extractor_version == FILE_CONTEXT_VERSION,
                        )
                    )
                )
                or 0
            ),
        }


async def run_backfill(
    settings: Settings,
    batch_size: int,
    *,
    on_progress: ProgressCallback | None = None,
) -> tuple[int, int, int]:
    """Backfill notes, tasks, and ready file artifacts in committed batches."""

    if batch_size < 1 or batch_size > 1_000:
        raise ValueError("batch size must be between 1 and 1000")
    storage = SQLiteStorage(settings.database_path)
    blob_store = LocalFileBlobStore(settings.file_storage_path)
    try:
        await storage.check_ready()
        await blob_store.check_ready()
        reporter = _BackfillProgressReporter.create(
            await _backfill_totals(storage),
            on_progress,
        )
        reporter.emit()
        return (
            await _backfill_notes(storage, batch_size, reporter),
            await _backfill_tasks(storage, batch_size, reporter),
            await _backfill_files(storage, blob_store, batch_size, reporter),
        )
    finally:
        await storage.close()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Backfill Cortex content chunks.")
    parser.add_argument("--batch-size", type=int, default=100)
    return parser


def _source_percentage(processed: int, total: int) -> float:
    return 100.0 if total == 0 else processed / total * 100


def _print_progress(progress: BackfillProgress) -> None:
    source_status = " | ".join(
        (f"{label} {processed}/{total} ({_source_percentage(processed, total):.1f}%)")
        for label, processed, total in (
            ("notes", progress.notes_processed, progress.notes_total),
            ("tasks", progress.tasks_processed, progress.tasks_total),
            ("files", progress.files_processed, progress.files_total),
        )
    )
    print(
        f"backfill {source_status} | overall "
        f"{progress.processed_total}/{progress.total} ({progress.percentage:.1f}%)",
        flush=True,
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    counts = asyncio.run(run_backfill(Settings(), args.batch_size, on_progress=_print_progress))
    print(
        f"backfill complete: 100.0% | processed notes={counts[0]} "
        f"tasks={counts[1]} files={counts[2]}"
    )


if __name__ == "__main__":
    main()
