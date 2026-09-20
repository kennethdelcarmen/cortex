"""Stable task-domain failures."""


class TaskError(Exception):
    """Base error translated by REST and MCP adapters."""

    status_code = 400
    code = "task_error"
    message = "The task request could not be completed."

    def __str__(self) -> str:
        return self.message


class TaskNotFoundError(TaskError):
    status_code = 404
    code = "task_not_found"
    message = "The task was not found."


class InvalidCursorError(TaskError):
    status_code = 400
    code = "invalid_task_cursor"
    message = "The task list cursor is invalid or expired."


class InvalidTaskQueryError(TaskError):
    status_code = 400
    code = "invalid_task_query"
    message = "The task list query is invalid."


class InvalidTaskReorderError(TaskError):
    code = "invalid_task_reorder"
    message = "The task cannot be placed before that task."


class InvalidTaskDatesError(TaskError):
    status_code = 422
    code = "invalid_task_dates"
    message = "The task start time must be before or equal to its due time."


class InvalidTaskDateTimezoneError(TaskError):
    status_code = 422
    code = "invalid_task_timezone"
    message = "Task dates must include a timezone."


class InvalidTaskTagError(TaskError):
    status_code = 422
    code = "invalid_task_tag"
    message = "Task tags must be non-empty and at most 64 characters."


class InvalidTaskSummaryTimezoneError(TaskError):
    status_code = 422
    code = "invalid_task_summary_timezone"
    message = "The task summary timezone is invalid."


class InvalidTaskRecurrenceError(TaskError):
    status_code = 422
    code = "invalid_task_recurrence"
    message = "The recurrence definition is invalid."


class InvalidTaskRecurrenceTimezoneError(TaskError):
    status_code = 422
    code = "invalid_task_recurrence_timezone"
    message = "The recurrence timezone is invalid."


class RecurrenceAnchorRequiredError(TaskError):
    status_code = 422
    code = "recurrence_anchor_required"
    message = "A recurring task requires a start time or due time."


class TaskSeriesNotFoundError(TaskError):
    status_code = 404
    code = "task_series_not_found"
    message = "The task series was not found."


class InvalidTaskSeriesStateError(TaskError):
    status_code = 409
    code = "invalid_task_series_state"
    message = "The task series cannot perform that operation in its current state."


class TaskOccurrenceRequiredError(TaskError):
    status_code = 422
    code = "task_occurrence_required"
    message = "This operation is only valid for a recurring task occurrence."
