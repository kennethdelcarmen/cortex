"""Typed protocol contracts for the money domain."""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator, model_validator

from .errors import InvalidCurrencyError, InvalidMoneyAmountError

SUPPORTED_CURRENCY_EXPONENTS: dict[str, int] = {
    "USD": 2,
    "EUR": 2,
    "GBP": 2,
    "CHF": 2,
    "CAD": 2,
    "AUD": 2,
    "SGD": 2,
    "HKD": 2,
    "CNY": 2,
    "INR": 2,
    "PHP": 2,
    "JPY": 0,
    "KRW": 0,
}

_DECIMAL_PATTERN = re.compile(r"^-?(?:0|[1-9]\d*)(?:\.\d+)?$")
_PERIOD_PATTERN = re.compile(r"^\d{4}-(?:0[1-9]|1[0-2])$")


class AccountType(StrEnum):
    CHECKING = "checking"
    SAVINGS = "savings"
    CASH = "cash"
    CREDIT_CARD = "credit_card"
    LOAN = "loan"
    INVESTMENT = "investment"
    OTHER = "other"


class CategoryKind(StrEnum):
    INCOME = "income"
    EXPENSE = "expense"


class TransactionState(StrEnum):
    POSTED = "posted"
    VOIDED = "voided"


class TransactionVoidReason(StrEnum):
    MANUAL = "manual"
    REVERSAL = "reversal"


class ReconciliationState(StrEnum):
    UNCLEARED = "uncleared"
    CLEARED = "cleared"
    RECONCILED = "reconciled"


