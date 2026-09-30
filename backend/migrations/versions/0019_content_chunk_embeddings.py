"""Add durable local embedding job state for content chunks."""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0019_content_chunk_embeddings"
down_revision: str | None = "0018_owner_display_name"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MODEL_NAME = "BAAI/bge-small-en-v1.5"
MODEL_VERSION = "v1"
DIMENSIONS = 384


def upgrade() -> None:
    op.create_table(
        "content_chunk_embeddings",
        sa.Column("chunk_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("source_version", sa.String(length=64), nullable=False),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column("model_version", sa.String(length=32), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'ready', 'failed')",
            name="ck_content_chunk_embeddings_status",
        ),
        sa.ForeignKeyConstraint(["chunk_id"], ["content_chunks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("chunk_id"),
    )
    op.create_index(
        "ix_content_chunk_embeddings_claim",
        "content_chunk_embeddings",
        ["status", "available_at", "lease_expires_at"],
    )
    op.create_index(
        "ix_content_chunk_embeddings_owner_status",
        "content_chunk_embeddings",
        ["user_id", "status", "updated_at"],
    )

    now = datetime.now(UTC)
    connection = op.get_bind()
    timestamp_type = sa.DateTime(timezone=True)
    connection.execute(
        sa.text(
            "INSERT INTO content_chunk_embeddings "
            "(chunk_id, user_id, source_version, model_name, model_version, dimensions, "
            "status, attempts, available_at, created_at, updated_at) "
            "SELECT id, user_id, source_version, :model_name, :model_version, :dimensions, "
            "'pending', 0, :available_at, :created_at, :updated_at "
            "FROM content_chunks"
        ).bindparams(
            sa.bindparam("available_at", type_=timestamp_type),
            sa.bindparam("created_at", type_=timestamp_type),
            sa.bindparam("updated_at", type_=timestamp_type),
        ),
        {
            "model_name": MODEL_NAME,
            "model_version": MODEL_VERSION,
            "dimensions": DIMENSIONS,
            "available_at": now,
            "created_at": now,
            "updated_at": now,
        },
    )


def downgrade() -> None:
    op.drop_index(
        "ix_content_chunk_embeddings_owner_status",
        table_name="content_chunk_embeddings",
    )
    op.drop_index("ix_content_chunk_embeddings_claim", table_name="content_chunk_embeddings")
    op.drop_table("content_chunk_embeddings")
