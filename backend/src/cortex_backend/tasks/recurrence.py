"""Calendar recurrence validation and occurrence generation."""

from __future__ import annotations

import calendar
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .errors import InvalidTaskRecurrenceTimezoneError
from .schemas import (
    RecurrenceFrequency,
    RecurrenceWeekday,
    TaskRecurrenceRequest,
)

HORIZON_DAYS = 90
MAX_OCCURRENCES_PER_MATERIALIZATION = 500

_WEEKDAY_NUMBERS = {
    RecurrenceWeekday.MONDAY: 0,
    RecurrenceWeekday.TUESDAY: 1,
    RecurrenceWeekday.WEDNESDAY: 2,
    RecurrenceWeekday.THURSDAY: 3,
    RecurrenceWeekday.FRIDAY: 4,
    RecurrenceWeekday.SATURDAY: 5,
    RecurrenceWeekday.SUNDAY: 6,
}


@dataclass(frozen=True)
class ScheduledOccurrence:
    """One generated wall-clock occurrence and its UTC representation."""

    local_at: datetime
    utc_at: datetime
    key: str


def timezone_or_error(timezone_name: str) -> ZoneInfo:
    """Resolve a user-provided IANA timezone or raise a stable domain error."""

    try:
        return ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        raise InvalidTaskRecurrenceTimezoneError() from None


def split_recurrence(payload: TaskRecurrenceRequest) -> tuple[str, dict[str, object]]:
    """Return the timezone and JSON-safe rule payload stored in the series."""

    values = payload.model_dump(mode="json")
    timezone_name = str(values.pop("timezone"))
    return timezone_name, values


def recurrence_request(timezone_name: str, rule: dict[str, object]) -> TaskRecurrenceRequest:
    """Rebuild a validated protocol recurrence from persisted values."""

    return TaskRecurrenceRequest.model_validate({"timezone": timezone_name, **rule})


def _localize(local_at: datetime, timezone: ZoneInfo) -> datetime:
    """Resolve a local wall-clock time, moving nonexistent DST times forward."""

    candidate = local_at.replace(tzinfo=timezone, fold=0)
    round_trip = candidate.astimezone(UTC).astimezone(timezone).replace(tzinfo=None)
    if round_trip != local_at:
        candidate = (local_at + (round_trip - local_at)).replace(tzinfo=timezone, fold=0)
    return candidate


def _month_date(year: int, month: int, requested_day: int) -> date:
    return date(year, month, min(requested_day, calendar.monthrange(year, month)[1]))


def _add_months(year: int, month: int, amount: int) -> tuple[int, int]:
    zero_based = year * 12 + month - 1 + amount
    return zero_based // 12, zero_based % 12 + 1


def _candidate_locals(
    anchor_local: datetime,
    frequency: RecurrenceFrequency,
    interval: int,
    weekdays: tuple[int, ...],
    month_day: int,
    year_month: int,
    year_day: int,
) -> Iterator[datetime]:
    """Yield local candidates in chronological order from the series anchor."""

    anchor_date = anchor_local.date()
    local_time = anchor_local.time().replace(tzinfo=None)

    if frequency == RecurrenceFrequency.DAILY:
        offset = 0
        while True:
            yield datetime.combine(anchor_date + timedelta(days=offset), local_time)
            offset += interval

    if frequency == RecurrenceFrequency.WEEKLY:
        week_start = anchor_date - timedelta(days=anchor_date.weekday())
        week_offset = 0
        while True:
            current_week = week_start + timedelta(weeks=week_offset)
            for weekday in weekdays:
                candidate_date = current_week + timedelta(days=weekday)
                if candidate_date >= anchor_date:
                    yield datetime.combine(candidate_date, local_time)
            week_offset += interval

    if frequency == RecurrenceFrequency.MONTHLY:
        month_offset = 0
        while True:
            year, month = _add_months(anchor_date.year, anchor_date.month, month_offset)
            yield datetime.combine(_month_date(year, month, month_day), local_time)
            month_offset += interval

    if frequency == RecurrenceFrequency.YEARLY:
        year_offset = 0
        while True:
            year = anchor_date.year + year_offset
            yield datetime.combine(_month_date(year, year_month, year_day), local_time)
            year_offset += interval


def iter_occurrences(
    anchor_at: datetime,
    timezone_name: str,
    rule: dict[str, object],
    *,
    after_at: datetime | None = None,
    through_at: datetime | None = None,
    limit: int | None = None,
) -> Iterator[ScheduledOccurrence]:
    """Yield bounded occurrences after a cursor and through a UTC horizon."""

    request = recurrence_request(timezone_name, rule)
    timezone = timezone_or_error(timezone_name)
    anchor_utc = anchor_at.astimezone(UTC)
    anchor_local = anchor_utc.astimezone(timezone).replace(tzinfo=None)
    weekdays = tuple(sorted(_WEEKDAY_NUMBERS[weekday] for weekday in request.weekdays))
    month_day = request.month_day or anchor_local.day
    year_month = request.month or anchor_local.month
    year_day = request.day or anchor_local.day
    occurrence_number = 0
    yielded = 0

    for local_at in _candidate_locals(
        anchor_local,
        request.frequency,
        request.interval,
        weekdays,
        month_day,
        year_month,
        year_day,
    ):
        if request.until_date is not None and local_at.date() > request.until_date:
            return
        if request.occurrence_count is not None and occurrence_number >= request.occurrence_count:
            return
        occurrence_number += 1

        aware_local = _localize(local_at, timezone)
        utc_at = aware_local.astimezone(UTC)
        if utc_at < anchor_utc:
            continue
        if after_at is not None and utc_at <= after_at.astimezone(UTC):
            continue
        if through_at is not None and utc_at > through_at.astimezone(UTC):
            return
        yield ScheduledOccurrence(
            local_at=aware_local,
            utc_at=utc_at,
            key=aware_local.isoformat(timespec="seconds"),
        )
        yielded += 1
        if limit is not None and yielded >= limit:
            return
