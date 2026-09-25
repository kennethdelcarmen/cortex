"""Add file tags and the local file search index."""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0013_file_tags_search"
down_revision: str | None = "0012_normalize_file_context_timestamps"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "file_tags",
        sa.Column("file_id", sa.String(length=36), nullable=False),
        sa.Column("tag_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["file_id"], ["files.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("file_id", "tag_id"),
    )
    op.create_index("ix_file_tags_tag_id", "file_tags", ["tag_id"])
    op.execute(
        sa.text(
            "CREATE VIRTUAL TABLE files_fts USING fts5("
            "file_id UNINDEXED, name, content, tags, tokenize='unicode61'"
            ")"
        )
    )

    connection = op.get_bind()
    connection.execute(
        sa.text(
            "INSERT INTO files_fts (file_id, name, content, tags) "
            "SELECT files.id, files.original_name, '', "
            "COALESCE(group_concat(tags.name, ' '), '') "
            "FROM files "
            "LEFT JOIN file_tags ON file_tags.file_id = files.id "
            "LEFT JOIN tags ON tags.id = file_tags.tag_id "
            "GROUP BY files.id, files.original_name"
        )
    )

    now = datetime.now(UTC)
    connection.execute(
        sa.text(
            "UPDATE file_context_jobs "
            "SET status = 'pending', attempts = 0, available_at = :available_at, "
            "lease_expires_at = NULL, last_error = NULL, updated_at = :updated_at "
            "WHERE status = 'ready'"
        ),
        {"available_at": now, "updated_at": now},
    )


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE files_fts"))
    op.drop_index("ix_file_tags_tag_id", table_name="file_tags")
    op.drop_table("file_tags")
