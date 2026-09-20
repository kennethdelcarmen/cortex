"""Add durable task recurrence series and occurrence metadata."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_task_recurrencies"
down_revision: str | None = "0004_activity_logs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "task_series",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="backlog"),
        sa.Column("priority", sa.String(length=8), nullable=False, server_default="none"),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("anchor_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("anchor_kind", sa.String(length=8), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("rule", sa.JSON(), nullable=False),
        sa.Column("until_date", sa.Date(), nullable=True),
        sa.Column("occurrence_count", sa.Integer(), nullable=True),
        sa.Column("state", sa.String(length=8), nullable=False, server_default="active"),
        sa.Column("materialized_through_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "state IN ('active', 'paused', 'ended')",
            name="ck_task_series_state",
        ),
        sa.CheckConstraint(
            "status IN ('backlog', 'todo', 'in_progress', 'done', 'canceled')",
            name="ck_task_series_status",
        ),
        sa.CheckConstraint(
            "priority IN ('none', 'low', 'medium', 'high')",
            name="ck_task_series_priority",
        ),
        sa.CheckConstraint(
            "anchor_kind IN ('start', 'due')",
            name="ck_task_series_anchor_kind",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_task_series_owner_state_updated",
        "task_series",
        ["user_id", "state", "updated_at"],
    )

    with op.batch_alter_table("tasks") as batch_op:
        batch_op.add_column(
            sa.Column("series_id", sa.String(length=36), nullable=True),
        )
        batch_op.add_column(
            sa.Column("occurrence_key", sa.String(length=64), nullable=True),
        )
        batch_op.add_column(
            sa.Column("series_exception", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
        batch_op.add_column(
            sa.Column("skipped_at", sa.DateTime(timezone=True), nullable=True),
        )
        batch_op.create_foreign_key(
            "fk_tasks_series_id_task_series",
            "task_series",
            ["series_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_unique_constraint(
            "uq_tasks_series_occurrence",
            ["series_id", "occurrence_key"],
        )

    op.create_index(
        "ix_tasks_owner_series_occurrence",
        "tasks",
        ["user_id", "series_id", "occurrence_key"],
    )

    op.create_table(
        "task_series_tags",
        sa.Column("series_id", sa.String(length=36), nullable=False),
        sa.Column("tag_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["series_id"], ["task_series.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("series_id", "tag_id"),
    )
    op.create_index("ix_task_series_tags_tag_id", "task_series_tags", ["tag_id"])


def downgrade() -> None:
    op.drop_index("ix_task_series_tags_tag_id", table_name="task_series_tags")
    op.drop_table("task_series_tags")
    op.drop_index("ix_tasks_owner_series_occurrence", table_name="tasks")
    with op.batch_alter_table("tasks") as batch_op:
        batch_op.drop_constraint("uq_tasks_series_occurrence", type_="unique")
        batch_op.drop_constraint("fk_tasks_series_id_task_series", type_="foreignkey")
        batch_op.drop_column("skipped_at")
        batch_op.drop_column("series_exception")
        batch_op.drop_column("occurrence_key")
        batch_op.drop_column("series_id")
    op.drop_index("ix_task_series_owner_state_updated", table_name="task_series")
    op.drop_table("task_series")
