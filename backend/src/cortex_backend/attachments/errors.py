"""Stable attachment-domain failures."""


class AttachmentError(Exception):
    """A safe, protocol-neutral attachment validation failure."""

    status_code = 422
    code = "invalid_attachment"
    message = "One or more attachments are invalid or unavailable."

    def __str__(self) -> str:
        return self.message
