"""Add durable content chunks and their local full-text index."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_content_chunking"
down_revision: str | None = "0014_record_file_attachments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "content_chunks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("source_type", sa.String(length=16), nullable=False),
        sa.Column("source_id", sa.String(length=64), nullable=False),
        sa.Column("source_version", sa.String(length=64), nullable=False),
        sa.Column("source_title", sa.String(length=200), nullable=True),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "source_type IN ('note', 'task', 'file')",
            name="ck_content_chunks_source_type",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "source_type",
            "source_id",
            "ordinal",
            name="uq_content_chunks_owner_source_ordinal",
        ),
    )
    op.create_index(
        "ix_content_chunks_owner_source",
        "content_chunks",
        ["user_id", "source_type", "source_id", "ordinal"],
    )
    op.create_index(
        "ix_content_chunks_owner_version",
        "content_chunks",
        ["user_id", "source_type", "source_version"],
    )
    op.execute(
        sa.text(
            "CREATE VIRTUAL TABLE content_chunks_fts USING fts5("
            "chunk_id UNINDEXED, content, tokenize='unicode61'"
            ")"
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE content_chunks_fts"))
    op.drop_index("ix_content_chunks_owner_version", table_name="content_chunks")
    op.drop_index("ix_content_chunks_owner_source", table_name="content_chunks")
    op.drop_table("content_chunks")
