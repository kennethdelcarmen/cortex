"""Stable failures for the file storage domain."""


class FileError(Exception):
    """Base error translated by REST and MCP adapters."""

    status_code = 400
    code = "file_error"
    message = "The file request could not be completed."

    def __str__(self) -> str:
        return self.message


class FileNotFoundError(FileError):
    """The requested active or deleted file is not visible to the owner."""

    status_code = 404
    code = "file_not_found"
    message = "The file was not found."


class FileMustBeDeletedError(FileError):
    status_code = 409
    code = "file_must_be_deleted"
    message = "Only deleted files can be permanently deleted."


class InvalidFileCursorError(FileError):
    """The file listing cursor cannot be used for the requested filters."""

    code = "invalid_file_cursor"
    message = "The file list cursor is invalid or expired."


class InvalidFileQueryError(FileError):
    """The file listing query is outside the supported bounds."""

    code = "invalid_file_query"
    message = "The file list query is invalid."


class InvalidFileNameError(FileError):
    """The supplied display filename is unsafe or empty."""

    status_code = 422
    code = "invalid_file_name"
    message = "The file name must contain safe, non-empty content."


class FileTooLargeError(FileError):
    """The upload exceeded the configured per-file limit."""

    status_code = 413
    code = "file_too_large"
    message = "The file exceeds the maximum allowed size."


class FileStorageUnavailableError(FileError):
    """The configured local file store cannot complete the operation."""

    status_code = 503
    code = "file_storage_unavailable"
    message = "File storage is not available."


class FileContentMissingError(FileError):
    """Metadata exists but the corresponding bytes are unavailable."""

    status_code = 404
    code = "file_content_missing"
    message = "The file contents are unavailable."


class FileContextNotReadyError(FileError):
    """The requested derived preview is not available yet."""

    status_code = 409
    code = "file_context_not_ready"
    message = "File context is not ready yet."


class FilePreviewUnavailableError(FileError):
    """The file context exists but no visual preview artifact is available."""

    status_code = 409
    code = "file_preview_unavailable"
    message = "A PDF preview is not available for this Office file."
