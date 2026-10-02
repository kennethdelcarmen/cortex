"""Track whether a voided transaction was manual or reversal-created."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023_money_transaction_void_reasons"
down_revision: str | None = "0022_money_transaction_splits"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("money_transactions") as batch_op:
        batch_op.add_column(sa.Column("void_reason", sa.String(length=8), nullable=True))

    connection = op.get_bind()
    connection.execute(
        sa.text(
            "UPDATE money_transactions "
            "SET void_reason = 'reversal' "
            "WHERE state = 'voided'"
        )
    )

    with op.batch_alter_table("money_transactions") as batch_op:
        batch_op.create_check_constraint(
            "ck_money_transactions_void_reason",
            "(state = 'posted' AND void_reason IS NULL) OR "
            "(state = 'voided' AND void_reason IN ('manual', 'reversal'))",
        )


def downgrade() -> None:
    with op.batch_alter_table("money_transactions") as batch_op:
        batch_op.drop_constraint("ck_money_transactions_void_reason", type_="check")
        batch_op.drop_column("void_reason")
