"""Add recurring money transaction schedules and occurrences."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021_money_recurring_transactions"
down_revision: str | None = "0020_credit_card_installments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "money_recurring_transactions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("payee_id", sa.String(length=36), nullable=True),
        sa.Column("memo", sa.Text(), nullable=True),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("rule", sa.JSON(), nullable=False),
        sa.Column("until_date", sa.Date(), nullable=True),
        sa.Column("occurrence_count", sa.Integer(), nullable=True),
        sa.Column("state", sa.String(length=8), nullable=False, server_default="active"),
        sa.Column("next_occurrence_date", sa.Date(), nullable=True),
        sa.Column("next_occurrence_number", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "state IN ('active', 'paused', 'ended')",
            name="ck_money_recurring_transactions_state",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["payee_id"], ["money_payees.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_money_recurring_transactions_owner_state_updated",
        "money_recurring_transactions",
        ["user_id", "state", "updated_at"],
    )
    op.create_index(
        "ix_money_recurring_transactions_owner_next_state",
        "money_recurring_transactions",
        ["user_id", "state", "next_occurrence_date"],
    )

    op.create_table(
        "money_recurring_postings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("recurring_transaction_id", sa.String(length=36), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=True),
        sa.Column("category_id", sa.String(length=36), nullable=True),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("amount", sa.String(length=64), nullable=False),
        sa.CheckConstraint(
            "(account_id IS NOT NULL AND category_id IS NULL) OR "
            "(account_id IS NULL AND category_id IS NOT NULL)",
            name="ck_money_recurring_postings_target",
        ),
        sa.CheckConstraint("amount <> '0'", name="ck_money_recurring_postings_nonzero"),
        sa.CheckConstraint(
            "length(currency_code) = 3", name="ck_money_recurring_postings_currency"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["recurring_transaction_id"],
            ["money_recurring_transactions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["account_id"], ["money_accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["category_id"], ["money_categories.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_money_recurring_postings_owner_schedule",
        "money_recurring_postings",
        ["user_id", "recurring_transaction_id"],
    )

    op.create_table(
        "money_recurring_occurrences",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("recurring_transaction_id", sa.String(length=36), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=9), nullable=False, server_default="scheduled"),
        sa.Column("transaction_id", sa.String(length=36), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('scheduled', 'posted', 'skipped')",
            name="ck_money_recurring_occurrences_status",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["recurring_transaction_id"],
            ["money_recurring_transactions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["transaction_id"], ["money_transactions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "recurring_transaction_id",
            "due_date",
            name="uq_money_recurring_occurrences_schedule_date",
        ),
    )
    op.create_index(
        "ix_money_recurring_occurrences_owner_due_status",
        "money_recurring_occurrences",
        ["user_id", "due_date", "status"],
    )
    op.create_index(
        "ix_money_recurring_occurrences_schedule_status",
        "money_recurring_occurrences",
        ["recurring_transaction_id", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_money_recurring_occurrences_schedule_status",
        table_name="money_recurring_occurrences",
    )
    op.drop_index(
        "ix_money_recurring_occurrences_owner_due_status",
        table_name="money_recurring_occurrences",
    )
    op.drop_table("money_recurring_occurrences")
    op.drop_index(
        "ix_money_recurring_postings_owner_schedule",
        table_name="money_recurring_postings",
    )
    op.drop_table("money_recurring_postings")
    op.drop_index(
        "ix_money_recurring_transactions_owner_next_state",
        table_name="money_recurring_transactions",
    )
    op.drop_index(
        "ix_money_recurring_transactions_owner_state_updated",
        table_name="money_recurring_transactions",
    )
    op.drop_table("money_recurring_transactions")
