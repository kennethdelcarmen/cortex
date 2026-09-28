"""Add first-class names to money transactions."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017_money_transaction_names"
down_revision: str | None = "0016_money_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "money_transactions",
        sa.Column("name", sa.String(length=200), nullable=True),
    )
    op.execute(
        sa.text(
            """
            UPDATE money_transactions
            SET name = COALESCE(
                (SELECT name FROM money_payees WHERE money_payees.id = money_transactions.payee_id),
                NULLIF(TRIM(memo), ''),
                'Untitled transaction'
            )
            WHERE name IS NULL
            """
        )
    )
    with op.batch_alter_table("money_transactions") as batch_op:
        batch_op.alter_column(
            "name",
            existing_type=sa.String(length=200),
            nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("money_transactions") as batch_op:
        batch_op.drop_column("name")
