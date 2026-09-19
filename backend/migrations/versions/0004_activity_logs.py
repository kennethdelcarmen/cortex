"""Create the owner-scoped append-only activity log table."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_activity_logs"
down_revision: str | None = "0003_task_positions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "activity_logs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=True),
        sa.Column("entity_id", sa.String(length=128), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_activity_logs_user_created",
        "activity_logs",
        ["user_id", "created_at", "id"],
    )
    op.create_index(
        "ix_activity_logs_user_event_created",
        "activity_logs",
        ["user_id", "event_type", "created_at", "id"],
    )
    op.create_index(
        "ix_activity_logs_user_entity_created",
        "activity_logs",
        ["user_id", "entity_type", "entity_id", "created_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_activity_logs_user_entity_created", table_name="activity_logs")
    op.drop_index("ix_activity_logs_user_event_created", table_name="activity_logs")
    op.drop_index("ix_activity_logs_user_created", table_name="activity_logs")
    op.drop_table("activity_logs")
