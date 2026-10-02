"""Owner-scoped money use cases over the shared database storage seam."""

from __future__ import annotations

import base64
import binascii
import calendar
import hashlib
import json
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_DOWN, Decimal
from typing import cast
from uuid import uuid4

from sqlalchemy import delete, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..recurrence import (
    CalendarOccurrence,
    iter_calendar_occurrences,
    local_date,
    next_calendar_occurrence,
    timezone_or_error,
)
from ..storage import DatabaseStorage
from .errors import (
    AccountNotFoundError,
    BudgetNotFoundError,
    CategoryNotFoundError,
    CurrencyMismatchError,
    DuplicateMoneyNameError,
    InstallmentPlanLockedError,
    InstallmentPlanNotFoundError,
    InvalidCreditCardSettingsError,
    InvalidInstallmentPlanError,
    InvalidMoneyCursorError,
    InvalidMoneyQueryError,
    InvalidPostingTargetError,
    InvalidReconciliationTargetError,
    InvalidReconciliationTransitionError,
    InvalidRecurringTransactionError,
    InvalidSplitTransactionError,
    PayeeNotFoundError,
    PostingNotFoundError,
    RecurringTransactionNotFoundError,
    RecurringTransactionStateError,
    ReversalNotAllowedError,
    TransactionLockedError,
    TransactionNotFoundError,
    TransactionRestoreNotAllowedError,
    TransactionTooSmallError,
    TransactionVoidedError,
    TransactionVoidNotAllowedError,
    UnbalancedTransactionError,
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
from .schemas import (
    SUPPORTED_CURRENCY_EXPONENTS,
    AccountCreateRequest,
    AccountType,
    AccountUpdateRequest,
    BudgetUpsertRequest,
    CategoryCreateRequest,
    CategoryKind,
    CategoryUpdateRequest,
    InstallmentOccurrenceState,
    InstallmentPlanCreateRequest,
    InstallmentPlanState,
    MoneyRecurrenceFrequency,
    MoneyRecurrenceState,
    MoneyRecurrenceWeekday,
    PayeeCreateRequest,
    PayeeUpdateRequest,
    PostingRequest,
    ReconciliationState,
    RecurringOccurrenceState,
    RecurringTransactionCreateRequest,
    RecurringTransactionUpdateRequest,
    TransactionCreateRequest,
    TransactionPostingRequest,
    TransactionReverseRequest,
    TransactionState,
    TransactionUpdateRequest,
    TransactionVoidReason,
    canonical_amount,
    normalize_currency,
    normalize_name,
    validate_period,
)

DEFAULT_LIMIT = 50
MAX_LIMIT = 100


@dataclass(frozen=True)
class AccountRecord:
    id: str
    name: str
    account_type: AccountType
    institution_name: str | None
    last_four: str | None
    currency_code: str
    opening_balance: str
    balance: str
    credit_limit: str | None
    amount_owed: str | None
    available_credit: str | None
    statement_close_day: int | None
    payment_due_day: int | None
    next_statement_close_date: date | None
    next_payment_due_date: date | None
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


@dataclass(frozen=True)
class PayeeRecord:
    id: str
    name: str
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


@dataclass(frozen=True)
class CategoryRecord:
    id: str
    name: str
    kind: CategoryKind
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


@dataclass(frozen=True)
class BudgetRecord:
    id: str
    category_id: str
    period: str
    currency_code: str
    amount: str
    spent_amount: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class MoneySummaryRecord:
    period: str
    currency_code: str
    total_balance: str
    income_amount: str
    spending_amount: str
    budget_amount: str
    budget_spent_amount: str
    budget_remaining_amount: str


@dataclass(frozen=True)
class PostingRecord:
    id: str
    position: int
    label: str | None
    account_id: str | None
    category_id: str | None
    currency_code: str
    amount: str
    reconciliation_state: ReconciliationState
    cleared_at: datetime | None
    reconciled_at: datetime | None


@dataclass(frozen=True)
class TransactionRecord:
    id: str
    transaction_date: date
    name: str
    payee_id: str | None
    memo: str | None
    state: str
    reversal_of_id: str | None
    postings: list[PostingRecord]
    created_at: datetime
    updated_at: datetime
    voided_at: datetime | None
    void_reason: TransactionVoidReason | None


@dataclass(frozen=True)
class InstallmentOccurrenceRecord:
    id: str
    sequence_number: int
    charge_date: date
    amount: str
    status: InstallmentOccurrenceState
    transaction_id: str | None
    charged_at: datetime | None


@dataclass(frozen=True)
class InstallmentPlanRecord:
    id: str
    account_id: str
    payee_id: str | None
    category_id: str
    currency_code: str
    purchase_date: date
    name: str
    memo: str | None
    total_amount: str
    fee_amount: str
    term_months: int
    status: InstallmentPlanState
    charged_count: int
    next_charge_date: date | None
    next_charge_amount: str | None
    remaining_amount: str
    occurrences: list[InstallmentOccurrenceRecord]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class RecurringPostingRecord:
    id: str
    account_id: str | None
    category_id: str | None
    currency_code: str
    amount: str


@dataclass(frozen=True)
class RecurringOccurrenceRecord:
    id: str
    sequence_number: int
    due_date: date
    status: RecurringOccurrenceState
    transaction_id: str | None
    processed_at: datetime | None


@dataclass(frozen=True)
class RecurringTransactionRecord:
    id: str
    start_date: date
    name: str
    payee_id: str | None
    memo: str | None
    timezone: str
    frequency: MoneyRecurrenceFrequency
    interval: int
    weekdays: list[MoneyRecurrenceWeekday]
    month_day: int | None
    month: int | None
    day: int | None
    until_date: date | None
    occurrence_count: int | None
    state: MoneyRecurrenceState
    next_occurrence_date: date | None
    next_occurrence_number: int | None
    posted_count: int
    postings: list[RecurringPostingRecord]
    occurrences: list[RecurringOccurrenceRecord]
    created_at: datetime
    updated_at: datetime
    paused_at: datetime | None
    ended_at: datetime | None


@dataclass(frozen=True)
class AccountListFilters:
    include_archived: bool = False
    archived_only: bool = False
    search: str | None = None
    limit: int = DEFAULT_LIMIT
    cursor: str | None = None


@dataclass(frozen=True)
class PayeeListFilters:
    include_archived: bool = False
    search: str | None = None
    limit: int = DEFAULT_LIMIT
    cursor: str | None = None


@dataclass(frozen=True)
class CategoryListFilters:
    include_archived: bool = False
    kind: CategoryKind | None = None
    search: str | None = None
    limit: int = DEFAULT_LIMIT
    cursor: str | None = None


@dataclass(frozen=True)
class BudgetListFilters:
    period: str | None = None
    currency_code: str | None = None
    category_id: str | None = None
    limit: int = DEFAULT_LIMIT
    cursor: str | None = None


@dataclass(frozen=True)
class TransactionListFilters:
    date_from: date | None = None
    date_to: date | None = None
    search: str | None = None
    account_id: str | None = None
    payee_id: str | None = None
    category_id: str | None = None
    currency_code: str | None = None
    reconciliation_state: ReconciliationState | None = None
    include_voided: bool = False
    limit: int = DEFAULT_LIMIT
    cursor: str | None = None


@dataclass(frozen=True)
class InstallmentPlanListFilters:
    account_id: str | None = None
    status: InstallmentPlanState | None = None
    limit: int = DEFAULT_LIMIT
    cursor: str | None = None


@dataclass(frozen=True)
class RecurringTransactionListFilters:
    state: MoneyRecurrenceState | None = None
    account_id: str | None = None
    search: str | None = None
    limit: int = DEFAULT_LIMIT
    cursor: str | None = None


@dataclass(frozen=True)
class AccountPage:
    items: list[AccountRecord]
    next_cursor: str | None


@dataclass(frozen=True)
class PayeePage:
    items: list[PayeeRecord]
    next_cursor: str | None


@dataclass(frozen=True)
class CategoryPage:
    items: list[CategoryRecord]
    next_cursor: str | None


@dataclass(frozen=True)
class BudgetPage:
    items: list[BudgetRecord]
    next_cursor: str | None


@dataclass(frozen=True)
class TransactionPage:
    items: list[TransactionRecord]
    next_cursor: str | None


@dataclass(frozen=True)
class InstallmentPlanPage:
    items: list[InstallmentPlanRecord]
    next_cursor: str | None


@dataclass(frozen=True)
class RecurringTransactionPage:
    items: list[RecurringTransactionRecord]
    next_cursor: str | None


@dataclass(frozen=True)
class RecurringProcessResult:
    processed_count: int
    failed_count: int


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _decimal(value: str) -> Decimal:
    return Decimal(value)


def _decimal_text(value: Decimal, currency_code: str) -> str:
    return canonical_amount(format(value, "f"), currency_code)


def _validate_limit(limit: int) -> int:
    if not 1 <= limit <= MAX_LIMIT:
        raise InvalidMoneyQueryError()
    return limit


def _filter_fingerprint(filters: object) -> str:
    payload = {key: value for key, value in vars(filters).items() if key not in {"cursor", "limit"}}
    for key, value in list(payload.items()):
        if isinstance(value, (date, datetime)):
            payload[key] = value.isoformat()
        elif hasattr(value, "value"):
            payload[key] = value.value
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _normalize_transaction_search(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.strip().split()).casefold()
    if len(normalized) > 200:
        raise InvalidMoneyQueryError()
    return normalized or None


def _encode_cursor(payload: dict[str, object]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str, fingerprint: str) -> dict[str, object]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
        if not isinstance(payload, dict) or payload.get("v") != 1:
            raise ValueError
        if payload.get("f") != fingerprint:
            raise ValueError
        return payload
    except (binascii.Error, ValueError, TypeError, json.JSONDecodeError):
        raise InvalidMoneyCursorError() from None


def _cursor_payload(updated_at: datetime, resource_id: str, fingerprint: str) -> dict[str, object]:
    return {
        "v": 1,
        "f": fingerprint,
        "updated_at": (_as_utc(updated_at) or updated_at).isoformat(),
        "id": resource_id,
    }


def _parse_updated_cursor(cursor: str, fingerprint: str) -> tuple[datetime, str]:
    payload = _decode_cursor(cursor, fingerprint)
    try:
        updated_at = datetime.fromisoformat(str(payload["updated_at"]))
        resource_id = payload["id"]
        if updated_at.tzinfo is None or not isinstance(resource_id, str) or not resource_id:
            raise ValueError
        return updated_at, resource_id
    except (KeyError, TypeError, ValueError):
        raise InvalidMoneyCursorError() from None


def _month_date(year: int, month: int, day: int) -> date:
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def _shift_month(year: int, month: int, months: int) -> tuple[int, int]:
    absolute_month = year * 12 + month - 1 + months
    shifted_year, month_index = divmod(absolute_month, 12)
    return shifted_year, month_index + 1


def _month_date_offset(value: date, day: int, months: int) -> date:
    year, month = _shift_month(value.year, value.month, months)
    return _month_date(year, month, day)


def _next_statement_close_date(
    account: MoneyAccount, value: date, *, strictly_after: bool = False
) -> date | None:
    if account.statement_close_day is None:
        return None
    candidate = _month_date(value.year, value.month, account.statement_close_day)
    if candidate < value or (strictly_after and candidate <= value):
        candidate = _month_date_offset(candidate, account.statement_close_day, 1)
    return candidate


def _next_payment_due_date(account: MoneyAccount, close_date: date | None) -> date | None:
    if close_date is None or account.payment_due_day is None:
        return None
    candidate = _month_date(close_date.year, close_date.month, account.payment_due_day)
    if candidate <= close_date:
        candidate = _month_date_offset(candidate, account.payment_due_day, 1)
    return candidate


def _account_record(account: MoneyAccount, balance: Decimal) -> AccountRecord:
    is_card = account.account_type == AccountType.CREDIT_CARD.value
    amount_owed: str | None = None
    available_credit: str | None = None
    next_close: date | None = None
    next_due: date | None = None
    credit_limit = account.credit_limit
    if is_card and credit_limit is not None:
        limit = _decimal(credit_limit)
        amount_owed = _decimal_text(max(-balance, Decimal(0)), account.currency_code)
        available_credit = _decimal_text(limit + balance, account.currency_code)
        next_close = _next_statement_close_date(account, datetime.now(UTC).date())
        next_due = _next_payment_due_date(account, next_close)
    return AccountRecord(
        id=account.id,
        name=account.name,
        account_type=AccountType(account.account_type),
        institution_name=account.institution_name,
        last_four=account.last_four,
        currency_code=account.currency_code,
        opening_balance=(
            _decimal_text(-_decimal(account.opening_balance), account.currency_code)
            if is_card
            else account.opening_balance
        ),
        balance=_decimal_text(balance, account.currency_code),
        credit_limit=credit_limit,
        amount_owed=amount_owed,
        available_credit=available_credit,
        statement_close_day=account.statement_close_day,
        payment_due_day=account.payment_due_day,
        next_statement_close_date=next_close,
        next_payment_due_date=next_due,
        created_at=_as_utc(account.created_at) or account.created_at,
        updated_at=_as_utc(account.updated_at) or account.updated_at,
        archived_at=_as_utc(account.archived_at),
    )


def _payee_record(payee: MoneyPayee) -> PayeeRecord:
    return PayeeRecord(
        id=payee.id,
        name=payee.name,
        created_at=_as_utc(payee.created_at) or payee.created_at,
        updated_at=_as_utc(payee.updated_at) or payee.updated_at,
        archived_at=_as_utc(payee.archived_at),
    )


def _category_record(category: MoneyCategory) -> CategoryRecord:
    return CategoryRecord(
        id=category.id,
        name=category.name,
        kind=CategoryKind(category.kind),
        created_at=_as_utc(category.created_at) or category.created_at,
        updated_at=_as_utc(category.updated_at) or category.updated_at,
        archived_at=_as_utc(category.archived_at),
    )


def _posting_record(posting: MoneyPosting) -> PostingRecord:
    return PostingRecord(
        id=posting.id,
        position=posting.position,
        label=posting.label,
        account_id=posting.account_id,
        category_id=posting.category_id,
        currency_code=posting.currency_code,
        amount=posting.amount,
        reconciliation_state=ReconciliationState(posting.reconciliation_state),
        cleared_at=_as_utc(posting.cleared_at),
        reconciled_at=_as_utc(posting.reconciled_at),
    )


def _transaction_record(
    transaction: MoneyTransaction,
    postings: list[MoneyPosting],
) -> TransactionRecord:
    return TransactionRecord(
        id=transaction.id,
        transaction_date=transaction.transaction_date,
        name=transaction.name,
        payee_id=transaction.payee_id,
        memo=transaction.memo,
        state=transaction.state,
        reversal_of_id=transaction.reversal_of_id,
        postings=[_posting_record(posting) for posting in postings],
        created_at=_as_utc(transaction.created_at) or transaction.created_at,
        updated_at=_as_utc(transaction.updated_at) or transaction.updated_at,
        voided_at=_as_utc(transaction.voided_at),
        void_reason=(
            TransactionVoidReason(transaction.void_reason)
            if transaction.void_reason is not None
            else None
        ),
    )


def _occurrence_record(occurrence: MoneyInstallmentOccurrence) -> InstallmentOccurrenceRecord:
    return InstallmentOccurrenceRecord(
        id=occurrence.id,
        sequence_number=occurrence.sequence_number,
        charge_date=occurrence.charge_date,
        amount=occurrence.amount,
        status=InstallmentOccurrenceState(occurrence.status),
        transaction_id=occurrence.transaction_id,
        charged_at=_as_utc(occurrence.charged_at),
    )


async def _installment_plan_record(
    db: AsyncSession, plan: MoneyInstallmentPlan
) -> InstallmentPlanRecord:
    occurrences = list(
        (
            await db.execute(
                select(MoneyInstallmentOccurrence)
                .where(MoneyInstallmentOccurrence.plan_id == plan.id)
                .order_by(MoneyInstallmentOccurrence.sequence_number.asc())
            )
        )
        .scalars()
        .all()
    )
    charged = [item for item in occurrences if item.status == InstallmentOccurrenceState.CHARGED]
    scheduled = [
        item for item in occurrences if item.status == InstallmentOccurrenceState.SCHEDULED
    ]
    remaining = sum((_decimal(item.amount) for item in scheduled), Decimal(0))
    return InstallmentPlanRecord(
        id=plan.id,
        account_id=plan.account_id,
        payee_id=plan.payee_id,
        category_id=plan.category_id,
        currency_code=plan.currency_code,
        purchase_date=plan.purchase_date,
        name=plan.name,
        memo=plan.memo,
        total_amount=plan.total_amount,
        fee_amount=plan.fee_amount,
        term_months=plan.term_months,
        status=InstallmentPlanState(plan.status),
        charged_count=len(charged),
        next_charge_date=scheduled[0].charge_date if scheduled else None,
        next_charge_amount=scheduled[0].amount if scheduled else None,
        remaining_amount=_decimal_text(remaining, plan.currency_code),
        occurrences=[_occurrence_record(item) for item in occurrences],
        created_at=_as_utc(plan.created_at) or plan.created_at,
        updated_at=_as_utc(plan.updated_at) or plan.updated_at,
    )


def _recurring_rule_values(schedule: MoneyRecurringTransaction) -> dict[str, object]:
    return {
        "timezone": schedule.timezone,
        "frequency": schedule.rule["frequency"],
        "interval": schedule.rule.get("interval", 1),
        "weekdays": schedule.rule.get("weekdays", []),
        "month_day": schedule.rule.get("month_day"),
        "month": schedule.rule.get("month"),
        "day": schedule.rule.get("day"),
        "until_date": schedule.until_date,
        "occurrence_count": schedule.occurrence_count,
    }


async def _recurring_transaction_record(
    db: AsyncSession, schedule: MoneyRecurringTransaction
) -> RecurringTransactionRecord:
    postings = list(
        (
            await db.execute(
                select(MoneyRecurringPosting)
                .where(MoneyRecurringPosting.recurring_transaction_id == schedule.id)
                .order_by(MoneyRecurringPosting.id.asc())
            )
        )
        .scalars()
        .all()
    )
    occurrences = list(
        (
            await db.execute(
                select(MoneyRecurringOccurrence)
                .where(MoneyRecurringOccurrence.recurring_transaction_id == schedule.id)
                .order_by(MoneyRecurringOccurrence.due_date.asc())
            )
        )
        .scalars()
        .all()
    )
    values = _recurring_rule_values(schedule)
    raw_weekdays = cast(list[object], values["weekdays"])
    return RecurringTransactionRecord(
        id=schedule.id,
        start_date=schedule.start_date,
        name=schedule.name,
        payee_id=schedule.payee_id,
        memo=schedule.memo,
        timezone=schedule.timezone,
        frequency=MoneyRecurrenceFrequency(str(values["frequency"])),
        interval=int(cast(int, values["interval"])),
        weekdays=[MoneyRecurrenceWeekday(str(value)) for value in raw_weekdays],
        month_day=cast(int | None, values["month_day"]),
        month=cast(int | None, values["month"]),
        day=cast(int | None, values["day"]),
        until_date=schedule.until_date,
        occurrence_count=schedule.occurrence_count,
        state=MoneyRecurrenceState(schedule.state),
        next_occurrence_date=schedule.next_occurrence_date,
        next_occurrence_number=schedule.next_occurrence_number,
        posted_count=sum(
            item.status == RecurringOccurrenceState.POSTED.value for item in occurrences
        ),
        postings=[
            RecurringPostingRecord(
                id=item.id,
                account_id=item.account_id,
                category_id=item.category_id,
                currency_code=item.currency_code,
                amount=item.amount,
            )
            for item in postings
        ],
        occurrences=[
            RecurringOccurrenceRecord(
                id=item.id,
                sequence_number=item.sequence_number,
                due_date=item.due_date,
                status=RecurringOccurrenceState(item.status),
                transaction_id=item.transaction_id,
                processed_at=_as_utc(item.processed_at),
            )
            for item in occurrences
        ],
        created_at=_as_utc(schedule.created_at) or schedule.created_at,
        updated_at=_as_utc(schedule.updated_at) or schedule.updated_at,
        paused_at=_as_utc(schedule.paused_at),
        ended_at=_as_utc(schedule.ended_at),
    )


async def _account_balance(db: AsyncSession, account: MoneyAccount) -> Decimal:
    result = await db.execute(
        select(MoneyPosting.amount)
        .join(MoneyTransaction, MoneyTransaction.id == MoneyPosting.transaction_id)
        .where(
            MoneyPosting.account_id == account.id,
            MoneyTransaction.user_id == account.user_id,
            MoneyTransaction.state == "posted",
            MoneyTransaction.reversal_of_id.is_(None),
        )
    )
    return _decimal(account.opening_balance) + sum(
        (_decimal(value) for (value,) in result.all()), Decimal(0)
    )


async def _spent_for_budget(
    db: AsyncSession,
    user_id: str,
    category_id: str,
    period: str,
    currency_code: str,
) -> Decimal:
    year, month = (int(part) for part in period.split("-"))
    start = date(year, month, 1)
    end = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
    result = await db.execute(
        select(MoneyPosting.amount)
        .join(MoneyTransaction, MoneyTransaction.id == MoneyPosting.transaction_id)
        .where(
            MoneyPosting.user_id == user_id,
            MoneyPosting.category_id == category_id,
            MoneyPosting.currency_code == currency_code,
            MoneyTransaction.transaction_date >= start,
            MoneyTransaction.transaction_date < end,
            MoneyTransaction.state == "posted",
            MoneyTransaction.reversal_of_id.is_(None),
        )
    )
    return sum((_decimal(value) for (value,) in result.all()), Decimal(0))


async def get_money_summary(
    storage: DatabaseStorage,
    user_id: str,
    period: str,
    currency_code: str = "PHP",
) -> MoneySummaryRecord:
    period = validate_period(period)
    currency_code = normalize_currency(currency_code)
    year, month = (int(part) for part in period.split("-"))
    start = date(year, month, 1)
    end = date(year + (month == 12), 1 if month == 12 else month + 1, 1)

    async with storage.session() as db:
        accounts = list(
            (
                await db.execute(
                    select(MoneyAccount).where(
                        MoneyAccount.user_id == user_id,
                        MoneyAccount.currency_code == currency_code,
                        MoneyAccount.archived_at.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        total_balance = Decimal(0)
        for account in accounts:
            total_balance += await _account_balance(db, account)

        category_postings = await db.execute(
            select(MoneyPosting.amount, MoneyCategory.kind)
            .join(MoneyTransaction, MoneyTransaction.id == MoneyPosting.transaction_id)
            .join(MoneyCategory, MoneyCategory.id == MoneyPosting.category_id)
            .where(
                MoneyPosting.user_id == user_id,
                MoneyPosting.currency_code == currency_code,
                MoneyTransaction.transaction_date >= start,
                MoneyTransaction.transaction_date < end,
                MoneyTransaction.state == "posted",
                MoneyTransaction.reversal_of_id.is_(None),
            )
        )
        income_amount = Decimal(0)
        spending_amount = Decimal(0)
        for amount, kind in category_postings.all():
            value = _decimal(amount)
            if kind == CategoryKind.INCOME.value:
                income_amount -= value
            elif kind == CategoryKind.EXPENSE.value:
                spending_amount += value

        budgets = list(
            (
                await db.execute(
                    select(MoneyBudget).where(
                        MoneyBudget.user_id == user_id,
                        MoneyBudget.period == period,
                        MoneyBudget.currency_code == currency_code,
                    )
                )
            )
            .scalars()
            .all()
        )
        budget_amount = sum((_decimal(budget.amount) for budget in budgets), Decimal(0))
        budget_spent_amount = Decimal(0)
        for budget in budgets:
            budget_spent_amount += await _spent_for_budget(
                db,
                user_id,
                budget.category_id,
                period,
                currency_code,
            )

        return MoneySummaryRecord(
            period=period,
            currency_code=currency_code,
            total_balance=_decimal_text(total_balance, currency_code),
            income_amount=_decimal_text(income_amount, currency_code),
            spending_amount=_decimal_text(spending_amount, currency_code),
            budget_amount=_decimal_text(budget_amount, currency_code),
            budget_spent_amount=_decimal_text(budget_spent_amount, currency_code),
            budget_remaining_amount=_decimal_text(
                budget_amount - budget_spent_amount,
                currency_code,
            ),
        )


async def _get_account(
    db: AsyncSession, user_id: str, account_id: str, *, active_only: bool = False
) -> MoneyAccount:
    statement = select(MoneyAccount).where(
        MoneyAccount.id == account_id,
        MoneyAccount.user_id == user_id,
    )
    if active_only:
        statement = statement.where(MoneyAccount.archived_at.is_(None))
    account = await db.scalar(statement.limit(1))
    if account is None:
        raise AccountNotFoundError()
    return account


async def _get_payee(
    db: AsyncSession, user_id: str, payee_id: str, *, active_only: bool = False
) -> MoneyPayee:
    statement = select(MoneyPayee).where(MoneyPayee.id == payee_id, MoneyPayee.user_id == user_id)
    if active_only:
        statement = statement.where(MoneyPayee.archived_at.is_(None))
    payee = await db.scalar(statement.limit(1))
    if payee is None:
        raise PayeeNotFoundError()
    return payee


async def _get_category(
    db: AsyncSession, user_id: str, category_id: str, *, active_only: bool = False
) -> MoneyCategory:
    statement = select(MoneyCategory).where(
        MoneyCategory.id == category_id,
        MoneyCategory.user_id == user_id,
    )
    if active_only:
        statement = statement.where(MoneyCategory.archived_at.is_(None))
    category = await db.scalar(statement.limit(1))
    if category is None:
        raise CategoryNotFoundError()
    return category


async def _get_budget(db: AsyncSession, user_id: str, budget_id: str) -> MoneyBudget:
    budget = await db.scalar(
        select(MoneyBudget)
        .where(MoneyBudget.id == budget_id, MoneyBudget.user_id == user_id)
        .limit(1)
    )
    if budget is None:
        raise BudgetNotFoundError()
    return budget


async def _get_transaction(db: AsyncSession, user_id: str, transaction_id: str) -> MoneyTransaction:
    transaction = await db.scalar(
        select(MoneyTransaction)
        .where(MoneyTransaction.id == transaction_id, MoneyTransaction.user_id == user_id)
        .limit(1)
    )
    if transaction is None:
        raise TransactionNotFoundError()
    return transaction


async def _has_reversal(db: AsyncSession, transaction_id: str) -> bool:
    return (
        await db.scalar(
            select(MoneyTransaction.id)
            .where(MoneyTransaction.reversal_of_id == transaction_id)
            .limit(1)
        )
    ) is not None


async def _get_recurring_transaction(
    db: AsyncSession, user_id: str, recurring_transaction_id: str
) -> MoneyRecurringTransaction:
    schedule = await db.scalar(
        select(MoneyRecurringTransaction)
        .where(
            MoneyRecurringTransaction.id == recurring_transaction_id,
            MoneyRecurringTransaction.user_id == user_id,
        )
        .limit(1)
    )
    if schedule is None:
        raise RecurringTransactionNotFoundError()
    return schedule


async def _postings_for_transaction(db: AsyncSession, transaction_id: str) -> list[MoneyPosting]:
    result = await db.execute(
        select(MoneyPosting)
        .where(MoneyPosting.transaction_id == transaction_id)
        .order_by(MoneyPosting.position.asc(), MoneyPosting.id.asc())
    )
    return list(result.scalars().all())


async def _ensure_name_available(
    db: AsyncSession,
    model: type[MoneyPayee] | type[MoneyCategory],
    user_id: str,
    name: str,
    resource_id: str | None = None,
) -> None:
    statement = select(model.id).where(model.user_id == user_id, model.name == name)
    if resource_id is not None:
        statement = statement.where(model.id != resource_id)
    if await db.scalar(statement.limit(1)) is not None:
        raise DuplicateMoneyNameError()


async def create_account(
    storage: DatabaseStorage, user_id: str, payload: AccountCreateRequest
) -> AccountRecord:
    now = _utc_now()
    async with storage.session() as db:
        async with db.begin():
            opening_balance = payload.opening_balance
            if payload.account_type == AccountType.CREDIT_CARD:
                opening_balance = _decimal_text(
                    -_decimal(payload.opening_balance), payload.currency_code
                )
            account = MoneyAccount(
                id=str(uuid4()),
                user_id=user_id,
                name=payload.name,
                account_type=payload.account_type.value,
                institution_name=payload.institution_name,
                last_four=payload.last_four,
                currency_code=normalize_currency(payload.currency_code),
                opening_balance=opening_balance,
                credit_limit=payload.credit_limit,
                statement_close_day=payload.statement_close_day,
                payment_due_day=payload.payment_due_day,
                created_at=now,
                updated_at=now,
            )
            db.add(account)
            await db.flush()
            return _account_record(account, _decimal(account.opening_balance))


async def get_account(storage: DatabaseStorage, user_id: str, account_id: str) -> AccountRecord:
    async with storage.session() as db:
        account = await _get_account(db, user_id, account_id)
        return _account_record(account, await _account_balance(db, account))


async def update_account(
    storage: DatabaseStorage,
    user_id: str,
    account_id: str,
    payload: AccountUpdateRequest,
) -> AccountRecord:
    now = _utc_now()
    async with storage.session() as db:
        async with db.begin():
            account = await _get_account(db, user_id, account_id, active_only=True)
            fields = payload.model_fields_set
            if "name" in fields and payload.name is not None:
                account.name = payload.name
            if "institution_name" in fields:
                account.institution_name = payload.institution_name
            if "last_four" in fields:
                account.last_four = payload.last_four
            card_fields = {"credit_limit", "statement_close_day", "payment_due_day"}
            if fields & card_fields and account.account_type != AccountType.CREDIT_CARD.value:
                raise InvalidCreditCardSettingsError()
            if "credit_limit" in fields and payload.credit_limit is not None:
                account.credit_limit = canonical_amount(
                    payload.credit_limit, account.currency_code, allow_zero=False
                )
            if "statement_close_day" in fields:
                account.statement_close_day = payload.statement_close_day
            if "payment_due_day" in fields:
                account.payment_due_day = payload.payment_due_day
            if account.account_type == AccountType.CREDIT_CARD.value and fields & card_fields:
                if (
                    account.credit_limit is None
                    or account.statement_close_day is None
                    or account.payment_due_day is None
                ):
                    raise InvalidCreditCardSettingsError()
            if fields:
                account.updated_at = now
            await db.flush()
            return _account_record(account, await _account_balance(db, account))


async def archive_account(storage: DatabaseStorage, user_id: str, account_id: str) -> AccountRecord:
    now = _utc_now()
    async with storage.session() as db:
        async with db.begin():
            account = await _get_account(db, user_id, account_id)
            if account.archived_at is None:
                account.archived_at = now
                account.updated_at = now
            await db.flush()
            return _account_record(account, await _account_balance(db, account))


async def restore_account(storage: DatabaseStorage, user_id: str, account_id: str) -> AccountRecord:
    now = _utc_now()
    async with storage.session() as db:
        async with db.begin():
            account = await _get_account(db, user_id, account_id)
            if account.archived_at is not None:
                account.archived_at = None
                account.updated_at = now
            await db.flush()
            return _account_record(account, await _account_balance(db, account))


async def list_accounts(
    storage: DatabaseStorage, user_id: str, filters: AccountListFilters
) -> AccountPage:
    _validate_limit(filters.limit)
    fingerprint = _filter_fingerprint(filters)
    async with storage.session() as db:
        statement = select(MoneyAccount).where(MoneyAccount.user_id == user_id)
        if filters.archived_only:
            statement = statement.where(MoneyAccount.archived_at.is_not(None))
        elif not filters.include_archived:
            statement = statement.where(MoneyAccount.archived_at.is_(None))
        if filters.search:
            search = normalize_name(filters.search)
            statement = statement.where(func.lower(MoneyAccount.name).contains(search))
        if filters.cursor:
            updated_at, resource_id = _parse_updated_cursor(filters.cursor, fingerprint)
            statement = statement.where(
                (MoneyAccount.updated_at < updated_at)
                | ((MoneyAccount.updated_at == updated_at) & (MoneyAccount.id < resource_id))
            )
        statement = statement.order_by(
            MoneyAccount.updated_at.desc(), MoneyAccount.id.desc()
        ).limit(filters.limit + 1)
        accounts = list((await db.execute(statement)).scalars().all())
        next_cursor = None
        if len(accounts) > filters.limit:
            accounts.pop()
            last = accounts[-1]
            next_cursor = _encode_cursor(_cursor_payload(last.updated_at, last.id, fingerprint))
        records = [
            _account_record(account, await _account_balance(db, account)) for account in accounts
        ]
        return AccountPage(records, next_cursor)


async def create_payee(
    storage: DatabaseStorage, user_id: str, payload: PayeeCreateRequest
) -> PayeeRecord:
    now = _utc_now()
    async with storage.session() as db:
        async with db.begin():
            await _ensure_name_available(db, MoneyPayee, user_id, payload.name)
            payee = MoneyPayee(
                id=str(uuid4()),
                user_id=user_id,
                name=payload.name,
                created_at=now,
                updated_at=now,
            )
            db.add(payee)
            await db.flush()
            return _payee_record(payee)


async def get_payee(storage: DatabaseStorage, user_id: str, payee_id: str) -> PayeeRecord:
    async with storage.session() as db:
        return _payee_record(await _get_payee(db, user_id, payee_id))


async def update_payee(
    storage: DatabaseStorage, user_id: str, payee_id: str, payload: PayeeUpdateRequest
) -> PayeeRecord:
    now = _utc_now()
    async with storage.session() as db:
        async with db.begin():
            payee = await _get_payee(db, user_id, payee_id, active_only=True)
            if "name" in payload.model_fields_set and payload.name is not None:
                await _ensure_name_available(db, MoneyPayee, user_id, payload.name, payee.id)
                payee.name = payload.name
                payee.updated_at = now
            await db.flush()
            return _payee_record(payee)


async def archive_payee(storage: DatabaseStorage, user_id: str, payee_id: str) -> PayeeRecord:
    now = _utc_now()
    async with storage.session() as db:
        async with db.begin():
            payee = await _get_payee(db, user_id, payee_id)
            if payee.archived_at is None:
                payee.archived_at = now
                payee.updated_at = now
            await db.flush()
            return _payee_record(payee)


async def restore_payee(storage: DatabaseStorage, user_id: str, payee_id: str) -> PayeeRecord:
    now = _utc_now()
    async with storage.session() as db:
        async with db.begin():
            payee = await _get_payee(db, user_id, payee_id)
            if payee.archived_at is not None:
                payee.archived_at = None
                payee.updated_at = now
            await db.flush()
            return _payee_record(payee)


async def list_payees(
    storage: DatabaseStorage, user_id: str, filters: PayeeListFilters
) -> PayeePage:
    _validate_limit(filters.limit)
    fingerprint = _filter_fingerprint(filters)
    async with storage.session() as db:
        statement = select(MoneyPayee).where(MoneyPayee.user_id == user_id)
        if not filters.include_archived:
            statement = statement.where(MoneyPayee.archived_at.is_(None))
        if filters.search:
            statement = statement.where(MoneyPayee.name.contains(normalize_name(filters.search)))
        if filters.cursor:
            updated_at, resource_id = _parse_updated_cursor(filters.cursor, fingerprint)
            statement = statement.where(
                (MoneyPayee.updated_at < updated_at)
                | ((MoneyPayee.updated_at == updated_at) & (MoneyPayee.id < resource_id))
            )
        statement = statement.order_by(MoneyPayee.updated_at.desc(), MoneyPayee.id.desc()).limit(
            filters.limit + 1
        )
        payees = list((await db.execute(statement)).scalars().all())
        next_cursor = None
        if len(payees) > filters.limit:
            payees.pop()
            last = payees[-1]
            next_cursor = _encode_cursor(_cursor_payload(last.updated_at, last.id, fingerprint))
        return PayeePage([_payee_record(payee) for payee in payees], next_cursor)


async def create_category(
    storage: DatabaseStorage, user_id: str, payload: CategoryCreateRequest
) -> CategoryRecord:
    now = _utc_now()
    async with storage.session() as db:
        async with db.begin():
            await _ensure_name_available(db, MoneyCategory, user_id, payload.name)
            category = MoneyCategory(
                id=str(uuid4()),
                user_id=user_id,
                name=payload.name,
                kind=payload.kind.value,
                created_at=now,
                updated_at=now,
            )
            db.add(category)
            await db.flush()
            return _category_record(category)


async def get_category(storage: DatabaseStorage, user_id: str, category_id: str) -> CategoryRecord:
    async with storage.session() as db:
        return _category_record(await _get_category(db, user_id, category_id))


async def update_category(
    storage: DatabaseStorage,
    user_id: str,
    category_id: str,
    payload: CategoryUpdateRequest,
) -> CategoryRecord:
    now = _utc_now()
    async with storage.session() as db:
        async with db.begin():
            category = await _get_category(db, user_id, category_id, active_only=True)
            if "name" in payload.model_fields_set and payload.name is not None:
                await _ensure_name_available(db, MoneyCategory, user_id, payload.name, category.id)
                category.name = payload.name
                category.updated_at = now
            await db.flush()
            return _category_record(category)


async def archive_category(
    storage: DatabaseStorage, user_id: str, category_id: str
) -> CategoryRecord:
    now = _utc_now()
    async with storage.session() as db:
        async with db.begin():
            category = await _get_category(db, user_id, category_id)
            if category.archived_at is None:
                category.archived_at = now
                category.updated_at = now
            await db.flush()
            return _category_record(category)


async def restore_category(
    storage: DatabaseStorage, user_id: str, category_id: str
) -> CategoryRecord:
    now = _utc_now()
    async with storage.session() as db:
        async with db.begin():
            category = await _get_category(db, user_id, category_id)
            if category.archived_at is not None:
                category.archived_at = None
                category.updated_at = now
            await db.flush()
            return _category_record(category)


async def list_categories(
    storage: DatabaseStorage, user_id: str, filters: CategoryListFilters
) -> CategoryPage:
    _validate_limit(filters.limit)
    fingerprint = _filter_fingerprint(filters)
    async with storage.session() as db:
        statement = select(MoneyCategory).where(MoneyCategory.user_id == user_id)
        if not filters.include_archived:
            statement = statement.where(MoneyCategory.archived_at.is_(None))
        if filters.kind is not None:
            statement = statement.where(MoneyCategory.kind == filters.kind.value)
        if filters.search:
            statement = statement.where(MoneyCategory.name.contains(normalize_name(filters.search)))
        if filters.cursor:
            updated_at, resource_id = _parse_updated_cursor(filters.cursor, fingerprint)
            statement = statement.where(
                (MoneyCategory.updated_at < updated_at)
                | ((MoneyCategory.updated_at == updated_at) & (MoneyCategory.id < resource_id))
            )
        statement = statement.order_by(
            MoneyCategory.updated_at.desc(), MoneyCategory.id.desc()
        ).limit(filters.limit + 1)
        categories = list((await db.execute(statement)).scalars().all())
        next_cursor = None
        if len(categories) > filters.limit:
            categories.pop()
            last = categories[-1]
            next_cursor = _encode_cursor(_cursor_payload(last.updated_at, last.id, fingerprint))
        return CategoryPage([_category_record(category) for category in categories], next_cursor)


async def _budget_record(db: AsyncSession, budget: MoneyBudget) -> BudgetRecord:
    spent = await _spent_for_budget(
        db,
        budget.user_id,
        budget.category_id,
        budget.period,
        budget.currency_code,
    )
    return BudgetRecord(
        id=budget.id,
        category_id=budget.category_id,
        period=budget.period,
        currency_code=budget.currency_code,
        amount=budget.amount,
        spent_amount=_decimal_text(spent, budget.currency_code),
        created_at=_as_utc(budget.created_at) or budget.created_at,
        updated_at=_as_utc(budget.updated_at) or budget.updated_at,
    )


async def upsert_budget(
    storage: DatabaseStorage,
    user_id: str,
    period: str,
    category_id: str,
    currency_code: str,
    payload: BudgetUpsertRequest,
) -> BudgetRecord:
    period = validate_period(period)
    currency_code = normalize_currency(currency_code)
    amount = canonical_amount(payload.amount, currency_code)
    if _decimal(amount) < 0:
        from .errors import InvalidMoneyAmountError

        raise InvalidMoneyAmountError()
    now = _utc_now()
    async with storage.session() as db:
        async with db.begin():
            category = await _get_category(db, user_id, category_id, active_only=True)
            if category.kind != CategoryKind.EXPENSE.value:
                raise InvalidPostingTargetError()
            budget = await db.scalar(
                select(MoneyBudget)
                .where(
                    MoneyBudget.user_id == user_id,
                    MoneyBudget.category_id == category_id,
                    MoneyBudget.period == period,
                    MoneyBudget.currency_code == currency_code,
                )
                .limit(1)
            )
            if budget is None:
                budget = MoneyBudget(
                    id=str(uuid4()),
                    user_id=user_id,
                    category_id=category_id,
                    period=period,
                    currency_code=currency_code,
                    amount=amount,
                    created_at=now,
                    updated_at=now,
                )
                db.add(budget)
            else:
                budget.amount = amount
                budget.updated_at = now
            await db.flush()
            return await _budget_record(db, budget)


async def get_budget(storage: DatabaseStorage, user_id: str, budget_id: str) -> BudgetRecord:
    async with storage.session() as db:
        return await _budget_record(db, await _get_budget(db, user_id, budget_id))


async def delete_budget(storage: DatabaseStorage, user_id: str, budget_id: str) -> None:
    async with storage.session() as db:
        async with db.begin():
            budget = await _get_budget(db, user_id, budget_id)
            await db.delete(budget)


async def list_budgets(
    storage: DatabaseStorage, user_id: str, filters: BudgetListFilters
) -> BudgetPage:
    _validate_limit(filters.limit)
    if filters.period is not None:
        validate_period(filters.period)
    currency_code = normalize_currency(filters.currency_code) if filters.currency_code else None
    fingerprint = _filter_fingerprint(
        BudgetListFilters(
            period=filters.period,
            currency_code=currency_code,
            category_id=filters.category_id,
            limit=filters.limit,
            cursor=None,
        )
    )
    async with storage.session() as db:
        statement = select(MoneyBudget).where(MoneyBudget.user_id == user_id)
        if filters.period is not None:
            statement = statement.where(MoneyBudget.period == filters.period)
        if currency_code is not None:
            statement = statement.where(MoneyBudget.currency_code == currency_code)
        if filters.category_id is not None:
            statement = statement.where(MoneyBudget.category_id == filters.category_id)
        if filters.cursor:
            updated_at, resource_id = _parse_updated_cursor(filters.cursor, fingerprint)
            statement = statement.where(
                (MoneyBudget.updated_at < updated_at)
                | ((MoneyBudget.updated_at == updated_at) & (MoneyBudget.id < resource_id))
            )
        statement = statement.order_by(MoneyBudget.updated_at.desc(), MoneyBudget.id.desc()).limit(
            filters.limit + 1
        )
        budgets = list((await db.execute(statement)).scalars().all())
        next_cursor = None
        if len(budgets) > filters.limit:
            budgets.pop()
            last = budgets[-1]
            next_cursor = _encode_cursor(_cursor_payload(last.updated_at, last.id, fingerprint))
        return BudgetPage([await _budget_record(db, budget) for budget in budgets], next_cursor)


async def _validate_postings(
    db: AsyncSession,
    user_id: str,
    postings: Sequence[PostingRequest],
    *,
    require_split_labels: bool = False,
) -> None:
    if len(postings) < 2:
        raise TransactionTooSmallError()
    totals: defaultdict[str, Decimal] = defaultdict(Decimal)
    for posting in postings:
        if posting.account_id is not None:
            account = await _get_account(db, user_id, posting.account_id, active_only=True)
            if account.currency_code != posting.currency_code:
                raise CurrencyMismatchError()
        elif posting.category_id is not None:
            await _get_category(db, user_id, posting.category_id, active_only=True)
        else:
            raise InvalidPostingTargetError()
        totals[posting.currency_code] += _decimal(posting.amount)
    if any(total != 0 for total in totals.values()):
        raise UnbalancedTransactionError()

    account_postings = [posting for posting in postings if posting.account_id is not None]
    category_postings = [posting for posting in postings if posting.category_id is not None]
    if not require_split_labels or len(account_postings) != 1 or len(category_postings) < 2:
        return

    if len({posting.currency_code for posting in postings}) != 1:
        raise InvalidSplitTransactionError()

    account_amount = _decimal(account_postings[0].amount)
    if any((account_amount > 0) == (_decimal(posting.amount) > 0) for posting in category_postings):
        raise InvalidSplitTransactionError()
    if any(getattr(posting, "label", None) is None for posting in category_postings):
        raise InvalidSplitTransactionError()


def _posting_from_request(
    user_id: str,
    transaction_id: str,
    request: TransactionPostingRequest,
    position: int,
) -> MoneyPosting:
    return MoneyPosting(
        id=str(uuid4()),
        user_id=user_id,
        transaction_id=transaction_id,
        position=position,
        label=request.label,
        account_id=request.account_id,
        category_id=request.category_id,
        currency_code=request.currency_code,
        amount=request.amount,
        reconciliation_state=ReconciliationState.UNCLEARED.value,
    )


async def _validate_payee(db: AsyncSession, user_id: str, payee_id: str | None) -> None:
    if payee_id is not None:
        await _get_payee(db, user_id, payee_id, active_only=True)


async def _create_transaction_in_session(
    db: AsyncSession,
    user_id: str,
    payload: TransactionCreateRequest,
    now: datetime,
    *,
    require_split_labels: bool = True,
) -> tuple[MoneyTransaction, list[MoneyPosting]]:
    await _validate_payee(db, user_id, payload.payee_id)
    await _validate_postings(
        db,
        user_id,
        payload.postings,
        require_split_labels=require_split_labels,
    )
    transaction = MoneyTransaction(
        id=str(uuid4()),
        user_id=user_id,
        transaction_date=payload.transaction_date,
        name=payload.name,
        payee_id=payload.payee_id,
        memo=payload.memo,
        state="posted",
        created_at=now,
        updated_at=now,
    )
    db.add(transaction)
    await db.flush()
    postings = [
        _posting_from_request(user_id, transaction.id, posting, position)
        for position, posting in enumerate(payload.postings)
    ]
    db.add_all(postings)
    await db.flush()
    return transaction, postings


async def create_transaction(
    storage: DatabaseStorage,
    user_id: str,
    payload: TransactionCreateRequest,
) -> TransactionRecord:
    now = _utc_now()
    async with storage.session() as db:
        async with db.begin():
            transaction, postings = await _create_transaction_in_session(db, user_id, payload, now)
            return _transaction_record(transaction, postings)


def _recurrence_rule_payload(
    payload: RecurringTransactionCreateRequest | RecurringTransactionUpdateRequest,
) -> dict[str, object]:
    assert payload.recurrence is not None
    values = payload.recurrence.model_dump(mode="json")
    values.pop("timezone", None)
    values.pop("until_date", None)
    values.pop("occurrence_count", None)
    return values


def _recurrence_parts(
    schedule: MoneyRecurringTransaction,
) -> tuple[str, int, tuple[int, ...], int | None, int | None, int | None]:
    raw_weekdays = cast(list[object], schedule.rule.get("weekdays", []))
    weekdays = tuple(
        {
            "monday": 0,
            "tuesday": 1,
            "wednesday": 2,
            "thursday": 3,
            "friday": 4,
            "saturday": 5,
            "sunday": 6,
        }[str(value)]
        for value in raw_weekdays
    )
    return (
        str(schedule.rule["frequency"]),
        int(cast(int, schedule.rule.get("interval", 1))),
        weekdays,
        cast(int | None, schedule.rule.get("month_day")),
        cast(int | None, schedule.rule.get("month")),
        cast(int | None, schedule.rule.get("day")),
    )


def _next_recurring_candidate(
    schedule: MoneyRecurringTransaction, current_date: date
) -> CalendarOccurrence | None:
    frequency, interval, weekdays, month_day, month, day = _recurrence_parts(schedule)
    return next_calendar_occurrence(
        schedule.start_date,
        frequency,
        interval,
        weekdays,
        month_day,
        month,
        day,
        schedule.until_date,
        schedule.occurrence_count,
        current_date,
    )


def _first_recurring_candidate(schedule: MoneyRecurringTransaction) -> CalendarOccurrence | None:
    frequency, interval, weekdays, month_day, month, day = _recurrence_parts(schedule)
    return next(
        iter_calendar_occurrences(
            schedule.start_date,
            frequency,
            interval,
            weekdays,
            month_day,
            month,
            day,
            schedule.until_date,
            schedule.occurrence_count,
            limit=1,
        ),
        None,
    )


def _set_next_recurring_candidate(
    schedule: MoneyRecurringTransaction, current_date: date, now: datetime
) -> None:
    candidate = _next_recurring_candidate(schedule, current_date)
    if candidate is None:
        schedule.next_occurrence_date = None
        schedule.next_occurrence_number = None
        schedule.state = MoneyRecurrenceState.ENDED.value
        schedule.ended_at = now
        return
    schedule.next_occurrence_date = candidate.occurrence_date
    schedule.next_occurrence_number = candidate.sequence_number


async def _recurring_posting_requests(
    db: AsyncSession, schedule_id: str
) -> list[TransactionPostingRequest]:
    rows = list(
        (
            await db.execute(
                select(MoneyRecurringPosting)
                .where(MoneyRecurringPosting.recurring_transaction_id == schedule_id)
                .order_by(MoneyRecurringPosting.id.asc())
            )
        )
        .scalars()
        .all()
    )
    return [
        TransactionPostingRequest(
            account_id=row.account_id,
            category_id=row.category_id,
            currency_code=row.currency_code,
            amount=row.amount,
        )
        for row in rows
    ]


async def _create_recurring_occurrence(
    db: AsyncSession,
    schedule: MoneyRecurringTransaction,
    occurrence_date: date,
    sequence_number: int,
    status: str = RecurringOccurrenceState.SCHEDULED.value,
) -> MoneyRecurringOccurrence:
    occurrence = MoneyRecurringOccurrence(
        id=str(uuid4()),
        user_id=schedule.user_id,
        recurring_transaction_id=schedule.id,
        sequence_number=sequence_number,
        due_date=occurrence_date,
        status=status,
    )
    db.add(occurrence)
    await db.flush()
    return occurrence


async def _ensure_next_recurring_occurrence(
    db: AsyncSession, schedule: MoneyRecurringTransaction
) -> None:
    if schedule.next_occurrence_date is None:
        return
    existing = await db.scalar(
        select(MoneyRecurringOccurrence).where(
            MoneyRecurringOccurrence.recurring_transaction_id == schedule.id,
            MoneyRecurringOccurrence.due_date == schedule.next_occurrence_date,
        )
    )
    if existing is None:
        await _create_recurring_occurrence(
            db,
            schedule,
            schedule.next_occurrence_date,
            schedule.next_occurrence_number or 1,
        )


async def create_recurring_transaction(
    storage: DatabaseStorage,
    user_id: str,
    payload: RecurringTransactionCreateRequest,
) -> RecurringTransactionRecord:
    now = _utc_now()
    try:
        timezone_or_error(payload.recurrence.timezone)
    except ValueError:
        raise InvalidRecurringTransactionError() from None
    async with storage.session() as db:
        async with db.begin():
            await _validate_payee(db, user_id, payload.payee_id)
            await _validate_postings(db, user_id, payload.postings)
            schedule = MoneyRecurringTransaction(
                id=str(uuid4()),
                user_id=user_id,
                start_date=payload.start_date,
                name=payload.name,
                payee_id=payload.payee_id,
                memo=payload.memo,
                timezone=payload.recurrence.timezone,
                rule=_recurrence_rule_payload(payload),
                until_date=payload.recurrence.until_date,
                occurrence_count=payload.recurrence.occurrence_count,
                state=MoneyRecurrenceState.ACTIVE.value,
                created_at=now,
                updated_at=now,
            )
            first = _first_recurring_candidate(schedule)
            if first is None:
                raise InvalidRecurringTransactionError()
            schedule.next_occurrence_date = first.occurrence_date
            schedule.next_occurrence_number = first.sequence_number
            db.add(schedule)
            await db.flush()
            db.add_all(
                [
                    MoneyRecurringPosting(
                        id=str(uuid4()),
                        user_id=user_id,
                        recurring_transaction_id=schedule.id,
                        account_id=posting.account_id,
                        category_id=posting.category_id,
                        currency_code=posting.currency_code,
                        amount=posting.amount,
                    )
                    for posting in payload.postings
                ]
            )
            await db.flush()
            await _create_recurring_occurrence(
                db, schedule, first.occurrence_date, first.sequence_number
            )
            return await _recurring_transaction_record(db, schedule)


async def get_recurring_transaction(
    storage: DatabaseStorage, user_id: str, recurring_transaction_id: str
) -> RecurringTransactionRecord:
    async with storage.session() as db:
        return await _recurring_transaction_record(
            db, await _get_recurring_transaction(db, user_id, recurring_transaction_id)
        )


async def list_recurring_transactions(
    storage: DatabaseStorage, user_id: str, filters: RecurringTransactionListFilters
) -> RecurringTransactionPage:
    _validate_limit(filters.limit)
    search = _normalize_transaction_search(filters.search)
    fingerprint = _filter_fingerprint(
        RecurringTransactionListFilters(
            state=filters.state,
            account_id=filters.account_id,
            search=search,
            limit=filters.limit,
            cursor=None,
        )
    )
    async with storage.session() as db:
        statement = select(MoneyRecurringTransaction).where(
            MoneyRecurringTransaction.user_id == user_id
        )
        if filters.state is not None:
            statement = statement.where(MoneyRecurringTransaction.state == filters.state.value)
        if filters.account_id is not None:
            statement = statement.where(
                exists().where(
                    MoneyRecurringPosting.recurring_transaction_id == MoneyRecurringTransaction.id,
                    MoneyRecurringPosting.account_id == filters.account_id,
                )
            )
        if search is not None:
            statement = statement.where(
                or_(
                    func.lower(MoneyRecurringTransaction.name).like(f"%{search}%"),
                    func.lower(MoneyRecurringTransaction.memo).like(f"%{search}%"),
                )
            )
        if filters.cursor:
            updated_at, resource_id = _parse_updated_cursor(filters.cursor, fingerprint)
            statement = statement.where(
                (MoneyRecurringTransaction.updated_at < updated_at)
                | (
                    (MoneyRecurringTransaction.updated_at == updated_at)
                    & (MoneyRecurringTransaction.id < resource_id)
                )
            )
        statement = statement.order_by(
            MoneyRecurringTransaction.updated_at.desc(),
            MoneyRecurringTransaction.id.desc(),
        ).limit(filters.limit + 1)
        schedules = list((await db.execute(statement)).scalars().all())
        next_cursor = None
        if len(schedules) > filters.limit:
            schedules.pop()
            last = schedules[-1]
            next_cursor = _encode_cursor(_cursor_payload(last.updated_at, last.id, fingerprint))
        return RecurringTransactionPage(
            [await _recurring_transaction_record(db, schedule) for schedule in schedules],
            next_cursor,
        )


async def update_recurring_transaction(
    storage: DatabaseStorage,
    user_id: str,
    recurring_transaction_id: str,
    payload: RecurringTransactionUpdateRequest,
) -> RecurringTransactionRecord:
    now = _utc_now()
    async with storage.session() as db:
        async with db.begin():
            schedule = await _get_recurring_transaction(db, user_id, recurring_transaction_id)
            if schedule.state == MoneyRecurrenceState.ENDED.value:
                raise RecurringTransactionStateError()
            values = payload.model_dump(exclude_unset=True)
            if payload.recurrence is not None:
                try:
                    timezone_or_error(payload.recurrence.timezone)
                except ValueError:
                    raise InvalidRecurringTransactionError() from None
                schedule.timezone = payload.recurrence.timezone
                schedule.rule = _recurrence_rule_payload(payload)
                schedule.until_date = payload.recurrence.until_date
                schedule.occurrence_count = payload.recurrence.occurrence_count
                await db.execute(
                    delete(MoneyRecurringOccurrence).where(
                        MoneyRecurringOccurrence.recurring_transaction_id == schedule.id,
                        MoneyRecurringOccurrence.status == RecurringOccurrenceState.SCHEDULED.value,
                    )
                )
                last_posted = await db.scalar(
                    select(MoneyRecurringOccurrence.due_date)
                    .where(
                        MoneyRecurringOccurrence.recurring_transaction_id == schedule.id,
                        MoneyRecurringOccurrence.status == RecurringOccurrenceState.POSTED.value,
                    )
                    .order_by(MoneyRecurringOccurrence.due_date.desc())
                    .limit(1)
                )
                first = _first_recurring_candidate(schedule)
                if last_posted is not None:
                    first = next(
                        iter_calendar_occurrences(
                            schedule.start_date,
                            *_recurrence_parts(schedule),
                            schedule.until_date,
                            schedule.occurrence_count,
                            after_date=last_posted,
                            limit=1,
                        ),
                        None,
                    )
                if first is None:
                    schedule.next_occurrence_date = None
                    schedule.next_occurrence_number = None
                    schedule.state = MoneyRecurrenceState.ENDED.value
                    schedule.ended_at = now
                else:
                    schedule.next_occurrence_date = first.occurrence_date
                    schedule.next_occurrence_number = first.sequence_number
                    await _create_recurring_occurrence(
                        db, schedule, first.occurrence_date, first.sequence_number
                    )
            if "name" in values and payload.name is not None:
                schedule.name = payload.name
            if "payee_id" in values:
                await _validate_payee(db, user_id, payload.payee_id)
                schedule.payee_id = payload.payee_id
            if "memo" in values:
                schedule.memo = payload.memo
            if payload.postings is not None:
                await _validate_postings(db, user_id, payload.postings)
                await db.execute(
                    delete(MoneyRecurringPosting).where(
                        MoneyRecurringPosting.recurring_transaction_id == schedule.id
                    )
                )
                db.add_all(
                    [
                        MoneyRecurringPosting(
                            id=str(uuid4()),
                            user_id=user_id,
                            recurring_transaction_id=schedule.id,
                            account_id=posting.account_id,
                            category_id=posting.category_id,
                            currency_code=posting.currency_code,
                            amount=posting.amount,
                        )
                        for posting in payload.postings
                    ]
                )
            schedule.updated_at = now
            await db.flush()
            return await _recurring_transaction_record(db, schedule)


async def pause_recurring_transaction(
    storage: DatabaseStorage, user_id: str, recurring_transaction_id: str
) -> RecurringTransactionRecord:
    now = _utc_now()
    async with storage.session() as db:
        async with db.begin():
            schedule = await _get_recurring_transaction(db, user_id, recurring_transaction_id)
            if schedule.state != MoneyRecurrenceState.ACTIVE.value:
                raise RecurringTransactionStateError()
            schedule.state = MoneyRecurrenceState.PAUSED.value
            schedule.paused_at = now
            schedule.updated_at = now
            await db.flush()
            return await _recurring_transaction_record(db, schedule)


async def resume_recurring_transaction(
    storage: DatabaseStorage, user_id: str, recurring_transaction_id: str
) -> RecurringTransactionRecord:
    now = _utc_now()
    async with storage.session() as db:
        async with db.begin():
            schedule = await _get_recurring_transaction(db, user_id, recurring_transaction_id)
            if schedule.state != MoneyRecurrenceState.PAUSED.value:
                raise RecurringTransactionStateError()
            resume_date = local_date(now, schedule.timezone)
            while (
                schedule.next_occurrence_date is not None
                and schedule.next_occurrence_date <= resume_date
            ):
                occurrence = await db.scalar(
                    select(MoneyRecurringOccurrence).where(
                        MoneyRecurringOccurrence.recurring_transaction_id == schedule.id,
                        MoneyRecurringOccurrence.due_date == schedule.next_occurrence_date,
                    )
                )
                if occurrence is None:
                    occurrence = await _create_recurring_occurrence(
                        db,
                        schedule,
                        schedule.next_occurrence_date,
                        schedule.next_occurrence_number or 1,
                    )
                if occurrence.status == RecurringOccurrenceState.SCHEDULED.value:
                    occurrence.status = RecurringOccurrenceState.SKIPPED.value
                _set_next_recurring_candidate(schedule, occurrence.due_date, now)
            if schedule.state == MoneyRecurrenceState.ENDED.value:
                schedule.updated_at = now
            else:
                schedule.state = MoneyRecurrenceState.ACTIVE.value
                schedule.paused_at = None
                schedule.updated_at = now
            await db.flush()
            return await _recurring_transaction_record(db, schedule)


async def end_recurring_transaction(
    storage: DatabaseStorage, user_id: str, recurring_transaction_id: str
) -> RecurringTransactionRecord:
    now = _utc_now()
    async with storage.session() as db:
        async with db.begin():
            schedule = await _get_recurring_transaction(db, user_id, recurring_transaction_id)
            if schedule.state == MoneyRecurrenceState.ENDED.value:
                raise RecurringTransactionStateError()
            scheduled = list(
                (
                    await db.execute(
                        select(MoneyRecurringOccurrence).where(
                            MoneyRecurringOccurrence.recurring_transaction_id == schedule.id,
                            MoneyRecurringOccurrence.status
                            == RecurringOccurrenceState.SCHEDULED.value,
                        )
                    )
                )
                .scalars()
                .all()
            )
            for occurrence in scheduled:
                occurrence.status = RecurringOccurrenceState.SKIPPED.value
            schedule.state = MoneyRecurrenceState.ENDED.value
            schedule.next_occurrence_date = None
            schedule.next_occurrence_number = None
            schedule.ended_at = now
            schedule.updated_at = now
            await db.flush()
            return await _recurring_transaction_record(db, schedule)


async def _process_one_recurring_occurrence(
    storage: DatabaseStorage,
    user_id: str,
    recurring_transaction_id: str,
    now: datetime,
) -> bool:
    async with storage.session() as db:
        async with db.begin():
            schedule = await _get_recurring_transaction(db, user_id, recurring_transaction_id)
            if (
                schedule.state != MoneyRecurrenceState.ACTIVE.value
                or schedule.next_occurrence_date is None
            ):
                return False
            due_date = schedule.next_occurrence_date
            occurrence = await db.scalar(
                select(MoneyRecurringOccurrence).where(
                    MoneyRecurringOccurrence.recurring_transaction_id == schedule.id,
                    MoneyRecurringOccurrence.due_date == due_date,
                )
            )
            if occurrence is None:
                occurrence = await _create_recurring_occurrence(
                    db, schedule, due_date, schedule.next_occurrence_number or 1
                )
            if occurrence.status != RecurringOccurrenceState.SCHEDULED.value:
                _set_next_recurring_candidate(schedule, due_date, now)
                await db.flush()
                return False
            postings = await _recurring_posting_requests(db, schedule.id)
            transaction_payload = TransactionCreateRequest(
                transaction_date=due_date,
                name=schedule.name,
                payee_id=schedule.payee_id,
                memo=schedule.memo,
                postings=postings,
            )
            transaction, _ = await _create_transaction_in_session(
                db,
                user_id,
                transaction_payload,
                now,
                require_split_labels=False,
            )
            occurrence.status = RecurringOccurrenceState.POSTED.value
            occurrence.transaction_id = transaction.id
            occurrence.processed_at = now
            _set_next_recurring_candidate(schedule, due_date, now)
            await _ensure_next_recurring_occurrence(db, schedule)
            schedule.updated_at = now
            await db.flush()
            return True


async def process_due_recurring_transactions(
    storage: DatabaseStorage,
    user_id: str | None = None,
    now: datetime | None = None,
) -> RecurringProcessResult:
    current = now or _utc_now()
    processed = 0
    failed = 0
    async with storage.session() as db:
        statement = select(MoneyRecurringTransaction).where(
            MoneyRecurringTransaction.state == MoneyRecurrenceState.ACTIVE.value,
            MoneyRecurringTransaction.next_occurrence_date.is_not(None),
        )
        if user_id is not None:
            statement = statement.where(MoneyRecurringTransaction.user_id == user_id)
        schedules = list((await db.execute(statement)).scalars().all())
        schedule_ids = [(schedule.user_id, schedule.id) for schedule in schedules]

    for schedule_user_id, schedule_id in schedule_ids:
        while True:
            async with storage.session() as db:
                schedule = await _get_recurring_transaction(db, schedule_user_id, schedule_id)
                if (
                    schedule.state != MoneyRecurrenceState.ACTIVE.value
                    or schedule.next_occurrence_date is None
                    or schedule.next_occurrence_date > local_date(current, schedule.timezone)
                ):
                    break
            try:
                if await _process_one_recurring_occurrence(
                    storage, schedule_user_id, schedule_id, current
                ):
                    processed += 1
            except Exception:
                failed += 1
                break
    return RecurringProcessResult(processed_count=processed, failed_count=failed)


async def get_transaction(
    storage: DatabaseStorage, user_id: str, transaction_id: str
) -> TransactionRecord:
    async with storage.session() as db:
        transaction = await _get_transaction(db, user_id, transaction_id)
        return _transaction_record(transaction, await _postings_for_transaction(db, transaction.id))


async def update_transaction(
    storage: DatabaseStorage,
    user_id: str,
    transaction_id: str,
    payload: TransactionUpdateRequest,
) -> TransactionRecord:
    now = _utc_now()
    async with storage.session() as db:
        async with db.begin():
            transaction = await _get_transaction(db, user_id, transaction_id)
            if transaction.state == "voided":
                raise TransactionVoidedError()
            current_postings = await _postings_for_transaction(db, transaction.id)
            if any(
                posting.reconciliation_state == ReconciliationState.RECONCILED.value
                for posting in current_postings
            ):
                raise TransactionLockedError()
            fields = payload.model_fields_set
            if "name" in fields and payload.name is not None:
                transaction.name = payload.name
            if "payee_id" in fields:
                await _validate_payee(db, user_id, payload.payee_id)
                transaction.payee_id = payload.payee_id
            if "transaction_date" in fields and payload.transaction_date is not None:
                transaction.transaction_date = payload.transaction_date
            if "memo" in fields:
                transaction.memo = payload.memo
            if "postings" in fields and payload.postings is not None:
                await _validate_postings(
                    db,
                    user_id,
                    payload.postings,
                    require_split_labels=True,
                )
                await db.execute(
                    delete(MoneyPosting).where(MoneyPosting.transaction_id == transaction.id)
                )
                db.add_all(
                    [
                        _posting_from_request(user_id, transaction.id, posting, position)
                        for position, posting in enumerate(payload.postings)
                    ]
                )
            if fields:
                transaction.updated_at = now
            await db.flush()
            return _transaction_record(
                transaction, await _postings_for_transaction(db, transaction.id)
            )


async def void_transaction(
    storage: DatabaseStorage, user_id: str, transaction_id: str
) -> TransactionRecord:
    now = _utc_now()
    async with storage.session() as db:
        async with db.begin():
            transaction = await _get_transaction(db, user_id, transaction_id)
            if transaction.state == TransactionState.VOIDED.value:
                raise TransactionVoidedError()
            postings = await _postings_for_transaction(db, transaction.id)
            if (
                transaction.reversal_of_id is not None
                or await _has_reversal(db, transaction.id)
                or any(
                    posting.account_id is not None
                    and posting.reconciliation_state == ReconciliationState.RECONCILED.value
                    for posting in postings
                )
            ):
                raise TransactionVoidNotAllowedError()
            transaction.state = TransactionState.VOIDED.value
            transaction.voided_at = now
            transaction.void_reason = TransactionVoidReason.MANUAL.value
            transaction.updated_at = now
            await db.flush()
            return _transaction_record(transaction, postings)


async def restore_transaction(
    storage: DatabaseStorage, user_id: str, transaction_id: str
) -> TransactionRecord:
    now = _utc_now()
    async with storage.session() as db:
        async with db.begin():
            transaction = await _get_transaction(db, user_id, transaction_id)
            if (
                transaction.state != TransactionState.VOIDED.value
                or transaction.void_reason != TransactionVoidReason.MANUAL.value
                or transaction.reversal_of_id is not None
                or await _has_reversal(db, transaction.id)
            ):
                raise TransactionRestoreNotAllowedError()
            transaction.state = TransactionState.POSTED.value
            transaction.voided_at = None
            transaction.void_reason = None
            transaction.updated_at = now
            await db.flush()
            return _transaction_record(
                transaction, await _postings_for_transaction(db, transaction.id)
            )


async def list_transactions(
    storage: DatabaseStorage,
    user_id: str,
    filters: TransactionListFilters,
) -> TransactionPage:
    _validate_limit(filters.limit)
    if filters.date_from and filters.date_to and filters.date_from > filters.date_to:
        raise InvalidMoneyQueryError()
    currency_code = normalize_currency(filters.currency_code) if filters.currency_code else None
    search = _normalize_transaction_search(filters.search)
    fingerprint = _filter_fingerprint(
        TransactionListFilters(
            date_from=filters.date_from,
            date_to=filters.date_to,
            search=search,
            account_id=filters.account_id,
            payee_id=filters.payee_id,
            category_id=filters.category_id,
            currency_code=currency_code,
            reconciliation_state=filters.reconciliation_state,
            include_voided=filters.include_voided,
            limit=filters.limit,
            cursor=None,
        )
    )
    async with storage.session() as db:
        statement = select(MoneyTransaction).where(MoneyTransaction.user_id == user_id)
        if not filters.include_voided:
            statement = statement.where(MoneyTransaction.state == "posted")
        if filters.date_from is not None:
            statement = statement.where(MoneyTransaction.transaction_date >= filters.date_from)
        if filters.date_to is not None:
            statement = statement.where(MoneyTransaction.transaction_date <= filters.date_to)
        if search is not None:
            search_pattern = f"%{search}%"
            payee_match = exists().where(
                MoneyPayee.id == MoneyTransaction.payee_id,
                MoneyPayee.user_id == user_id,
                func.lower(MoneyPayee.name).like(search_pattern),
            )
            category_match = exists().where(
                MoneyPosting.transaction_id == MoneyTransaction.id,
                MoneyPosting.category_id == MoneyCategory.id,
                MoneyCategory.user_id == user_id,
                func.lower(MoneyCategory.name).like(search_pattern),
            )
            account_match = exists().where(
                MoneyPosting.transaction_id == MoneyTransaction.id,
                MoneyPosting.account_id == MoneyAccount.id,
                MoneyAccount.user_id == user_id,
                func.lower(MoneyAccount.name).like(search_pattern),
            )
            statement = statement.where(
                or_(
                    func.lower(MoneyTransaction.name).like(search_pattern),
                    func.lower(MoneyTransaction.memo).like(search_pattern),
                    payee_match,
                    category_match,
                    account_match,
                )
            )
        if filters.payee_id is not None:
            statement = statement.where(MoneyTransaction.payee_id == filters.payee_id)
        posting_exists = exists().where(MoneyPosting.transaction_id == MoneyTransaction.id)
        if filters.account_id is not None:
            statement = statement.where(
                posting_exists.where(MoneyPosting.account_id == filters.account_id)
            )
        if filters.category_id is not None:
            statement = statement.where(
                posting_exists.where(MoneyPosting.category_id == filters.category_id)
            )
        if currency_code is not None:
            statement = statement.where(
                posting_exists.where(MoneyPosting.currency_code == currency_code)
            )
        if filters.reconciliation_state is not None:
            statement = statement.where(
                posting_exists.where(
                    MoneyPosting.account_id.is_not(None),
                    MoneyPosting.reconciliation_state == filters.reconciliation_state.value,
                )
            )
        if filters.cursor:
            payload = _decode_cursor(filters.cursor, fingerprint)
            try:
                cursor_date = date.fromisoformat(str(payload["transaction_date"]))
                cursor_id = payload["id"]
                if not isinstance(cursor_id, str) or not cursor_id:
                    raise ValueError
            except (KeyError, TypeError, ValueError):
                raise InvalidMoneyCursorError() from None
            statement = statement.where(
                (MoneyTransaction.transaction_date < cursor_date)
                | (
                    (MoneyTransaction.transaction_date == cursor_date)
                    & (MoneyTransaction.id < cursor_id)
                )
            )
        statement = statement.order_by(
            MoneyTransaction.transaction_date.desc(), MoneyTransaction.id.desc()
        ).limit(filters.limit + 1)
        transactions = list((await db.execute(statement)).scalars().all())
        next_cursor = None
        if len(transactions) > filters.limit:
            transactions.pop()
            last = transactions[-1]
            next_cursor = _encode_cursor(
                {
                    "v": 1,
                    "f": fingerprint,
                    "transaction_date": last.transaction_date.isoformat(),
                    "id": last.id,
                }
            )
        records = [
            _transaction_record(transaction, await _postings_for_transaction(db, transaction.id))
            for transaction in transactions
        ]
        return TransactionPage(records, next_cursor)


async def _get_posting_for_transaction(
    db: AsyncSession,
    user_id: str,
    transaction_id: str,
    posting_id: str,
) -> tuple[MoneyTransaction, MoneyPosting]:
    transaction = await _get_transaction(db, user_id, transaction_id)
    posting = await db.scalar(
        select(MoneyPosting)
        .where(
            MoneyPosting.id == posting_id,
            MoneyPosting.transaction_id == transaction_id,
            MoneyPosting.user_id == user_id,
        )
        .limit(1)
    )
    if posting is None:
        raise PostingNotFoundError()
    return transaction, posting


async def clear_posting(
    storage: DatabaseStorage,
    user_id: str,
    transaction_id: str,
    posting_id: str,
) -> TransactionRecord:
    now = _utc_now()
    async with storage.session() as db:
        async with db.begin():
            transaction, posting = await _get_posting_for_transaction(
                db, user_id, transaction_id, posting_id
            )
            if transaction.state == "voided":
                raise TransactionVoidedError()
            if posting.account_id is None:
                raise InvalidReconciliationTargetError()
            if posting.reconciliation_state != ReconciliationState.UNCLEARED.value:
                raise InvalidReconciliationTransitionError()
            posting.reconciliation_state = ReconciliationState.CLEARED.value
            posting.cleared_at = now
            transaction.updated_at = now
            await db.flush()
            return _transaction_record(
                transaction, await _postings_for_transaction(db, transaction.id)
            )


async def reconcile_posting(
    storage: DatabaseStorage,
    user_id: str,
    transaction_id: str,
    posting_id: str,
) -> TransactionRecord:
    now = _utc_now()
    async with storage.session() as db:
        async with db.begin():
            transaction, posting = await _get_posting_for_transaction(
                db, user_id, transaction_id, posting_id
            )
            if transaction.state == "voided":
                raise TransactionVoidedError()
            if posting.account_id is None:
                raise InvalidReconciliationTargetError()
            if posting.reconciliation_state != ReconciliationState.CLEARED.value:
                raise InvalidReconciliationTransitionError()
            posting.reconciliation_state = ReconciliationState.RECONCILED.value
            posting.reconciled_at = now
            transaction.updated_at = now
            await db.flush()
            return _transaction_record(
                transaction, await _postings_for_transaction(db, transaction.id)
            )


async def reverse_transaction(
    storage: DatabaseStorage,
    user_id: str,
    transaction_id: str,
    payload: TransactionReverseRequest | None = None,
) -> TransactionRecord:
    payload = payload or TransactionReverseRequest()
    now = _utc_now()
    async with storage.session() as db:
        async with db.begin():
            original = await _get_transaction(db, user_id, transaction_id)
            if original.state == "voided":
                raise TransactionVoidedError()
            original_postings = await _postings_for_transaction(db, original.id)
            if not any(
                posting.account_id is not None
                and posting.reconciliation_state == ReconciliationState.RECONCILED.value
                for posting in original_postings
            ):
                raise ReversalNotAllowedError()
            reversal = MoneyTransaction(
                id=str(uuid4()),
                user_id=user_id,
                transaction_date=payload.transaction_date or original.transaction_date,
                name=f"Reversal of {original.name}",
                payee_id=original.payee_id,
                memo=payload.memo or f"Reversal of {original.id}",
                state="posted",
                reversal_of_id=original.id,
                created_at=now,
                updated_at=now,
            )
            db.add(reversal)
            original.state = "voided"
            original.voided_at = now
            original.void_reason = TransactionVoidReason.REVERSAL.value
            original.updated_at = now
            await db.flush()
            reversal_postings = []
            for posting in original_postings:
                reversal_postings.append(
                    MoneyPosting(
                        id=str(uuid4()),
                        user_id=user_id,
                        transaction_id=reversal.id,
                        position=posting.position,
                        label=posting.label,
                        account_id=posting.account_id,
                        category_id=posting.category_id,
                        currency_code=posting.currency_code,
                        amount=_decimal_text(-_decimal(posting.amount), posting.currency_code),
                        reconciliation_state=ReconciliationState.UNCLEARED.value,
                    )
                )
            db.add_all(reversal_postings)
            await db.flush()
            return _transaction_record(reversal, reversal_postings)


async def _get_installment_plan(
    db: AsyncSession, user_id: str, plan_id: str
) -> MoneyInstallmentPlan:
    plan = await db.scalar(
        select(MoneyInstallmentPlan)
        .where(MoneyInstallmentPlan.id == plan_id, MoneyInstallmentPlan.user_id == user_id)
        .limit(1)
    )
    if plan is None:
        raise InstallmentPlanNotFoundError()
    return plan


def _installment_amounts(total: Decimal, term_months: int, currency_code: str) -> list[str]:
    if total <= 0:
        raise InvalidInstallmentPlanError()
    exponent = SUPPORTED_CURRENCY_EXPONENTS[normalize_currency(currency_code)]
    unit = Decimal(1).scaleb(-exponent)
    base = (total / term_months).quantize(unit, rounding=ROUND_DOWN)
    if base < unit:
        raise InvalidInstallmentPlanError()
    amounts = [base for _ in range(term_months - 1)]
    amounts.append(total - (base * (term_months - 1)))
    return [_decimal_text(amount, currency_code) for amount in amounts]


async def create_installment_plan(
    storage: DatabaseStorage,
    user_id: str,
    payload: InstallmentPlanCreateRequest,
) -> InstallmentPlanRecord:
    now = _utc_now()
    async with storage.session() as db:
        async with db.begin():
            account = await _get_account(db, user_id, payload.account_id, active_only=True)
            if account.account_type != AccountType.CREDIT_CARD.value:
                raise InvalidInstallmentPlanError()
            if (
                account.statement_close_day is None
                or account.payment_due_day is None
                or account.credit_limit is None
            ):
                raise InvalidCreditCardSettingsError()
            if account.currency_code != payload.currency_code:
                raise CurrencyMismatchError()
            category = await _get_category(db, user_id, payload.category_id, active_only=True)
            if category.kind != CategoryKind.EXPENSE.value:
                raise InvalidInstallmentPlanError()
            await _validate_payee(db, user_id, payload.payee_id)
            amounts = _installment_amounts(
                Decimal(payload.total_amount) + Decimal(payload.fee_amount),
                payload.term_months,
                payload.currency_code,
            )
            first_charge = _next_statement_close_date(
                account, payload.purchase_date, strictly_after=True
            )
            if first_charge is None:
                raise InvalidCreditCardSettingsError()
            plan = MoneyInstallmentPlan(
                id=str(uuid4()),
                user_id=user_id,
                account_id=account.id,
                payee_id=payload.payee_id,
                category_id=payload.category_id,
                currency_code=payload.currency_code,
                purchase_date=payload.purchase_date,
                name=payload.name,
                memo=payload.memo,
                total_amount=payload.total_amount,
                fee_amount=payload.fee_amount,
                term_months=payload.term_months,
                status=InstallmentPlanState.ACTIVE.value,
                created_at=now,
                updated_at=now,
            )
            db.add(plan)
            await db.flush()
            occurrences = [
                MoneyInstallmentOccurrence(
                    id=str(uuid4()),
                    user_id=user_id,
                    plan_id=plan.id,
                    sequence_number=index + 1,
                    charge_date=_month_date_offset(
                        first_charge, account.statement_close_day, index
                    ),
                    amount=amount,
                    status=InstallmentOccurrenceState.SCHEDULED.value,
                )
                for index, amount in enumerate(amounts)
            ]
            db.add_all(occurrences)
            await db.flush()
            return await _installment_plan_record(db, plan)


async def get_installment_plan(
    storage: DatabaseStorage, user_id: str, plan_id: str
) -> InstallmentPlanRecord:
    async with storage.session() as db:
        plan = await _get_installment_plan(db, user_id, plan_id)
        return await _installment_plan_record(db, plan)


async def list_installment_plans(
    storage: DatabaseStorage, user_id: str, filters: InstallmentPlanListFilters
) -> InstallmentPlanPage:
    _validate_limit(filters.limit)
    fingerprint = _filter_fingerprint(filters)
    async with storage.session() as db:
        statement = select(MoneyInstallmentPlan).where(MoneyInstallmentPlan.user_id == user_id)
        if filters.account_id is not None:
            statement = statement.where(MoneyInstallmentPlan.account_id == filters.account_id)
        if filters.status is not None:
            statement = statement.where(MoneyInstallmentPlan.status == filters.status.value)
        if filters.cursor:
            payload = _decode_cursor(filters.cursor, fingerprint)
            try:
                cursor_date = date.fromisoformat(str(payload["purchase_date"]))
                cursor_id = payload["id"]
                if not isinstance(cursor_id, str) or not cursor_id:
                    raise ValueError
            except (KeyError, TypeError, ValueError):
                raise InvalidMoneyCursorError() from None
            statement = statement.where(
                (MoneyInstallmentPlan.purchase_date < cursor_date)
                | (
                    (MoneyInstallmentPlan.purchase_date == cursor_date)
                    & (MoneyInstallmentPlan.id < cursor_id)
                )
            )
        statement = statement.order_by(
            MoneyInstallmentPlan.purchase_date.desc(), MoneyInstallmentPlan.id.desc()
        ).limit(filters.limit + 1)
        plans = list((await db.execute(statement)).scalars().all())
        next_cursor = None
        if len(plans) > filters.limit:
            plans.pop()
            last = plans[-1]
            next_cursor = _encode_cursor(
                {
                    "v": 1,
                    "f": fingerprint,
                    "purchase_date": last.purchase_date.isoformat(),
                    "id": last.id,
                }
            )
        return InstallmentPlanPage(
            [await _installment_plan_record(db, plan) for plan in plans], next_cursor
        )


async def cancel_installment_plan(
    storage: DatabaseStorage, user_id: str, plan_id: str
) -> InstallmentPlanRecord:
    now = _utc_now()
    async with storage.session() as db:
        async with db.begin():
            plan = await _get_installment_plan(db, user_id, plan_id)
            if plan.status == InstallmentPlanState.COMPLETED.value:
                raise InstallmentPlanLockedError()
            if plan.status != InstallmentPlanState.CANCELLED.value:
                occurrences = list(
                    (
                        await db.execute(
                            select(MoneyInstallmentOccurrence).where(
                                MoneyInstallmentOccurrence.plan_id == plan.id,
                                MoneyInstallmentOccurrence.status
                                == InstallmentOccurrenceState.SCHEDULED.value,
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                for occurrence in occurrences:
                    occurrence.status = InstallmentOccurrenceState.CANCELLED.value
                plan.status = InstallmentPlanState.CANCELLED.value
                plan.updated_at = now
                await db.flush()
            return await _installment_plan_record(db, plan)


async def process_due_installments(
    storage: DatabaseStorage,
    user_id: str | None = None,
    today: date | None = None,
) -> int:
    charge_date = today or datetime.now(UTC).date()
    now = _utc_now()
    processed = 0
    async with storage.session() as db:
        async with db.begin():
            statement = (
                select(MoneyInstallmentOccurrence)
                .join(
                    MoneyInstallmentPlan,
                    MoneyInstallmentPlan.id == MoneyInstallmentOccurrence.plan_id,
                )
                .where(
                    MoneyInstallmentOccurrence.status == InstallmentOccurrenceState.SCHEDULED.value,
                    MoneyInstallmentOccurrence.charge_date <= charge_date,
                )
                .order_by(
                    MoneyInstallmentOccurrence.charge_date.asc(),
                    MoneyInstallmentOccurrence.sequence_number.asc(),
                )
            )
            if user_id is not None:
                statement = statement.where(MoneyInstallmentOccurrence.user_id == user_id)
            occurrences = list((await db.execute(statement)).scalars().all())
            for occurrence in occurrences:
                plan = await db.scalar(
                    select(MoneyInstallmentPlan)
                    .where(MoneyInstallmentPlan.id == occurrence.plan_id)
                    .limit(1)
                )
                if plan is None or plan.status != InstallmentPlanState.ACTIVE.value:
                    occurrence.status = InstallmentOccurrenceState.CANCELLED.value
                    continue
                account = await db.scalar(
                    select(MoneyAccount).where(MoneyAccount.id == plan.account_id).limit(1)
                )
                if account is None:
                    raise AccountNotFoundError()
                transaction_id = str(uuid4())
                installment_label = (
                    f"Installment {occurrence.sequence_number} of {plan.term_months}"
                )
                transaction = MoneyTransaction(
                    id=transaction_id,
                    user_id=plan.user_id,
                    transaction_date=occurrence.charge_date,
                    name=f"{plan.name} · {installment_label}"[:200],
                    payee_id=plan.payee_id,
                    memo=(f"{plan.memo} · {installment_label}" if plan.memo else installment_label)[
                        :10_000
                    ],
                    state=TransactionState.POSTED.value,
                    created_at=now,
                    updated_at=now,
                )
                db.add(transaction)
                await db.flush()
                db.add_all(
                    [
                        MoneyPosting(
                            id=str(uuid4()),
                            user_id=plan.user_id,
                            transaction_id=transaction_id,
                            position=0,
                            label=None,
                            account_id=account.id,
                            category_id=None,
                            currency_code=plan.currency_code,
                            amount=_decimal_text(-_decimal(occurrence.amount), plan.currency_code),
                            reconciliation_state=ReconciliationState.UNCLEARED.value,
                        ),
                        MoneyPosting(
                            id=str(uuid4()),
                            user_id=plan.user_id,
                            transaction_id=transaction_id,
                            position=1,
                            label=None,
                            account_id=None,
                            category_id=plan.category_id,
                            currency_code=plan.currency_code,
                            amount=occurrence.amount,
                            reconciliation_state=ReconciliationState.UNCLEARED.value,
                        ),
                    ]
                )
                occurrence.status = InstallmentOccurrenceState.CHARGED.value
                occurrence.transaction_id = transaction_id
                occurrence.charged_at = now
                plan.updated_at = now
                processed += 1
                remaining = await db.scalar(
                    select(func.count(MoneyInstallmentOccurrence.id)).where(
                        MoneyInstallmentOccurrence.plan_id == plan.id,
                        MoneyInstallmentOccurrence.status
                        == InstallmentOccurrenceState.SCHEDULED.value,
                    )
                )
                if remaining == 0:
                    plan.status = InstallmentPlanState.COMPLETED.value
            await db.flush()
    return processed
