"""Stable memory-domain failures."""


class NoteError(Exception):
    """Base error translated by REST and MCP adapters."""

    status_code = 400
    code = "note_error"
    message = "The note request could not be completed."

    def __str__(self) -> str:
        return self.message


class NoteNotFoundError(NoteError):
    status_code = 404
    code = "note_not_found"
    message = "The note was not found."


class InvalidNoteCursorError(NoteError):
    status_code = 400
    code = "invalid_note_cursor"
    message = "The note list cursor is invalid or expired."


class InvalidNoteQueryError(NoteError):
    status_code = 400
    code = "invalid_note_query"
    message = "The note list query is invalid."


class InvalidNoteTagError(NoteError):
    status_code = 422
    code = "invalid_note_tag"
    message = "Note tags must be non-empty and at most 64 characters."
