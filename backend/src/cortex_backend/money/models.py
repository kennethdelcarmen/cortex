"""SQLAlchemy models owned by the money domain."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..auth.models import Base


class MoneyAccount(Base):
    """An owner-scoped financial account."""

    __tablename__ = "money_accounts"
    __table_args__ = (
        CheckConstraint(
            "account_type IN ('checking', 'savings', 'cash', 'credit_card', "
            "'loan', 'investment', 'other')",
            name="ck_money_accounts_type",
        ),
        CheckConstraint("length(currency_code) = 3", name="ck_money_accounts_currency"),
        CheckConstraint(
            "last_four IS NULL OR (length(last_four) = 4 AND last_four NOT GLOB '*[^0-9]*')",
            name="ck_money_accounts_last_four",
        ),
        Index("ix_money_accounts_owner_archived_name", "user_id", "archived_at", "name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    account_type: Mapped[str] = mapped_column(String(16), nullable=False)
    institution_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    last_four: Mapped[str | None] = mapped_column(String(4), nullable=True)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    opening_balance: Mapped[str] = mapped_column(String(64), nullable=False, default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MoneyPayee(Base):
    """A normalized owner-scoped payee."""

    __tablename__ = "money_payees"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_money_payees_owner_name"),
        Index("ix_money_payees_owner_archived_name", "user_id", "archived_at", "name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MoneyCategory(Base):
    """A flat income or expense category."""

    __tablename__ = "money_categories"
    __table_args__ = (
        CheckConstraint("kind IN ('income', 'expense')", name="ck_money_categories_kind"),
        UniqueConstraint("user_id", "name", name="uq_money_categories_owner_name"),
        Index("ix_money_categories_owner_archived_name", "user_id", "archived_at", "name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[str] = mapped_column(String(8), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MoneyBudget(Base):
    """A monthly allocation for one expense category and currency."""

    __tablename__ = "money_budgets"
    __table_args__ = (
        CheckConstraint("length(period) = 7", name="ck_money_budgets_period"),
        CheckConstraint("length(currency_code) = 3", name="ck_money_budgets_currency"),
        UniqueConstraint(
            "user_id",
            "category_id",
            "period",
            "currency_code",
            name="uq_money_budgets_owner_category_period_currency",
        ),
        Index("ix_money_budgets_owner_period_currency", "user_id", "period", "currency_code"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    category_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("money_categories.id", ondelete="RESTRICT"), nullable=False
    )
    period: Mapped[str] = mapped_column(String(7), nullable=False)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    amount: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MoneyTransaction(Base):
    """A balanced owner-scoped transaction header."""

    __tablename__ = "money_transactions"
    __table_args__ = (
        CheckConstraint("state IN ('posted', 'voided')", name="ck_money_transactions_state"),
        Index(
            "ix_money_transactions_owner_date_id",
            "user_id",
            "transaction_date",
            "id",
        ),
        Index(
            "ix_money_transactions_owner_payee_date",
            "user_id",
            "payee_id",
            "transaction_date",
        ),
        Index("ix_money_transactions_owner_state_date", "user_id", "state", "transaction_date"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    payee_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("money_payees.id", ondelete="RESTRICT"), nullable=True
    )
    memo: Mapped[str | None] = mapped_column(Text, nullable=True)
    state: Mapped[str] = mapped_column(String(8), nullable=False, default="posted")
    reversal_of_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("money_transactions.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MoneyPosting(Base):
    """One account or category side of a balanced transaction."""

    __tablename__ = "money_postings"
    __table_args__ = (
        CheckConstraint(
            "(account_id IS NOT NULL AND category_id IS NULL) OR "
            "(account_id IS NULL AND category_id IS NOT NULL)",
            name="ck_money_postings_target",
        ),
        CheckConstraint("amount <> '0'", name="ck_money_postings_nonzero"),
        CheckConstraint(
            "reconciliation_state IN ('uncleared', 'cleared', 'reconciled')",
            name="ck_money_postings_reconciliation",
        ),
        CheckConstraint("length(currency_code) = 3", name="ck_money_postings_currency"),
        Index(
            "ix_money_postings_owner_account_transaction",
            "user_id",
            "account_id",
            "transaction_id",
        ),
        Index(
            "ix_money_postings_owner_category_transaction",
            "user_id",
            "category_id",
            "transaction_id",
        ),
        Index(
            "ix_money_postings_owner_reconciliation",
            "user_id",
            "reconciliation_state",
            "transaction_id",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    transaction_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("money_transactions.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("money_accounts.id", ondelete="RESTRICT"), nullable=True
    )
    category_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("money_categories.id", ondelete="RESTRICT"), nullable=True
    )
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    amount: Mapped[str] = mapped_column(String(64), nullable=False)
    reconciliation_state: Mapped[str] = mapped_column(
        String(10), nullable=False, default="uncleared"
    )
    cleared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reconciled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
