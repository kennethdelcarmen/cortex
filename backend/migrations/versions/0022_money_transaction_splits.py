"""Add ordered, labelled transaction postings for split transactions."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022_money_transaction_splits"
down_revision: str | None = "0021_money_recurring_transactions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("money_postings") as batch_op:
        batch_op.add_column(sa.Column("position", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("label", sa.String(length=200), nullable=True))

    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            """
            SELECT id, transaction_id
            FROM money_postings
            ORDER BY transaction_id, id
            """
        )
    ).mappings()
    positions: dict[str, int] = {}
    for row in rows:
        transaction_id = str(row["transaction_id"])
        position = positions.get(transaction_id, 0)
        connection.execute(
            sa.text("UPDATE money_postings SET position = :position WHERE id = :posting_id"),
            {"position": position, "posting_id": row["id"]},
        )
        positions[transaction_id] = position + 1

    with op.batch_alter_table("money_postings") as batch_op:
        batch_op.alter_column(
            "position",
            existing_type=sa.Integer(),
            nullable=False,
        )
        batch_op.create_check_constraint(
            "ck_money_postings_position_nonnegative",
            "position >= 0",
        )
        batch_op.create_unique_constraint(
            "uq_money_postings_transaction_position",
            ["transaction_id", "position"],
        )


def downgrade() -> None:
    # Downgrading intentionally discards labels and server-assigned posting order.
    with op.batch_alter_table("money_postings") as batch_op:
        batch_op.drop_constraint("uq_money_postings_transaction_position", type_="unique")
        batch_op.drop_constraint("ck_money_postings_position_nonnegative", type_="check")
        batch_op.drop_column("label")
        batch_op.drop_column("position")
