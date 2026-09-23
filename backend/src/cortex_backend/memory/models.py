"""SQLAlchemy models owned by the memory domain."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..auth.models import Base


class Note(Base):
    """An owner-scoped sanitized HTML note or journal entry."""

    __tablename__ = "notes"
    __table_args__ = (
        Index(
            "ix_notes_owner_deleted_updated",
            "user_id",
            "deleted_at",
            "updated_at",
            "id",
        ),
        Index(
            "ix_notes_owner_deleted_journal",
            "user_id",
            "deleted_at",
            "journal_date",
            "updated_at",
            "id",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    journal_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class NoteTag(Base):
    """Many-to-many membership between notes and the shared owner tag catalog."""

    __tablename__ = "note_tags"
    __table_args__ = (Index("ix_note_tags_tag_id", "tag_id"),)

    note_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("notes.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tag_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tags.id", ondelete="CASCADE"),
        primary_key=True,
    )
