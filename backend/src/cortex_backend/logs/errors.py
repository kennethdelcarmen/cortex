"""Stable activity-log domain failures."""


class ActivityLogError(Exception):
    """Base error raised by activity-log services."""

    status_code = 400
    code = "activity_log_error"
    message = "The activity log request could not be completed."

    def __str__(self) -> str:
        return self.message


class InvalidActivityLogCursorError(ActivityLogError):
    """The activity-log cursor cannot be decoded or no longer matches its filters."""

    code = "invalid_activity_log_cursor"
    message = "The activity log cursor is invalid or expired."


class InvalidActivityLogQueryError(ActivityLogError):
    """The activity-log list query is outside the supported bounds."""

    code = "invalid_activity_log_query"
    message = "The activity log query is invalid."
