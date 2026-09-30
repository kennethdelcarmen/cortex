"""Persistence models and constants for local chunk embeddings."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..auth.models import Base

EMBEDDING_MODEL_NAME = "BAAI/bge-small-en-v1.5"
EMBEDDING_MODEL_VERSION = "v1"
EMBEDDING_DIMENSIONS = 384
EmbeddingStatus = Literal["pending", "processing", "ready", "failed"]


class ContentChunkEmbedding(Base):
    """Durable embedding-job state for one current content chunk."""

    __tablename__ = "content_chunk_embeddings"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'processing', 'ready', 'failed')",
            name="ck_content_chunk_embeddings_status",
        ),
        Index(
            "ix_content_chunk_embeddings_claim",
            "status",
            "available_at",
            "lease_expires_at",
        ),
        Index(
            "ix_content_chunk_embeddings_owner_status",
            "user_id",
            "status",
            "updated_at",
        ),
    )

    chunk_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("content_chunks.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_version: Mapped[str] = mapped_column(String(64), nullable=False)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    model_version: Mapped[str] = mapped_column(String(32), nullable=False)
    dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
