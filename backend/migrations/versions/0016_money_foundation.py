"""Create the owner-scoped money foundation."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016_money_foundation"
down_revision: str | None = "0015_content_chunking"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "money_accounts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("account_type", sa.String(length=16), nullable=False),
        sa.Column("institution_name", sa.String(length=200), nullable=True),
        sa.Column("last_four", sa.String(length=4), nullable=True),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("opening_balance", sa.String(length=64), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "account_type IN ('checking', 'savings', 'cash', 'credit_card', 'loan', "
            "'investment', 'other')",
            name="ck_money_accounts_type",
        ),
        sa.CheckConstraint("length(currency_code) = 3", name="ck_money_accounts_currency"),
        sa.CheckConstraint(
            "last_four IS NULL OR (length(last_four) = 4 AND last_four NOT GLOB '*[^0-9]*')",
            name="ck_money_accounts_last_four",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_money_accounts_owner_archived_name",
        "money_accounts",
        ["user_id", "archived_at", "name"],
    )

    op.create_table(
        "money_payees",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "name", name="uq_money_payees_owner_name"),
    )
    op.create_index(
        "ix_money_payees_owner_archived_name",
        "money_payees",
        ["user_id", "archived_at", "name"],
    )

    op.create_table(
        "money_categories",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("kind IN ('income', 'expense')", name="ck_money_categories_kind"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "name", name="uq_money_categories_owner_name"),
    )
    op.create_index(
        "ix_money_categories_owner_archived_name",
        "money_categories",
        ["user_id", "archived_at", "name"],
    )

    op.create_table(
        "money_budgets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("category_id", sa.String(length=36), nullable=False),
        sa.Column("period", sa.String(length=7), nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("amount", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(period) = 7", name="ck_money_budgets_period"),
        sa.CheckConstraint("length(currency_code) = 3", name="ck_money_budgets_currency"),
        sa.ForeignKeyConstraint(["category_id"], ["money_categories.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "category_id",
            "period",
            "currency_code",
            name="uq_money_budgets_owner_category_period_currency",
        ),
    )
    op.create_index(
        "ix_money_budgets_owner_period_currency",
        "money_budgets",
        ["user_id", "period", "currency_code"],
    )

    op.create_table(
        "money_transactions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("transaction_date", sa.Date(), nullable=False),
        sa.Column("payee_id", sa.String(length=36), nullable=True),
        sa.Column("memo", sa.Text(), nullable=True),
        sa.Column("state", sa.String(length=8), nullable=False, server_default="posted"),
        sa.Column("reversal_of_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "state IN ('posted', 'voided')",
            name="ck_money_transactions_state",
        ),
        sa.ForeignKeyConstraint(["payee_id"], ["money_payees.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reversal_of_id"], ["money_transactions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_money_transactions_owner_date_id",
        "money_transactions",
        ["user_id", "transaction_date", "id"],
    )
    op.create_index(
        "ix_money_transactions_owner_payee_date",
        "money_transactions",
        ["user_id", "payee_id", "transaction_date"],
    )
    op.create_index(
        "ix_money_transactions_owner_state_date",
        "money_transactions",
        ["user_id", "state", "transaction_date"],
    )

    op.create_table(
        "money_postings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("transaction_id", sa.String(length=36), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=True),
        sa.Column("category_id", sa.String(length=36), nullable=True),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("amount", sa.String(length=64), nullable=False),
        sa.Column(
            "reconciliation_state",
            sa.String(length=10),
            nullable=False,
            server_default="uncleared",
        ),
        sa.Column("cleared_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reconciled_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(account_id IS NOT NULL AND category_id IS NULL) OR "
            "(account_id IS NULL AND category_id IS NOT NULL)",
            name="ck_money_postings_target",
        ),
        sa.CheckConstraint("amount <> '0'", name="ck_money_postings_nonzero"),
        sa.CheckConstraint(
            "reconciliation_state IN ('uncleared', 'cleared', 'reconciled')",
            name="ck_money_postings_reconciliation",
        ),
        sa.CheckConstraint("length(currency_code) = 3", name="ck_money_postings_currency"),
        sa.ForeignKeyConstraint(["account_id"], ["money_accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["category_id"], ["money_categories.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["transaction_id"], ["money_transactions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_money_postings_owner_account_transaction",
        "money_postings",
        ["user_id", "account_id", "transaction_id"],
    )
    op.create_index(
        "ix_money_postings_owner_category_transaction",
        "money_postings",
        ["user_id", "category_id", "transaction_id"],
    )
    op.create_index(
        "ix_money_postings_owner_reconciliation",
        "money_postings",
        ["user_id", "reconciliation_state", "transaction_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_money_postings_owner_reconciliation", table_name="money_postings")
    op.drop_index("ix_money_postings_owner_category_transaction", table_name="money_postings")
    op.drop_index("ix_money_postings_owner_account_transaction", table_name="money_postings")
    op.drop_table("money_postings")
    op.drop_index("ix_money_transactions_owner_state_date", table_name="money_transactions")
    op.drop_index("ix_money_transactions_owner_payee_date", table_name="money_transactions")
    op.drop_index("ix_money_transactions_owner_date_id", table_name="money_transactions")
    op.drop_table("money_transactions")
    op.drop_index("ix_money_budgets_owner_period_currency", table_name="money_budgets")
    op.drop_table("money_budgets")
    op.drop_index("ix_money_categories_owner_archived_name", table_name="money_categories")
    op.drop_table("money_categories")
    op.drop_index("ix_money_payees_owner_archived_name", table_name="money_payees")
    op.drop_table("money_payees")
    op.drop_index("ix_money_accounts_owner_archived_name", table_name="money_accounts")
    op.drop_table("money_accounts")
