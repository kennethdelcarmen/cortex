"""Add credit-card configuration and statement-charge installment plans."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020_credit_card_installments"
down_revision: str | None = "0019_content_chunk_embeddings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("money_accounts", sa.Column("credit_limit", sa.String(length=64), nullable=True))
    op.add_column("money_accounts", sa.Column("statement_close_day", sa.Integer(), nullable=True))
    op.add_column("money_accounts", sa.Column("payment_due_day", sa.Integer(), nullable=True))

    op.create_table(
        "money_installment_plans",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=False),
        sa.Column("payee_id", sa.String(length=36), nullable=True),
        sa.Column("category_id", sa.String(length=36), nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("purchase_date", sa.Date(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("memo", sa.Text(), nullable=True),
        sa.Column("total_amount", sa.String(length=64), nullable=False),
        sa.Column("fee_amount", sa.String(length=64), nullable=False, server_default="0"),
        sa.Column("term_months", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('active', 'completed', 'cancelled')",
            name="ck_money_installment_plans_status",
        ),
        sa.CheckConstraint("term_months BETWEEN 1 AND 120", name="ck_money_installment_plans_term"),
        sa.CheckConstraint("length(currency_code) = 3", name="ck_money_installment_plans_currency"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["account_id"], ["money_accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["payee_id"], ["money_payees.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["category_id"], ["money_categories.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_money_installment_plans_owner_account_status",
        "money_installment_plans",
        ["user_id", "account_id", "status"],
    )
    op.create_index(
        "ix_money_installment_plans_owner_purchase_date",
        "money_installment_plans",
        ["user_id", "purchase_date", "id"],
    )

    op.create_table(
        "money_installment_occurrences",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("plan_id", sa.String(length=36), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("charge_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=9), nullable=False, server_default="scheduled"),
        sa.Column("transaction_id", sa.String(length=36), nullable=True),
        sa.Column("charged_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('scheduled', 'charged', 'cancelled')",
            name="ck_money_installment_occurrences_status",
        ),
        sa.CheckConstraint("amount <> '0'", name="ck_money_installment_occurrences_amount"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["plan_id"], ["money_installment_plans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["transaction_id"], ["money_transactions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "plan_id", "sequence_number", name="uq_money_installment_occurrences_plan_sequence"
        ),
    )
    op.create_index(
        "ix_money_installment_occurrences_owner_due_status",
        "money_installment_occurrences",
        ["user_id", "charge_date", "status"],
    )
    op.create_index(
        "ix_money_installment_occurrences_plan_status",
        "money_installment_occurrences",
        ["plan_id", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_money_installment_occurrences_plan_status",
        table_name="money_installment_occurrences",
    )
    op.drop_index(
        "ix_money_installment_occurrences_owner_due_status",
        table_name="money_installment_occurrences",
    )
    op.drop_table("money_installment_occurrences")
    op.drop_index(
        "ix_money_installment_plans_owner_purchase_date",
        table_name="money_installment_plans",
    )
    op.drop_index(
        "ix_money_installment_plans_owner_account_status",
        table_name="money_installment_plans",
    )
    op.drop_table("money_installment_plans")
    op.drop_column("money_accounts", "payment_due_day")
    op.drop_column("money_accounts", "statement_close_day")
    op.drop_column("money_accounts", "credit_limit")
