"""Create the owner-scoped task and tag tables."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_tasks_foundation"
down_revision: str | None = "0001_auth_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tasks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="backlog"),
        sa.Column("priority", sa.String(length=8), nullable=False, server_default="none"),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('backlog', 'todo', 'in_progress', 'done', 'canceled')",
            name="ck_tasks_status",
        ),
        sa.CheckConstraint(
            "priority IN ('none', 'low', 'medium', 'high')",
            name="ck_tasks_priority",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_tasks_owner_deleted_status",
        "tasks",
        ["user_id", "deleted_at", "status"],
    )
    op.create_index(
        "ix_tasks_owner_deleted_priority",
        "tasks",
        ["user_id", "deleted_at", "priority"],
    )
    op.create_index(
        "ix_tasks_owner_deleted_due_created",
        "tasks",
        ["user_id", "deleted_at", "due_at", "created_at", "id"],
    )

    op.create_table(
        "tags",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "name", name="uq_tags_user_name"),
    )
    op.create_index("ix_tags_user_id", "tags", ["user_id"])

    op.create_table(
        "task_tags",
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("tag_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("task_id", "tag_id"),
    )
    op.create_index("ix_task_tags_tag_id", "task_tags", ["tag_id"])


def downgrade() -> None:
    op.drop_index("ix_task_tags_tag_id", table_name="task_tags")
    op.drop_table("task_tags")
    op.drop_index("ix_tags_user_id", table_name="tags")
    op.drop_table("tags")
    op.drop_index("ix_tasks_owner_deleted_due_created", table_name="tasks")
    op.drop_index("ix_tasks_owner_deleted_priority", table_name="tasks")
    op.drop_index("ix_tasks_owner_deleted_status", table_name="tasks")
    op.drop_table("tasks")
