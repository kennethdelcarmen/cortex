"""Create owner-scoped file metadata."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_files_foundation"
down_revision: str | None = "0009_fixed_tags"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "files",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("storage_key", sa.String(length=64), nullable=False),
        sa.Column("media_type", sa.String(length=127), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key", name="uq_files_storage_key"),
    )
    op.create_index(
        "ix_files_owner_deleted_created",
        "files",
        ["user_id", "deleted_at", "created_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_files_owner_deleted_created", table_name="files")
    op.drop_table("files")
