"""Stable, transport-independent authentication failures."""


class AuthError(Exception):
    """Expected authentication failure translated by the HTTP adapter."""

    def __init__(self, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class SetupNotConfiguredError(AuthError):
    def __init__(self) -> None:
        super().__init__(
            "setup_not_configured",
            "Owner setup is not configured.",
            503,
        )


class InvalidSetupSecretError(AuthError):
    def __init__(self) -> None:
        super().__init__("invalid_setup_secret", "The setup secret is invalid.", 403)


class AlreadyInitializedError(AuthError):
    def __init__(self) -> None:
        super().__init__(
            "auth_already_initialized",
            "Owner setup has already been completed.",
            409,
        )


class InvalidCredentialsError(AuthError):
    def __init__(self) -> None:
        super().__init__("invalid_credentials", "Invalid email or password.", 401)


class UnauthenticatedError(AuthError):
    def __init__(self) -> None:
        super().__init__("unauthenticated", "Authentication is required.", 401)


class CsrfValidationError(AuthError):
    def __init__(self) -> None:
        super().__init__("csrf_validation_failed", "The CSRF validation failed.", 403)


class InvalidCurrentPasswordError(AuthError):
    def __init__(self) -> None:
        super().__init__(
            "invalid_current_password",
            "The current password is incorrect.",
            400,
        )


class InvalidMcpApiKeyConfigurationError(AuthError):
    def __init__(self) -> None:
        super().__init__(
            "invalid_mcp_api_key_configuration",
            "The MCP access key configuration is invalid.",
            422,
        )
