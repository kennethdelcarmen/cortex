"""Allow owner-scoped money projections in the shared content index."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024_money_rag_sources"
down_revision: str | None = "0023_money_transaction_void_reasons"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MONEY_SOURCE_TYPES = (
    "'money_account', 'money_payee', 'money_category', 'money_budget', "
    "'money_transaction', 'money_recurring', 'money_installment'"
)


def upgrade() -> None:
    with op.batch_alter_table("content_chunks") as batch_op:
        batch_op.drop_constraint("ck_content_chunks_source_type", type_="check")
        batch_op.alter_column(
            "source_type",
            existing_type=sa.String(length=16),
            type_=sa.String(length=32),
            existing_nullable=False,
        )
        batch_op.create_check_constraint(
            "ck_content_chunks_source_type",
            f"source_type IN ('note', 'task', 'file', {MONEY_SOURCE_TYPES})",
        )


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "DELETE FROM content_chunk_embeddings WHERE chunk_id IN ("
            "SELECT id FROM content_chunks WHERE source_type IN ("
            f"{MONEY_SOURCE_TYPES}))"
        )
    )
    connection.execute(
        sa.text(
            "DELETE FROM content_chunks_fts WHERE chunk_id IN ("
            "SELECT id FROM content_chunks WHERE source_type IN ("
            f"{MONEY_SOURCE_TYPES}))"
        )
    )
    connection.execute(
        sa.text(f"DELETE FROM content_chunks WHERE source_type IN ({MONEY_SOURCE_TYPES})")
    )
    vector_table = connection.execute(
        sa.text(
            "SELECT 1 FROM sqlite_master "
            "WHERE type IN ('table', 'view') AND name = 'content_chunk_vectors'"
        )
    ).scalar()
    if vector_table:
        connection.execute(
            sa.text(
                "DELETE FROM content_chunk_vectors WHERE chunk_id NOT IN ("
                "SELECT id FROM content_chunks)"
            )
        )
    with op.batch_alter_table("content_chunks") as batch_op:
        batch_op.drop_constraint("ck_content_chunks_source_type", type_="check")
        batch_op.alter_column(
            "source_type",
            existing_type=sa.String(length=32),
            type_=sa.String(length=16),
            existing_nullable=False,
        )
        batch_op.create_check_constraint(
            "ck_content_chunks_source_type",
            "source_type IN ('note', 'task', 'file')",
        )
