"""Owner-scoped text projections for money records in the shared RAG index."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..chunking.service import (
    ChunkSource,
    delete_source_chunks,
    replace_source_chunks,
    source_version,
)
from .models import (
    MoneyAccount,
    MoneyBudget,
    MoneyCategory,
    MoneyInstallmentOccurrence,
    MoneyInstallmentPlan,
    MoneyPayee,
    MoneyPosting,
    MoneyRecurringOccurrence,
    MoneyRecurringPosting,
    MoneyRecurringTransaction,
    MoneyTransaction,
)
from .schemas import SUPPORTED_CURRENCY_EXPONENTS

MoneyRagSourceType = Literal[
    "money_account",
    "money_payee",
    "money_category",
    "money_budget",
    "money_transaction",
    "money_recurring",
    "money_installment",
]

MONEY_RAG_SOURCE_TYPES: tuple[MoneyRagSourceType, ...] = (
    "money_account",
    "money_payee",
    "money_category",
    "money_budget",
    "money_transaction",
    "money_recurring",
    "money_installment",
)
RAG_VERSION_SALT = "money-rag-v1"


def _decimal(value: str) -> Decimal:
    return Decimal(value)


def _amount(value: Decimal | str, currency_code: str) -> str:
    exponent = SUPPORTED_CURRENCY_EXPONENTS.get(currency_code, 2)
    quantum = Decimal(1).scaleb(-exponent)
    return format(Decimal(value).quantize(quantum), "f")


def _date(value: date | None) -> str:
    return value.isoformat() if value is not None else "none"


def _status(value: str, archived_at: object | None = None) -> str:
    if archived_at is not None:
        return f"{value}, archived"
    return value


def _source(
    *,
    user_id: str,
    source_type: MoneyRagSourceType,
    source_id: str,
    title: str,
    lines: Iterable[str],
) -> ChunkSource:
    return ChunkSource(
        user_id=user_id,
        source_type=source_type,
        source_id=source_id,
        title=title,
        text="\n".join((title, *lines)),
        version_salt=RAG_VERSION_SALT,
    )


async def _account_balance(db: AsyncSession, account: MoneyAccount) -> Decimal:
    amounts = await db.scalars(
        select(MoneyPosting.amount)
        .join(MoneyTransaction, MoneyTransaction.id == MoneyPosting.transaction_id)
        .where(
            MoneyPosting.account_id == account.id,
            MoneyPosting.user_id == account.user_id,
            MoneyTransaction.state == "posted",
            MoneyTransaction.reversal_of_id.is_(None),
        )
    )
    return _decimal(account.opening_balance) + sum(
        (_decimal(value) for value in amounts.all()), Decimal(0)
    )


async def _account_source(db: AsyncSession, user_id: str, source_id: str) -> ChunkSource | None:
    account = await db.scalar(
        select(MoneyAccount).where(
            MoneyAccount.id == source_id,
            MoneyAccount.user_id == user_id,
        )
    )
    if account is None:
        return None
    balance = await _account_balance(db, account)
    lines = [
        f"Account type: {account.account_type}.",
        f"Institution: {account.institution_name or 'not specified'}.",
        f"Currency: {account.currency_code}.",
        f"Opening balance: {_amount(account.opening_balance, account.currency_code)}.",
        f"Current balance: {_amount(balance, account.currency_code)}.",
        f"Status: {_status('active', account.archived_at)}.",
    ]
    if account.credit_limit is not None:
        lines.extend(
            (
                f"Credit limit: {_amount(account.credit_limit, account.currency_code)}.",
                f"Amount owed: {_amount(max(-balance, Decimal(0)), account.currency_code)}.",
                "Available credit: "
                f"{_amount(_decimal(account.credit_limit) + balance, account.currency_code)}.",
                f"Statement close day: {account.statement_close_day or 'not specified'}.",
                f"Payment due day: {account.payment_due_day or 'not specified'}.",
            )
        )
    return _source(
        user_id=user_id,
        source_type="money_account",
        source_id=account.id,
        title=f"Money account: {account.name}",
        lines=lines,
    )


async def _payee_source(db: AsyncSession, user_id: str, source_id: str) -> ChunkSource | None:
    payee = await db.scalar(
        select(MoneyPayee).where(MoneyPayee.id == source_id, MoneyPayee.user_id == user_id)
    )
    if payee is None:
        return None
    return _source(
        user_id=user_id,
        source_type="money_payee",
        source_id=payee.id,
        title=f"Money payee: {payee.name}",
        lines=[f"Status: {_status('active', payee.archived_at)}."],
    )


async def _category_source(db: AsyncSession, user_id: str, source_id: str) -> ChunkSource | None:
    category = await db.scalar(
        select(MoneyCategory).where(
            MoneyCategory.id == source_id,
            MoneyCategory.user_id == user_id,
        )
    )
    if category is None:
        return None
    return _source(
        user_id=user_id,
        source_type="money_category",
        source_id=category.id,
        title=f"Money category: {category.name}",
        lines=[
            f"Kind: {category.kind}.",
            f"Status: {_status('active', category.archived_at)}.",
        ],
    )


async def _budget_spent(db: AsyncSession, budget: MoneyBudget) -> Decimal:
    year, month = (int(part) for part in budget.period.split("-"))
    start = date(year, month, 1)
    end = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
    amounts = await db.scalars(
        select(MoneyPosting.amount)
        .join(MoneyTransaction, MoneyTransaction.id == MoneyPosting.transaction_id)
        .where(
            MoneyPosting.user_id == budget.user_id,
            MoneyPosting.category_id == budget.category_id,
            MoneyPosting.currency_code == budget.currency_code,
            MoneyTransaction.transaction_date >= start,
            MoneyTransaction.transaction_date < end,
            MoneyTransaction.state == "posted",
            MoneyTransaction.reversal_of_id.is_(None),
        )
    )
    return sum((_decimal(value) for value in amounts.all()), Decimal(0))


async def _budget_source(db: AsyncSession, user_id: str, source_id: str) -> ChunkSource | None:
    budget = await db.scalar(
        select(MoneyBudget).where(
            MoneyBudget.id == source_id,
            MoneyBudget.user_id == user_id,
        )
    )
    if budget is None:
        return None
    category = await db.scalar(select(MoneyCategory).where(MoneyCategory.id == budget.category_id))
    category_name = category.name if category is not None else "Unknown category"
    spent = await _budget_spent(db, budget)
    amount = _decimal(budget.amount)
    return _source(
        user_id=user_id,
        source_type="money_budget",
        source_id=budget.id,
        title=f"Money budget: {category_name} · {budget.period}",
        lines=[
            f"Category: {category_name}.",
            f"Period: {budget.period}.",
            f"Currency: {budget.currency_code}.",
            f"Planned amount: {_amount(amount, budget.currency_code)}.",
            f"Spent amount: {_amount(spent, budget.currency_code)}.",
            f"Remaining amount: {_amount(amount - spent, budget.currency_code)}.",
        ],
    )


async def _named_targets(
    db: AsyncSession,
    user_id: str,
    postings: Sequence[MoneyPosting],
) -> tuple[dict[str, MoneyAccount], dict[str, MoneyCategory]]:
    account_ids = {posting.account_id for posting in postings if posting.account_id is not None}
    category_ids = {posting.category_id for posting in postings if posting.category_id is not None}
    accounts = (
        {
            account.id: account
            for account in (
                await db.scalars(
                    select(MoneyAccount).where(
                        MoneyAccount.user_id == user_id,
                        MoneyAccount.id.in_(account_ids),
                    )
                )
            ).all()
        }
        if account_ids
        else {}
    )
    categories = (
        {
            category.id: category
            for category in (
                await db.scalars(
                    select(MoneyCategory).where(
                        MoneyCategory.user_id == user_id,
                        MoneyCategory.id.in_(category_ids),
                    )
                )
            ).all()
        }
        if category_ids
        else {}
    )
    return accounts, categories


def _posting_line(
    posting: MoneyPosting,
    accounts: dict[str, MoneyAccount],
    categories: dict[str, MoneyCategory],
) -> str:
    target = "account"
    account = accounts.get(posting.account_id) if posting.account_id is not None else None
    target_name = account.name if account is not None else None
    if target_name is None:
        target = "category"
        category = categories.get(posting.category_id) if posting.category_id is not None else None
        target_name = category.name if category is not None else "Unknown category"
    label = f", label {posting.label!r}" if posting.label else ""
    return (
        f"Posting {posting.position + 1}: {target} {target_name}, "
        f"amount {posting.amount} {posting.currency_code}, "
        f"reconciliation {posting.reconciliation_state}{label}."
    )


async def _transaction_source(db: AsyncSession, user_id: str, source_id: str) -> ChunkSource | None:
    transaction = await db.scalar(
        select(MoneyTransaction).where(
            MoneyTransaction.id == source_id,
            MoneyTransaction.user_id == user_id,
        )
    )
    if transaction is None:
        return None
    postings = list(
        (
            await db.scalars(
                select(MoneyPosting)
                .where(MoneyPosting.transaction_id == transaction.id)
                .order_by(MoneyPosting.position.asc())
            )
        ).all()
    )
    accounts, categories = await _named_targets(db, user_id, postings)
    payee = (
        await db.scalar(select(MoneyPayee).where(MoneyPayee.id == transaction.payee_id))
        if transaction.payee_id
        else None
    )
    lines = [
        f"Date: {_date(transaction.transaction_date)}.",
        f"Payee: {payee.name if payee is not None else 'not specified'}.",
        f"State: {transaction.state}.",
        f"Void reason: {transaction.void_reason or 'none'}.",
        f"Memo: {transaction.memo or 'none'}.",
    ]
    if transaction.reversal_of_id is not None:
        lines.append("This transaction reverses an earlier transaction.")
    lines.extend(_posting_line(posting, accounts, categories) for posting in postings)
    return _source(
        user_id=user_id,
        source_type="money_transaction",
        source_id=transaction.id,
        title=f"Money transaction: {transaction.name}",
        lines=lines,
    )


async def _recurring_source(db: AsyncSession, user_id: str, source_id: str) -> ChunkSource | None:
    schedule = await db.scalar(
        select(MoneyRecurringTransaction).where(
            MoneyRecurringTransaction.id == source_id,
            MoneyRecurringTransaction.user_id == user_id,
        )
    )
    if schedule is None:
        return None
    postings = list(
        (
            await db.scalars(
                select(MoneyRecurringPosting)
                .where(MoneyRecurringPosting.recurring_transaction_id == schedule.id)
                .order_by(MoneyRecurringPosting.id.asc())
            )
        ).all()
    )
    occurrences = list(
        (
            await db.scalars(
                select(MoneyRecurringOccurrence)
                .where(MoneyRecurringOccurrence.recurring_transaction_id == schedule.id)
                .order_by(MoneyRecurringOccurrence.due_date.asc())
            )
        ).all()
    )
    account_ids = {posting.account_id for posting in postings if posting.account_id is not None}
    category_ids = {posting.category_id for posting in postings if posting.category_id is not None}
    accounts = (
        {
            account.id: account
            for account in (
                await db.scalars(
                    select(MoneyAccount).where(
                        MoneyAccount.user_id == user_id,
                        MoneyAccount.id.in_(account_ids),
                    )
                )
            ).all()
        }
        if account_ids
        else {}
    )
    categories = (
        {
            category.id: category
            for category in (
                await db.scalars(
                    select(MoneyCategory).where(
                        MoneyCategory.user_id == user_id,
                        MoneyCategory.id.in_(category_ids),
                    )
                )
            ).all()
        }
        if category_ids
        else {}
    )
    payee = (
        await db.scalar(select(MoneyPayee).where(MoneyPayee.id == schedule.payee_id))
        if schedule.payee_id
        else None
    )
    rule = schedule.rule
    lines = [
        f"Start date: {_date(schedule.start_date)}.",
        f"Payee: {payee.name if payee is not None else 'not specified'}.",
        f"Memo: {schedule.memo or 'none'}.",
        f"Timezone: {schedule.timezone}.",
        f"Frequency: {rule.get('frequency', 'not specified')}.",
        f"Interval: {rule.get('interval', 1)}.",
        f"State: {schedule.state}.",
        f"Next occurrence: {_date(schedule.next_occurrence_date)}.",
        f"Next occurrence number: {schedule.next_occurrence_number or 'none'}.",
        f"Until date: {_date(schedule.until_date)}.",
        f"Occurrence count limit: {schedule.occurrence_count or 'none'}.",
    ]
    for posting in postings:
        account = accounts.get(posting.account_id) if posting.account_id is not None else None
        category = categories.get(posting.category_id) if posting.category_id is not None else None
        target = (
            account.name
            if account is not None
            else category.name
            if category is not None
            else "Unknown target"
        )
        lines.append(
            f"Template posting: {target}, amount {posting.amount} {posting.currency_code}."
        )
    lines.append(f"Occurrences recorded: {len(occurrences)}.")
    for occurrence in occurrences:
        lines.append(
            f"Occurrence {occurrence.sequence_number}: due {_date(occurrence.due_date)}, "
            f"status {occurrence.status}, "
            f"transaction {'recorded' if occurrence.transaction_id else 'not recorded'}."
        )
    return _source(
        user_id=user_id,
        source_type="money_recurring",
        source_id=schedule.id,
        title=f"Recurring money transaction: {schedule.name}",
        lines=lines,
    )


async def _installment_source(db: AsyncSession, user_id: str, source_id: str) -> ChunkSource | None:
    plan = await db.scalar(
        select(MoneyInstallmentPlan).where(
            MoneyInstallmentPlan.id == source_id,
            MoneyInstallmentPlan.user_id == user_id,
        )
    )
    if plan is None:
        return None
    occurrences = list(
        (
            await db.scalars(
                select(MoneyInstallmentOccurrence)
                .where(MoneyInstallmentOccurrence.plan_id == plan.id)
                .order_by(MoneyInstallmentOccurrence.sequence_number.asc())
            )
        ).all()
    )
    account = await db.scalar(select(MoneyAccount).where(MoneyAccount.id == plan.account_id))
    category = await db.scalar(select(MoneyCategory).where(MoneyCategory.id == plan.category_id))
    payee = (
        await db.scalar(select(MoneyPayee).where(MoneyPayee.id == plan.payee_id))
        if plan.payee_id
        else None
    )
    lines = [
        f"Purchase date: {_date(plan.purchase_date)}.",
        f"Account: {account.name if account is not None else 'unknown account'}.",
        f"Category: {category.name if category is not None else 'unknown category'}.",
        f"Payee: {payee.name if payee is not None else 'not specified'}.",
        f"Currency: {plan.currency_code}.",
        f"Memo: {plan.memo or 'none'}.",
        f"Total amount: {plan.total_amount}.",
        f"Fee amount: {plan.fee_amount}.",
        f"Term months: {plan.term_months}.",
        f"Status: {plan.status}.",
        f"Occurrences recorded: {len(occurrences)}.",
    ]
    for occurrence in occurrences:
        lines.append(
            f"Occurrence {occurrence.sequence_number}: charge {_date(occurrence.charge_date)}, "
            f"amount {occurrence.amount} {plan.currency_code}, status {occurrence.status}, "
            f"transaction {'recorded' if occurrence.transaction_id else 'not recorded'}."
        )
    return _source(
        user_id=user_id,
        source_type="money_installment",
        source_id=plan.id,
        title=f"Installment money plan: {plan.name}",
        lines=lines,
    )


async def _source_for_type(
    db: AsyncSession,
    user_id: str,
    source_type: MoneyRagSourceType,
    source_id: str,
) -> ChunkSource | None:
    if source_type == "money_account":
        return await _account_source(db, user_id, source_id)
    if source_type == "money_payee":
        return await _payee_source(db, user_id, source_id)
    if source_type == "money_category":
        return await _category_source(db, user_id, source_id)
    if source_type == "money_budget":
        return await _budget_source(db, user_id, source_id)
    if source_type == "money_transaction":
        return await _transaction_source(db, user_id, source_id)
    if source_type == "money_recurring":
        return await _recurring_source(db, user_id, source_id)
    return await _installment_source(db, user_id, source_id)


async def refresh_money_source(
    db: AsyncSession,
    user_id: str,
    source_type: MoneyRagSourceType,
    source_id: str,
    *,
    now: datetime | None = None,
    skip_if_current: bool = False,
) -> None:
    source = await _source_for_type(db, user_id, source_type, source_id)
    if source is None:
        await delete_source_chunks(db, source_type, source_id, user_id=user_id)
        return
    if skip_if_current:
        version = source_version(source)
        current = await db.scalar(
            text(
                "SELECT 1 FROM content_chunks "
                "WHERE user_id = :user_id AND source_type = :source_type "
                "AND source_id = :source_id AND source_version = :source_version "
                "LIMIT 1"
            ),
            {
                "user_id": user_id,
                "source_type": source_type,
                "source_id": source_id,
                "source_version": version,
            },
        )
        if current:
            return
    await replace_source_chunks(db, source, now=now)


async def budget_ids_for_transactions(
    db: AsyncSession,
    user_id: str,
    transaction_ids: Sequence[str],
) -> set[str]:
    """Return budgets affected by the current postings of transactions."""

    if not transaction_ids:
        return set()
    transactions = {
        transaction.id: transaction
        for transaction in (
            await db.scalars(
                select(MoneyTransaction).where(
                    MoneyTransaction.user_id == user_id,
                    MoneyTransaction.id.in_(transaction_ids),
                )
            )
        ).all()
    }
    postings = list(
        (
            await db.scalars(
                select(MoneyPosting).where(
                    MoneyPosting.user_id == user_id,
                    MoneyPosting.transaction_id.in_(transactions),
                    MoneyPosting.category_id.is_not(None),
                )
            )
        ).all()
    )
    keys = {
        (
            posting.category_id,
            transactions[posting.transaction_id].transaction_date.strftime("%Y-%m"),
            posting.currency_code,
        )
        for posting in postings
        if posting.category_id is not None and posting.transaction_id in transactions
    }
    if not keys:
        return set()
    category_ids = {category_id for category_id, _, _ in keys}
    budgets = list(
        (
            await db.scalars(
                select(MoneyBudget).where(
                    MoneyBudget.user_id == user_id,
                    MoneyBudget.category_id.in_(category_ids),
                )
            )
        ).all()
    )
    return {
        budget.id
        for budget in budgets
        if (budget.category_id, budget.period, budget.currency_code) in keys
    }


async def refresh_money_rag(
    db: AsyncSession,
    user_id: str,
    *,
    account_ids: Iterable[str] = (),
    payee_ids: Iterable[str] = (),
    category_ids: Iterable[str] = (),
    budget_ids: Iterable[str] = (),
    transaction_ids: Iterable[str] = (),
    recurring_ids: Iterable[str] = (),
    installment_ids: Iterable[str] = (),
    now: datetime | None = None,
) -> None:
    """Refresh changed money records and their owner-scoped dependents."""

    account_set = set(account_ids)
    payee_set = set(payee_ids)
    category_set = set(category_ids)
    budget_set = set(budget_ids)
    transaction_set = set(transaction_ids)
    recurring_set = set(recurring_ids)
    installment_set = set(installment_ids)

    if account_set:
        transaction_set.update(
            await db.scalars(
                select(MoneyPosting.transaction_id).where(
                    MoneyPosting.user_id == user_id,
                    MoneyPosting.account_id.in_(account_set),
                )
            )
        )
        recurring_set.update(
            await db.scalars(
                select(MoneyRecurringPosting.recurring_transaction_id).where(
                    MoneyRecurringPosting.user_id == user_id,
                    MoneyRecurringPosting.account_id.in_(account_set),
                )
            )
        )
        installment_set.update(
            await db.scalars(
                select(MoneyInstallmentPlan.id).where(
                    MoneyInstallmentPlan.user_id == user_id,
                    MoneyInstallmentPlan.account_id.in_(account_set),
                )
            )
        )
    if payee_set:
        transaction_set.update(
            await db.scalars(
                select(MoneyTransaction.id).where(
                    MoneyTransaction.user_id == user_id,
                    MoneyTransaction.payee_id.in_(payee_set),
                )
            )
        )
        recurring_set.update(
            await db.scalars(
                select(MoneyRecurringTransaction.id).where(
                    MoneyRecurringTransaction.user_id == user_id,
                    MoneyRecurringTransaction.payee_id.in_(payee_set),
                )
            )
        )
        installment_set.update(
            await db.scalars(
                select(MoneyInstallmentPlan.id).where(
                    MoneyInstallmentPlan.user_id == user_id,
                    MoneyInstallmentPlan.payee_id.in_(payee_set),
                )
            )
        )
    if category_set:
        budget_set.update(
            await db.scalars(
                select(MoneyBudget.id).where(
                    MoneyBudget.user_id == user_id,
                    MoneyBudget.category_id.in_(category_set),
                )
            )
        )
        transaction_set.update(
            await db.scalars(
                select(MoneyPosting.transaction_id).where(
                    MoneyPosting.user_id == user_id,
                    MoneyPosting.category_id.in_(category_set),
                )
            )
        )
        recurring_set.update(
            await db.scalars(
                select(MoneyRecurringPosting.recurring_transaction_id).where(
                    MoneyRecurringPosting.user_id == user_id,
                    MoneyRecurringPosting.category_id.in_(category_set),
                )
            )
        )
        installment_set.update(
            await db.scalars(
                select(MoneyInstallmentPlan.id).where(
                    MoneyInstallmentPlan.user_id == user_id,
                    MoneyInstallmentPlan.category_id.in_(category_set),
                )
            )
        )
    if installment_set:
        transaction_set.update(
            await db.scalars(
                select(MoneyInstallmentOccurrence.transaction_id).where(
                    MoneyInstallmentOccurrence.user_id == user_id,
                    MoneyInstallmentOccurrence.plan_id.in_(installment_set),
                    MoneyInstallmentOccurrence.transaction_id.is_not(None),
                )
            )
        )
    if transaction_set:
        transaction_postings = list(
            (
                await db.scalars(
                    select(MoneyPosting).where(
                        MoneyPosting.user_id == user_id,
                        MoneyPosting.transaction_id.in_(transaction_set),
                    )
                )
            ).all()
        )
        account_set.update(
            posting.account_id for posting in transaction_postings if posting.account_id is not None
        )
        category_set.update(
            posting.category_id
            for posting in transaction_postings
            if posting.category_id is not None
        )
        budget_set.update(await budget_ids_for_transactions(db, user_id, tuple(transaction_set)))
    if recurring_set:
        recurring_postings = list(
            (
                await db.scalars(
                    select(MoneyRecurringPosting).where(
                        MoneyRecurringPosting.user_id == user_id,
                        MoneyRecurringPosting.recurring_transaction_id.in_(recurring_set),
                    )
                )
            ).all()
        )
        account_set.update(
            posting.account_id for posting in recurring_postings if posting.account_id is not None
        )
        category_set.update(
            posting.category_id for posting in recurring_postings if posting.category_id is not None
        )
    if installment_set:
        plans = list(
            (
                await db.scalars(
                    select(MoneyInstallmentPlan).where(
                        MoneyInstallmentPlan.user_id == user_id,
                        MoneyInstallmentPlan.id.in_(installment_set),
                    )
                )
            ).all()
        )
        account_set.update(plan.account_id for plan in plans)
        category_set.update(plan.category_id for plan in plans)
        budget_set.update(
            await db.scalars(
                select(MoneyBudget.id).where(
                    MoneyBudget.user_id == user_id,
                    MoneyBudget.category_id.in_(category_set),
                )
            )
        )

    for source_type, source_ids in (
        ("money_account", account_set),
        ("money_payee", payee_set),
        ("money_category", category_set),
        ("money_budget", budget_set),
        ("money_transaction", transaction_set),
        ("money_recurring", recurring_set),
        ("money_installment", installment_set),
    ):
        for source_id in sorted(source_ids):
            await refresh_money_source(
                db,
                user_id,
                source_type,  # type: ignore[arg-type]
                source_id,
                now=now,
            )
