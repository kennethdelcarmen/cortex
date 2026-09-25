"""Add reusable file attachments for notes, tasks, and task series."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_record_file_attachments"
down_revision: str | None = "0013_file_tags_search"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _create_link_table(
    table_name: str,
    owner_column: str,
    owner_table: str,
    position_constraint: str,
    file_index: str,
    owner_index: str,
) -> None:
    op.create_table(
        table_name,
        sa.Column(owner_column, sa.String(length=36), nullable=False),
        sa.Column("file_id", sa.String(length=36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint([owner_column], [f"{owner_table}.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["file_id"], ["files.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint(owner_column, "file_id"),
    )
    op.create_index(position_constraint, table_name, [owner_column, "position"], unique=True)
    op.create_index(file_index, table_name, ["file_id"])
    op.create_index(owner_index, table_name, [owner_column, "position"])


def upgrade() -> None:
    _create_link_table(
        "note_files",
        "note_id",
        "notes",
        "uq_note_files_position",
        "ix_note_files_file_id",
        "ix_note_files_note_position",
    )
    _create_link_table(
        "task_files",
        "task_id",
        "tasks",
        "uq_task_files_position",
        "ix_task_files_file_id",
        "ix_task_files_task_position",
    )
    _create_link_table(
        "task_series_files",
        "series_id",
        "task_series",
        "uq_task_series_files_position",
        "ix_task_series_files_file_id",
        "ix_task_series_files_series_position",
    )


def downgrade() -> None:
    op.drop_index("ix_task_series_files_series_position", table_name="task_series_files")
    op.drop_index("ix_task_series_files_file_id", table_name="task_series_files")
    op.drop_index("uq_task_series_files_position", table_name="task_series_files")
    op.drop_table("task_series_files")
    op.drop_index("ix_task_files_task_position", table_name="task_files")
    op.drop_index("ix_task_files_file_id", table_name="task_files")
    op.drop_index("uq_task_files_position", table_name="task_files")
    op.drop_table("task_files")
    op.drop_index("ix_note_files_note_position", table_name="note_files")
    op.drop_index("ix_note_files_file_id", table_name="note_files")
    op.drop_index("uq_note_files_position", table_name="note_files")
    op.drop_table("note_files")
