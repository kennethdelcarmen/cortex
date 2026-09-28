"""Owner-scoped money use cases over the shared database storage seam."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import delete, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..storage import DatabaseStorage
from .errors import (
    AccountNotFoundError,
    BudgetNotFoundError,
    CategoryNotFoundError,
    CurrencyMismatchError,
    DuplicateMoneyNameError,
    InvalidMoneyCursorError,
    InvalidMoneyQueryError,
    InvalidPostingTargetError,
    InvalidReconciliationTransitionError,
    PayeeNotFoundError,
    PostingNotFoundError,
    ReversalNotAllowedError,
    TransactionLockedError,
    TransactionNotFoundError,
    TransactionTooSmallError,
    TransactionVoidedError,
    UnbalancedTransactionError,
)
from .models import (
    MoneyAccount,
    MoneyBudget,
    MoneyCategory,
    MoneyPayee,
    MoneyPosting,
    MoneyTransaction,
)
from .schemas import (
    AccountCreateRequest,
    AccountType,
    AccountUpdateRequest,
    BudgetUpsertRequest,
    CategoryCreateRequest,
    CategoryKind,
    CategoryUpdateRequest,
    PayeeCreateRequest,
    PayeeUpdateRequest,
    PostingRequest,
    ReconciliationState,
    TransactionCreateRequest,
    TransactionReverseRequest,
    TransactionUpdateRequest,
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


@dataclass(frozen=True)
class AccountListFilters:
    include_archived: bool = False
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


def _account_record(account: MoneyAccount, balance: Decimal) -> AccountRecord:
    return AccountRecord(
        id=account.id,
        name=account.name,
        account_type=AccountType(account.account_type),
        institution_name=account.institution_name,
        last_four=account.last_four,
        currency_code=account.currency_code,
        opening_balance=account.opening_balance,
        balance=_decimal_text(balance, account.currency_code),
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


async def _postings_for_transaction(db: AsyncSession, transaction_id: str) -> list[MoneyPosting]:
    result = await db.execute(
        select(MoneyPosting)
        .where(MoneyPosting.transaction_id == transaction_id)
        .order_by(MoneyPosting.id.asc())
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
            account = MoneyAccount(
                id=str(uuid4()),
                user_id=user_id,
                name=payload.name,
                account_type=payload.account_type.value,
                institution_name=payload.institution_name,
                last_four=payload.last_four,
                currency_code=normalize_currency(payload.currency_code),
                opening_balance=payload.opening_balance,
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
        if not filters.include_archived:
            statement = statement.where(MoneyAccount.archived_at.is_(None))
        if filters.search:
            search = normalize_name(filters.search)
            statement = statement.where(MoneyAccount.name.contains(search))
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
    postings: list[PostingRequest],
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


def _posting_from_request(
    user_id: str,
    transaction_id: str,
    request: PostingRequest,
) -> MoneyPosting:
    return MoneyPosting(
        id=str(uuid4()),
        user_id=user_id,
        transaction_id=transaction_id,
        account_id=request.account_id,
        category_id=request.category_id,
        currency_code=request.currency_code,
        amount=request.amount,
        reconciliation_state=ReconciliationState.UNCLEARED.value,
    )


async def _validate_payee(db: AsyncSession, user_id: str, payee_id: str | None) -> None:
    if payee_id is not None:
        await _get_payee(db, user_id, payee_id, active_only=True)


async def create_transaction(
    storage: DatabaseStorage,
    user_id: str,
    payload: TransactionCreateRequest,
) -> TransactionRecord:
    now = _utc_now()
    async with storage.session() as db:
        async with db.begin():
            await _validate_payee(db, user_id, payload.payee_id)
            await _validate_postings(db, user_id, payload.postings)
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
                _posting_from_request(user_id, transaction.id, posting)
                for posting in payload.postings
            ]
            db.add_all(postings)
            await db.flush()
            return _transaction_record(transaction, postings)


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
                await _validate_postings(db, user_id, payload.postings)
                await db.execute(
                    delete(MoneyPosting).where(MoneyPosting.transaction_id == transaction.id)
                )
                db.add_all(
                    [
                        _posting_from_request(user_id, transaction.id, posting)
                        for posting in payload.postings
                    ]
                )
            if fields:
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
                    MoneyPosting.reconciliation_state == filters.reconciliation_state.value
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
                posting.reconciliation_state == ReconciliationState.RECONCILED.value
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
            original.updated_at = now
            await db.flush()
            reversal_postings = []
            for posting in original_postings:
                reversal_postings.append(
                    MoneyPosting(
                        id=str(uuid4()),
                        user_id=user_id,
                        transaction_id=reversal.id,
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
