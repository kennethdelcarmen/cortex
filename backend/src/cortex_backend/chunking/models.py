"""SQLAlchemy models owned by the shared content-chunking domain."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..auth.models import Base


class ContentChunk(Base):
    """One deterministic, owner-scoped chunk of a source record."""

    __tablename__ = "content_chunks"
    __table_args__ = (
        CheckConstraint(
            "source_type IN ('note', 'task', 'file')",
            name="ck_content_chunks_source_type",
        ),
        Index(
            "ix_content_chunks_owner_source",
            "user_id",
            "source_type",
            "source_id",
            "ordinal",
        ),
        Index(
            "ix_content_chunks_owner_version",
            "user_id",
            "source_type",
            "source_version",
        ),
        UniqueConstraint(
            "user_id",
            "source_type",
            "source_id",
            "ordinal",
            name="uq_content_chunks_owner_source_ordinal",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_type: Mapped[str] = mapped_column(String(16), nullable=False)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source_version: Mapped[str] = mapped_column(String(64), nullable=False)
    source_title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