class InstallmentPlanState(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class InstallmentOccurrenceState(StrEnum):
    SCHEDULED = "scheduled"
    CHARGED = "charged"
    CANCELLED = "cancelled"


class MoneyRecurrenceFrequency(StrEnum):
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"


class MoneyRecurrenceState(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    ENDED = "ended"


class MoneyRecurrenceWeekday(StrEnum):
    MONDAY = "monday"
    TUESDAY = "tuesday"
    WEDNESDAY = "wednesday"
    THURSDAY = "thursday"
    FRIDAY = "friday"
    SATURDAY = "saturday"
    SUNDAY = "sunday"


class RecurringOccurrenceState(StrEnum):
    SCHEDULED = "scheduled"
    POSTED = "posted"
    SKIPPED = "skipped"


def normalize_name(value: str) -> str:
    normalized = " ".join(value.strip().split()).casefold()
    if not normalized:
        raise ValueError("name must contain content")
    return normalized


def normalize_display_name(value: str) -> str:
    normalized = " ".join(value.strip().split())
    if not normalized:
        raise ValueError("name must contain content")
    return normalized


def normalize_transaction_name(value: str) -> str:
    normalized = " ".join(value.strip().split())
    if not normalized:
        raise ValueError("transaction name must contain content")
    return normalized


def normalize_currency(value: str) -> str:
    normalized = value.strip().upper()
    if normalized not in SUPPORTED_CURRENCY_EXPONENTS:
        raise InvalidCurrencyError()
    return normalized


def canonical_amount(value: str, currency_code: str, *, allow_zero: bool = True) -> str:
    if not isinstance(value, str) or not _DECIMAL_PATTERN.fullmatch(value.strip()):
        raise InvalidMoneyAmountError()
    normalized_currency = normalize_currency(currency_code)
    raw = value.strip()
    try:
        amount = Decimal(raw)
    except InvalidOperation:
        raise InvalidMoneyAmountError() from None
    if not amount.is_finite() or (not allow_zero and amount == 0):
        raise InvalidMoneyAmountError()
    exponent = SUPPORTED_CURRENCY_EXPONENTS[normalized_currency]
    exponent_value = amount.as_tuple().exponent
    if isinstance(exponent_value, str):
        raise InvalidMoneyAmountError()
    fractional_digits = max(0, -exponent_value)
    if fractional_digits > exponent:
        raise InvalidMoneyAmountError()
    if len(amount.as_tuple().digits) > 38:
        raise InvalidMoneyAmountError()
    if amount == 0:
        return "0" if exponent == 0 else f"0.{('0' * exponent)}"
    return format(amount, "f")


def validate_period(value: str) -> str:
    normalized = value.strip()
    if not _PERIOD_PATTERN.fullmatch(normalized):
        from .errors import InvalidBudgetPeriodError

        raise InvalidBudgetPeriodError()
    return normalized


class AccountCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    account_type: AccountType
    institution_name: str | None = Field(default=None, max_length=200)
    last_four: str | None = Field(default=None, pattern=r"^\d{4}$")
    currency_code: str = Field(min_length=3, max_length=3)
    opening_balance: str = "0"
    credit_limit: str | None = None
    statement_close_day: int | None = Field(default=None, ge=1, le=31)
    payment_due_day: int | None = Field(default=None, ge=1, le=31)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return normalize_display_name(value)

    @field_validator("institution_name")
    @classmethod
    def validate_institution_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.strip().split())
        return normalized or None

    @field_validator("currency_code")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        try:
            return normalize_currency(value)
        except InvalidCurrencyError as exc:
            raise ValueError(exc.message) from exc

    @model_validator(mode="after")
    def validate_balance(self) -> AccountCreateRequest:
        try:
            self.opening_balance = canonical_amount(self.opening_balance, self.currency_code)
            if self.account_type == AccountType.CREDIT_CARD:
                if self.credit_limit is None:
                    raise ValueError("credit limit is required for credit cards")
                self.credit_limit = canonical_amount(
                    self.credit_limit, self.currency_code, allow_zero=False
                )
                if self.statement_close_day is None or self.payment_due_day is None:
                    raise ValueError("statement and payment days are required for credit cards")
            elif any(
                value is not None
                for value in (self.credit_limit, self.statement_close_day, self.payment_due_day)
            ):
                raise ValueError("credit-card settings are only valid for credit-card accounts")
        except (InvalidCurrencyError, InvalidMoneyAmountError) as exc:
            raise ValueError(exc.message) from exc
        return self


class AccountUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    institution_name: str | None = Field(default=None, max_length=200)
    last_four: str | None = Field(default=None, pattern=r"^\d{4}$")
    credit_limit: str | None = None
    statement_close_day: int | None = Field(default=None, ge=1, le=31)
    payment_due_day: int | None = Field(default=None, ge=1, le=31)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        return normalize_display_name(value) if value is not None else None

    @field_validator("institution_name")
    @classmethod
    def validate_institution_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.strip().split())
        return normalized or None


class PayeeCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return normalize_name(value)


class PayeeUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        return normalize_name(value) if value is not None else None


class CategoryCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    kind: CategoryKind

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return normalize_name(value)


class CategoryUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        return normalize_name(value) if value is not None else None


class BudgetUpsertRequest(BaseModel):
    amount: str


class PostingRequest(BaseModel):
    account_id: str | None = None
    category_id: str | None = None
    currency_code: str = Field(min_length=3, max_length=3)
    amount: str

    @field_validator("currency_code")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        try:
            return normalize_currency(value)
        except InvalidCurrencyError as exc:
            raise ValueError(exc.message) from exc

    @model_validator(mode="after")
    def validate_target(self) -> PostingRequest:
        if (self.account_id is None) == (self.category_id is None):
            from .errors import InvalidPostingTargetError

            raise InvalidPostingTargetError()
        try:
            self.amount = canonical_amount(self.amount, self.currency_code, allow_zero=False)
        except (InvalidCurrencyError, InvalidMoneyAmountError) as exc:
            raise ValueError(exc.message) from exc
        return self


class TransactionPostingRequest(PostingRequest):
    label: str | None = Field(default=None, max_length=200)

    @field_validator("label")
    @classmethod
    def validate_label(cls, value: str | None) -> str | None:
        return normalize_display_name(value) if value is not None else None


