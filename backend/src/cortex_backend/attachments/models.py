"""SQLAlchemy models for reusable file links."""

from __future__ import annotations

from sqlalchemy import ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..auth.models import Base


class NoteFile(Base):
    """An ordered link between a note and an owner-scoped file."""

    __tablename__ = "note_files"
    __table_args__ = (
        UniqueConstraint("note_id", "position", name="uq_note_files_position"),
        Index("ix_note_files_file_id", "file_id"),
        Index("ix_note_files_note_position", "note_id", "position"),
    )

    note_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("notes.id", ondelete="CASCADE"),
        primary_key=True,
    )
    file_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("files.id", ondelete="CASCADE"),
        primary_key=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)


class TaskFile(Base):
    """An ordered link between a concrete task occurrence and a file."""

    __tablename__ = "task_files"
    __table_args__ = (
        UniqueConstraint("task_id", "position", name="uq_task_files_position"),
        Index("ix_task_files_file_id", "file_id"),
        Index("ix_task_files_task_position", "task_id", "position"),
    )

    task_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        primary_key=True,
    )
    file_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("files.id", ondelete="CASCADE"),
        primary_key=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)


class TaskSeriesFile(Base):
    """An ordered default attachment link for a recurring task series."""

    __tablename__ = "task_series_files"
    __table_args__ = (
        UniqueConstraint("series_id", "position", name="uq_task_series_files_position"),
        Index("ix_task_series_files_file_id", "file_id"),
        Index("ix_task_series_files_series_position", "series_id", "position"),
    )

    series_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("task_series.id", ondelete="CASCADE"),
        primary_key=True,
    )
    file_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("files.id", ondelete="CASCADE"),
        primary_key=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
