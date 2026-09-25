"""Stable failures for cross-domain recovery operations."""


class RecoveryError(Exception):
    """Base error translated by REST and MCP adapters."""

    status_code = 400
    code = "recovery_error"
    message = "The recovery request could not be completed."

    def __str__(self) -> str:
        return self.message


class InvalidRecoveryCursorError(RecoveryError):
    code = "invalid_recovery_cursor"
    message = "The recovery list cursor is invalid or expired."


class InvalidRecoveryQueryError(RecoveryError):
    code = "invalid_recovery_query"
    message = "The recovery list query is invalid."


class RecoveryItemNotFoundError(RecoveryError):
    status_code = 404
    code = "recovery_item_not_found"
    message = "The recovery item was not found."