class TransactionCreateRequest(BaseModel):
    transaction_date: date
    name: str = Field(min_length=1, max_length=200)
    payee_id: str | None = None
    memo: str | None = Field(default=None, max_length=10_000)
    postings: list[TransactionPostingRequest] = Field(min_length=2, max_length=100)

    @field_validator("memo")
    @classmethod
    def validate_memo(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return normalize_transaction_name(value)


class TransactionUpdateRequest(BaseModel):
    transaction_date: date | None = None
    name: str | None = Field(default=None, min_length=1, max_length=200)
    payee_id: str | None = None
    memo: str | None = Field(default=None, max_length=10_000)
    postings: list[TransactionPostingRequest] | None = Field(
        default=None, min_length=2, max_length=100
    )

    @field_validator("memo")
    @classmethod
    def validate_memo(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        return normalize_transaction_name(value) if value is not None else None


class TransactionReverseRequest(BaseModel):
    transaction_date: date | None = None
    memo: str | None = Field(default=None, max_length=10_000)

    @field_validator("memo")
    @classmethod
    def validate_memo(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class MoneyRecurrenceRequest(BaseModel):
    timezone: str = Field(min_length=1, max_length=64)
    frequency: MoneyRecurrenceFrequency
    interval: int = Field(default=1, ge=1, le=365)
    weekdays: list[MoneyRecurrenceWeekday] = Field(default_factory=list, max_length=7)
    month_day: int | None = Field(default=None, ge=1, le=31)
    month: int | None = Field(default=None, ge=1, le=12)
    day: int | None = Field(default=None, ge=1, le=31)
    until_date: date | None = None
    occurrence_count: int | None = Field(default=None, ge=1, le=100_000)

    @field_validator("timezone")
    @classmethod
    def validate_timezone_name(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def validate_selectors(self) -> MoneyRecurrenceRequest:
        if len(set(self.weekdays)) != len(self.weekdays):
            raise ValueError("weekly recurrence weekdays must be unique")
        if self.frequency == MoneyRecurrenceFrequency.WEEKLY and not self.weekdays:
            raise ValueError("weekly recurrence requires at least one weekday")
        if self.frequency != MoneyRecurrenceFrequency.WEEKLY and self.weekdays:
            raise ValueError("weekdays are only valid for weekly recurrence")
        if self.frequency != MoneyRecurrenceFrequency.MONTHLY and self.month_day is not None:
            raise ValueError("month_day is only valid for monthly recurrence")
        if self.frequency != MoneyRecurrenceFrequency.YEARLY and (
            self.month is not None or self.day is not None
        ):
            raise ValueError("month and day are only valid for yearly recurrence")
        if (self.month is None) != (self.day is None):
            raise ValueError("yearly recurrence requires both month and day")
        if self.until_date is not None and self.occurrence_count is not None:
            raise ValueError("until_date and occurrence_count cannot both be set")
        return self


class InstallmentPlanCreateRequest(BaseModel):
    account_id: str
    currency_code: str = Field(min_length=3, max_length=3)
    purchase_date: date
    name: str = Field(min_length=1, max_length=200)
    payee_id: str | None = None
    category_id: str
    memo: str | None = Field(default=None, max_length=10_000)
    total_amount: str
    fee_amount: str = "0"
    term_months: int = Field(ge=1, le=120)

    @field_validator("currency_code")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        try:
            return normalize_currency(value)
        except InvalidCurrencyError as exc:
            raise ValueError(exc.message) from exc

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return normalize_transaction_name(value)

    @field_validator("memo")
    @classmethod
    def validate_memo(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def validate_amounts(self) -> InstallmentPlanCreateRequest:
        try:
            self.total_amount = canonical_amount(
                self.total_amount, self.currency_code, allow_zero=False
            )
            self.fee_amount = canonical_amount(self.fee_amount, self.currency_code)
            if Decimal(self.total_amount) <= 0:
                raise ValueError("total amount must be positive")
            if Decimal(self.fee_amount) < 0:
                raise ValueError("fee amount cannot be negative")
        except (InvalidCurrencyError, InvalidMoneyAmountError) as exc:
            raise ValueError(exc.message) from exc
        return self


class RecurringTransactionCreateRequest(BaseModel):
    start_date: date
    name: str = Field(min_length=1, max_length=200)
    payee_id: str | None = None
    memo: str | None = Field(default=None, max_length=10_000)
    recurrence: MoneyRecurrenceRequest
    postings: list[PostingRequest] = Field(min_length=2, max_length=100)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return normalize_transaction_name(value)

    @field_validator("memo")
    @classmethod
    def validate_memo(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class RecurringTransactionUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    payee_id: str | None = None
    memo: str | None = Field(default=None, max_length=10_000)
    recurrence: MoneyRecurrenceRequest | None = None
    postings: list[PostingRequest] | None = Field(default=None, min_length=2, max_length=100)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        return normalize_transaction_name(value) if value is not None else None

    @field_validator("memo")
    @classmethod
    def validate_memo(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class AccountResponse(BaseModel):
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


class PayeeResponse(BaseModel):
    id: str
    name: str
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


class CategoryResponse(BaseModel):
    id: str
    name: str
    kind: CategoryKind
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


class BudgetResponse(BaseModel):
    id: str
    category_id: str
    period: str
    currency_code: str
    amount: str
    spent_amount: str
    created_at: datetime
    updated_at: datetime


class MoneySummaryResponse(BaseModel):
    period: str
    currency_code: str
    total_balance: str
    income_amount: str
    spending_amount: str
    budget_amount: str
    budget_spent_amount: str
    budget_remaining_amount: str


class PostingResponse(BaseModel):
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


class TransactionResponse(BaseModel):
    id: str
    transaction_date: date
    name: str
    payee_id: str | None
    memo: str | None
    state: TransactionState
    reversal_of_id: str | None
    postings: list[PostingResponse]
    created_at: datetime
    updated_at: datetime
    voided_at: datetime | None
    void_reason: TransactionVoidReason | None


class AccountListResponse(BaseModel):
    items: list[AccountResponse]
    next_cursor: str | None


class PayeeListResponse(BaseModel):
    items: list[PayeeResponse]
    next_cursor: str | None


class CategoryListResponse(BaseModel):
    items: list[CategoryResponse]
    next_cursor: str | None


class BudgetListResponse(BaseModel):
    items: list[BudgetResponse]
    next_cursor: str | None


class TransactionListResponse(BaseModel):
    items: list[TransactionResponse]
    next_cursor: str | None


class InstallmentOccurrenceResponse(BaseModel):
    id: str
    sequence_number: int
    charge_date: date
    amount: str
    status: InstallmentOccurrenceState
    transaction_id: str | None
    charged_at: datetime | None


class InstallmentPlanResponse(BaseModel):
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
    occurrences: list[InstallmentOccurrenceResponse]
    created_at: datetime
    updated_at: datetime


class InstallmentPlanListResponse(BaseModel):
    items: list[InstallmentPlanResponse]
    next_cursor: str | None


class InstallmentProcessResponse(BaseModel):
    processed_count: int


class RecurringPostingResponse(BaseModel):
    id: str
    account_id: str | None
    category_id: str | None
    currency_code: str
    amount: str


class RecurringOccurrenceResponse(BaseModel):
    id: str
    sequence_number: int
    due_date: date
    status: RecurringOccurrenceState
    transaction_id: str | None
    processed_at: datetime | None


class RecurringTransactionResponse(BaseModel):
    id: str
    start_date: date
    name: str
    payee_id: str | None
    memo: str | None
    recurrence: MoneyRecurrenceRequest
    state: MoneyRecurrenceState
    next_occurrence_date: date | None
    next_occurrence_number: int | None
    posted_count: int
    postings: list[RecurringPostingResponse]
    occurrences: list[RecurringOccurrenceResponse]
    created_at: datetime
    updated_at: datetime
    paused_at: datetime | None
    ended_at: datetime | None


class RecurringTransactionListResponse(BaseModel):
    items: list[RecurringTransactionResponse]
    next_cursor: str | None


class RecurringProcessResponse(BaseModel):
    processed_count: int
    failed_count: int
