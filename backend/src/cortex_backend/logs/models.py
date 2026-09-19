"""SQLAlchemy models owned by the activity-log domain."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from ..auth.models import Base


class ActivityLog(Base):
    """An immutable owner-scoped record of a domain activity."""

    __tablename__ = "activity_logs"
    __table_args__ = (
        Index(
            "ix_activity_logs_user_created",
            "user_id",
            "created_at",
            "id",
        ),
        Index(
            "ix_activity_logs_user_event_created",
            "user_id",
            "event_type",
            "created_at",
            "id",
        ),
        Index(
            "ix_activity_logs_user_entity_created",
            "user_id",
            "entity_type",
            "entity_id",
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
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
