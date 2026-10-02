"""Stable money-domain failures."""


class MoneyError(Exception):
    """Base error translated by REST and MCP adapters."""

    status_code = 400
    code = "money_error"
    message = "The money request could not be completed."

    def __str__(self) -> str:
        return self.message


class MoneyNotFoundError(MoneyError):
    status_code = 404
    code = "money_resource_not_found"
    message = "The money resource was not found."


class AccountNotFoundError(MoneyNotFoundError):
    code = "money_account_not_found"
    message = "The account was not found."


class PayeeNotFoundError(MoneyNotFoundError):
    code = "money_payee_not_found"
    message = "The payee was not found."


class CategoryNotFoundError(MoneyNotFoundError):
    code = "money_category_not_found"
    message = "The category was not found."


class BudgetNotFoundError(MoneyNotFoundError):
    code = "money_budget_not_found"
    message = "The budget was not found."


class TransactionNotFoundError(MoneyNotFoundError):
    code = "money_transaction_not_found"
    message = "The transaction was not found."


class PostingNotFoundError(MoneyNotFoundError):
    code = "money_posting_not_found"
    message = "The transaction posting was not found."


class DuplicateMoneyNameError(MoneyError):
    status_code = 409
    code = "money_duplicate_name"
    message = "A resource with that name already exists."


class InvalidMoneyQueryError(MoneyError):
    code = "money_invalid_query"
    message = "The money list query is invalid."


class InvalidMoneyCursorError(MoneyError):
    code = "money_invalid_cursor"
    message = "The money list cursor is invalid or expired."


class InvalidCurrencyError(MoneyError):
    status_code = 422
    code = "money_invalid_currency"
    message = "The currency is unsupported or invalid."


class InvalidMoneyAmountError(MoneyError):
    status_code = 422
    code = "money_invalid_amount"
    message = "The amount is invalid for its currency."


class InvalidBudgetPeriodError(MoneyError):
    status_code = 422
    code = "money_invalid_period"
    message = "The budget period must use YYYY-MM format."


class InvalidPostingTargetError(MoneyError):
    status_code = 422
    code = "money_invalid_posting_target"
    message = "A posting must target exactly one account or category."


class CurrencyMismatchError(MoneyError):
    status_code = 422
    code = "money_currency_mismatch"
    message = "The posting currency does not match its account."


class UnbalancedTransactionError(MoneyError):
    status_code = 422
    code = "money_unbalanced_transaction"
    message = "Transaction postings must balance to zero per currency."


class InvalidSplitTransactionError(MoneyError):
    status_code = 422
    code = "money_invalid_split_transaction"
    message = (
        "A split transaction must contain one account posting and at least two labelled "
        "category postings in one currency and direction."
    )


class TransactionTooSmallError(MoneyError):
    status_code = 422
    code = "money_transaction_requires_postings"
    message = "A transaction must contain at least two non-zero postings."


class TransactionLockedError(MoneyError):
    status_code = 409
    code = "money_transaction_locked"
    message = "The transaction cannot be edited after reconciliation."


class TransactionVoidedError(MoneyError):
    status_code = 409
    code = "money_transaction_voided"
    message = "The transaction has already been voided."


class TransactionVoidNotAllowedError(MoneyError):
    status_code = 409
    code = "money_transaction_void_not_allowed"
    message = "Only standalone transactions without reconciled account postings can be voided."


class TransactionRestoreNotAllowedError(MoneyError):
    status_code = 409
    code = "money_transaction_restore_not_allowed"
    message = "Only manually voided standalone transactions can be restored."


class InvalidReconciliationTransitionError(MoneyError):
    status_code = 409
    code = "money_invalid_reconciliation_transition"
    message = "The posting cannot perform that reconciliation transition."


class InvalidReconciliationTargetError(MoneyError):
    status_code = 409
    code = "money_invalid_reconciliation_target"
    message = "Only account postings can be cleared or reconciled."


class InvalidArchiveStateError(MoneyError):
    status_code = 409
    code = "money_invalid_archive_state"
    message = "The resource cannot perform that archive operation."


class ReversalNotAllowedError(MoneyError):
    status_code = 409
    code = "money_reversal_not_allowed"
    message = "Only a reconciled transaction can be reversed."


class InvalidCreditCardSettingsError(MoneyError):
    status_code = 422
    code = "money_invalid_credit_card_settings"
    message = "Credit-card limit and statement dates are required and must be valid."


class InstallmentPlanNotFoundError(MoneyNotFoundError):
    code = "money_installment_plan_not_found"
    message = "The installment plan was not found."


class InstallmentOccurrenceNotFoundError(MoneyNotFoundError):
    code = "money_installment_occurrence_not_found"
    message = "The installment occurrence was not found."


class InvalidInstallmentPlanError(MoneyError):
    status_code = 422
    code = "money_invalid_installment_plan"
    message = "The installment plan is invalid for the selected account or category."


class InstallmentPlanLockedError(MoneyError):
    status_code = 409
    code = "money_installment_plan_locked"
    message = "The installment plan cannot be changed after a charge has posted."


class RecurringTransactionNotFoundError(MoneyNotFoundError):
    code = "money_recurring_transaction_not_found"
    message = "The recurring transaction was not found."


class InvalidRecurringTransactionError(MoneyError):
    status_code = 422
    code = "money_invalid_recurring_transaction"
    message = "The recurring transaction is invalid for the selected accounts, categories, or rule."


class RecurringTransactionStateError(MoneyError):
    status_code = 409
    code = "money_recurring_transaction_state"
    message = "The recurring transaction cannot perform that lifecycle operation."
