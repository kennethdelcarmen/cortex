"""Add owner-scoped task positions for board ordering."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_task_positions"
down_revision: str | None = "0002_tasks_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
    )

    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            """
            SELECT id, user_id, status, due_at, created_at
            FROM tasks
            ORDER BY
                user_id,
                status,
                CASE WHEN due_at IS NULL THEN 1 ELSE 0 END,
                due_at,
                created_at DESC,
                id
            """
        )
    ).mappings()
    positions: dict[tuple[str, str], int] = {}
    for row in rows:
        key = (row["user_id"], row["status"])
        position = positions.get(key, 0)
        connection.execute(
            sa.text("UPDATE tasks SET position = :position WHERE id = :task_id"),
            {"position": position, "task_id": row["id"]},
        )
        positions[key] = position + 1

    op.create_index(
        "ix_tasks_owner_deleted_status_position",
        "tasks",
        ["user_id", "deleted_at", "status", "position"],
    )


def downgrade() -> None:
    op.drop_index("ix_tasks_owner_deleted_status_position", table_name="tasks")
    with op.batch_alter_table("tasks") as batch_op:
        batch_op.drop_column("position")
