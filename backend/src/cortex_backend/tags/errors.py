"""Stable shared tag-domain failures."""


class TagError(Exception):
    """Base error translated by REST and MCP adapters."""

    status_code = 400
    code = "tag_error"
    message = "The tag request could not be completed."

    def __str__(self) -> str:
        return self.message


class TagNotFoundError(TagError):
    status_code = 404
    code = "tag_not_found"
    message = "The tag was not found."


class TagNameConflictError(TagError):
    status_code = 409
    code = "tag_name_conflict"
    message = "A tag with that name already exists."


class TagInactiveError(TagError):
    status_code = 409
    code = "tag_inactive"
    message = "That tag is inactive. Restore it before using it on a new record."


class TagMustBeArchivedError(TagError):
    status_code = 409
    code = "tag_must_be_archived"
    message = "Only archived tags can be permanently deleted."


class InvalidTagNameError(TagError):
    status_code = 422
    code = "invalid_tag_name"
    message = "Tag names must be non-empty and at most 64 characters."


class InvalidTagColorError(TagError):
    status_code = 422
    code = "invalid_tag_color"
    message = "That tag color is not supported."


class UnknownTagError(TagError):
    status_code = 422
    code = "unknown_tag"

    def __init__(self, unknown_tags: list[str], allowed_tags: list[str]) -> None:
        self.unknown_tags = unknown_tags
        self.allowed_tags = allowed_tags
        self.message = "Some tags are not in the active tag catalog."
        super().__init__(self.message)
