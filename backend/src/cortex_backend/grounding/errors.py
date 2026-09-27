"""Stable failures for grounded question preparation."""


class GroundingError(Exception):
    """Base error translated by the MCP adapter."""

    code = "grounding_error"
    message = "The question could not be prepared."

    def __str__(self) -> str:
        return self.message


class InvalidQuestionError(GroundingError):
    """The question is empty or outside the supported retrieval bounds."""

    code = "invalid_question"
    message = "The question must contain valid searchable content."
