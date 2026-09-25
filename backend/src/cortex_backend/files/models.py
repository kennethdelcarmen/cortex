"""SQLAlchemy models owned by the file storage domain."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..auth.models import Base

FILE_CONTEXT_VERSION = "v1"


class File(Base):
    """Owner-scoped metadata for one opaque file object on local storage."""

    __tablename__ = "files"
    __table_args__ = (
        UniqueConstraint("storage_key", name="uq_files_storage_key"),
        Index(
            "ix_files_owner_deleted_created",
            "user_id",
            "deleted_at",
            "created_at",
            "id",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class FileTag(Base):
    """Many-to-many membership between files and the shared owner-scoped tag catalog."""

    __tablename__ = "file_tags"
    __table_args__ = (Index("ix_file_tags_tag_id", "tag_id"),)

    file_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("files.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tag_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tags.id", ondelete="CASCADE"),
        primary_key=True,
    )


class FileContextJob(Base):
    """Durable owner-scoped processing state shared by duplicate source bytes."""

    __tablename__ = "file_context_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'processing', 'ready', 'unsupported', 'failed')",
            name="ck_file_context_jobs_status",
        ),
        UniqueConstraint(
            "user_id",
            "source_sha256",
            "extractor_version",
            name="uq_file_context_jobs_owner_hash_version",
        ),
        Index(
            "ix_file_context_jobs_claim",
            "status",
            "available_at",
            "lease_expires_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(String(255), nullable=True)
    extractor_version: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class FileArtifact(Base):
    """Manifest for an immutable derived artifact stored beside source blobs."""

    __tablename__ = "file_artifacts"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "source_sha256",
            "artifact_kind",
            "extractor_version",
            name="uq_file_artifacts_owner_hash_kind_version",
        ),
        Index("ix_file_artifacts_owner_hash", "user_id", "source_sha256"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    extractor_version: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
