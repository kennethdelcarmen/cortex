"""Add durable file context processing and derived artifact manifests."""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision: str = "0011_file_context_pipeline"
down_revision: str | None = "0010_files_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("files") as batch_op:
        batch_op.drop_column("media_type")

    op.create_table(
        "file_context_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("source_sha256", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=255), nullable=True),
        sa.Column("extractor_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'ready', 'unsupported', 'failed')",
            name="ck_file_context_jobs_status",
        ),
        sa.UniqueConstraint(
            "user_id",
            "source_sha256",
            "extractor_version",
            name="uq_file_context_jobs_owner_hash_version",
        ),
    )
    op.create_index(
        "ix_file_context_jobs_claim",
        "file_context_jobs",
        ["status", "available_at", "lease_expires_at"],
    )

    op.create_table(
        "file_artifacts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("source_sha256", sa.String(length=64), nullable=False),
        sa.Column("artifact_kind", sa.String(length=32), nullable=False),
        sa.Column("storage_key", sa.String(length=255), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("extractor_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "source_sha256",
            "artifact_kind",
            "extractor_version",
            name="uq_file_artifacts_owner_hash_kind_version",
        ),
    )
    op.create_index(
        "ix_file_artifacts_owner_hash",
        "file_artifacts",
        ["user_id", "source_sha256"],
    )

    now = datetime.now(UTC)
    connection = op.get_bind()
    timestamp_type = sa.DateTime(timezone=True)
    existing_files = connection.execute(
        sa.text("SELECT user_id, sha256 FROM files GROUP BY user_id, sha256")
    ).fetchall()
    for user_id, source_sha256 in existing_files:
        connection.execute(
            sa.text(
                "INSERT INTO file_context_jobs "
                "(id, user_id, source_sha256, status, attempts, available_at, "
                "extractor_version, created_at, updated_at) "
                "VALUES (:id, :user_id, :source_sha256, 'pending', 0, :available_at, "
                "'v1', :created_at, :updated_at)"
            ).bindparams(
                sa.bindparam("available_at", type_=timestamp_type),
                sa.bindparam("created_at", type_=timestamp_type),
                sa.bindparam("updated_at", type_=timestamp_type),
            ),
            {
                "id": str(uuid4()),
                "user_id": user_id,
                "source_sha256": source_sha256,
                "available_at": now,
                "created_at": now,
                "updated_at": now,
            },
        )


def downgrade() -> None:
    op.drop_index("ix_file_artifacts_owner_hash", table_name="file_artifacts")
    op.drop_table("file_artifacts")
    op.drop_index("ix_file_context_jobs_claim", table_name="file_context_jobs")
    op.drop_table("file_context_jobs")
    with op.batch_alter_table("files") as batch_op:
        batch_op.add_column(
            sa.Column(
                "media_type",
                sa.String(length=127),
                nullable=False,
                server_default="application/octet-stream",
            )
        )
    with op.batch_alter_table("files") as batch_op:
        batch_op.alter_column("media_type", server_default=None)
