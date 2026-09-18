"""SQLAlchemy models owned by the task domain."""

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


class Task(Base):
    """An owner-scoped piece of work."""

    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint(
            "status IN ('backlog', 'todo', 'in_progress', 'done', 'canceled')",
            name="ck_tasks_status",
        ),
        CheckConstraint(
            "priority IN ('none', 'low', 'medium', 'high')",
            name="ck_tasks_priority",
        ),
        Index("ix_tasks_owner_deleted_status", "user_id", "deleted_at", "status"),
        Index(
            "ix_tasks_owner_deleted_status_position",
            "user_id",
            "deleted_at",
            "status",
            "position",
        ),
        Index("ix_tasks_owner_deleted_priority", "user_id", "deleted_at", "priority"),
        Index(
            "ix_tasks_owner_deleted_due_created",
            "user_id",
            "deleted_at",
            "due_at",
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
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="backlog")
    priority: Mapped[str] = mapped_column(String(8), nullable=False, default="none")
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Tag(Base):
    """An owner-scoped normalized task tag."""

    __tablename__ = "tags"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_tags_user_name"),
        Index("ix_tags_user_id", "user_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TaskTag(Base):
    """Many-to-many membership between tasks and owner-scoped tags."""

    __tablename__ = "task_tags"
    __table_args__ = (Index("ix_task_tags_tag_id", "tag_id"),)

    task_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tag_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tags.id", ondelete="CASCADE"),
        primary_key=True,
    )
