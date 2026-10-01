"""Small calendar recurrence primitives shared by domain schedulers."""

from __future__ import annotations

import calendar
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@dataclass(frozen=True)
class CalendarOccurrence:
    """One calendar occurrence and its one-based position in the rule."""

    occurrence_date: date
    sequence_number: int


def timezone_or_error(timezone_name: str) -> ZoneInfo:
    """Resolve an IANA timezone name."""

    try:
        return ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError("invalid recurrence timezone") from None


def local_date(now: datetime, timezone_name: str) -> date:
    """Return the calendar date at ``now`` in an IANA timezone."""

    aware_now = now if now.tzinfo is not None else now.replace(tzinfo=UTC)
    return aware_now.astimezone(timezone_or_error(timezone_name)).date()


def _month_date(year: int, month: int, requested_day: int) -> date:
    return date(year, month, min(requested_day, calendar.monthrange(year, month)[1]))


def _add_months(year: int, month: int, amount: int) -> tuple[int, int]:
    zero_based = year * 12 + month - 1 + amount
    return zero_based // 12, zero_based % 12 + 1


def _next_candidate(
    anchor_date: date,
    frequency: str,
    interval: int,
    weekdays: tuple[int, ...],
    month_day: int | None,
    year_month: int | None,
    year_day: int | None,
    current: date,
) -> date:
    """Return the first candidate strictly after ``current``."""

    if frequency == "weekly":
        selected = weekdays or (anchor_date.weekday(),)
        candidate = current + timedelta(days=1)
        anchor_week_start = anchor_date - timedelta(days=anchor_date.weekday())
        while True:
            candidate_week_start = candidate - timedelta(days=candidate.weekday())
            weeks_from_anchor = (candidate_week_start - anchor_week_start).days // 7
            if candidate.weekday() in selected and weeks_from_anchor >= 0:
                if weeks_from_anchor % interval == 0:
                    return candidate
            candidate += timedelta(days=1)

    if frequency == "monthly":
        requested_day = month_day or anchor_date.day
        months_from_anchor = (
            (current.year - anchor_date.year) * 12 + current.month - anchor_date.month
        )
        offset = max(0, months_from_anchor + 1)
        while True:
            year, month = _add_months(anchor_date.year, anchor_date.month, offset)
            if offset % interval == 0:
                candidate = _month_date(year, month, requested_day)
                if candidate > current:
                    return candidate
            offset += 1

    if frequency == "yearly":
        month = year_month or anchor_date.month
        day = year_day or anchor_date.day
        first_year = max(anchor_date.year, current.year + (current >= date(current.year, month, 1)))
        year = first_year
        while True:
            years_from_anchor = year - anchor_date.year
            if years_from_anchor >= 0 and years_from_anchor % interval == 0:
                candidate = _month_date(year, month, day)
                if candidate > current:
                    return candidate
            year += 1

    raise ValueError("unsupported recurrence frequency")


def iter_calendar_occurrences(
    anchor_date: date,
    frequency: str,
    interval: int = 1,
    weekdays: tuple[int, ...] = (),
    month_day: int | None = None,
    year_month: int | None = None,
    year_day: int | None = None,
    until_date: date | None = None,
    occurrence_count: int | None = None,
    *,
    after_date: date | None = None,
    limit: int | None = None,
) -> Iterator[CalendarOccurrence]:
    """Yield bounded calendar occurrences in chronological order."""

    if interval < 1:
        raise ValueError("interval must be positive")
    if frequency not in {"weekly", "monthly", "yearly"}:
        raise ValueError("unsupported recurrence frequency")
    if until_date is not None and occurrence_count is not None:
        raise ValueError("until_date and occurrence_count are mutually exclusive")

    current = anchor_date - timedelta(days=1)
    sequence_number = 0
    yielded = 0
    while True:
        occurrence_date = (
            anchor_date
            if sequence_number == 0
            else _next_candidate(
                anchor_date,
                frequency,
                interval,
                weekdays,
                month_day,
                year_month,
                year_day,
                current,
            )
        )
        sequence_number += 1
        current = occurrence_date

        if occurrence_count is not None and sequence_number > occurrence_count:
            return
        if until_date is not None and occurrence_date > until_date:
            return
        if after_date is not None and occurrence_date <= after_date:
            continue

        yield CalendarOccurrence(occurrence_date, sequence_number)
        yielded += 1
        if limit is not None and yielded >= limit:
            return


def next_calendar_occurrence(
    anchor_date: date,
    frequency: str,
    interval: int,
    weekdays: tuple[int, ...],
    month_day: int | None,
    year_month: int | None,
    year_day: int | None,
    until_date: date | None,
    occurrence_count: int | None,
    current_date: date,
) -> CalendarOccurrence | None:
    """Return the next occurrence after ``current_date`` or ``None``."""

    return next(
        iter_calendar_occurrences(
            anchor_date,
            frequency,
            interval,
            weekdays,
            month_day,
            year_month,
            year_day,
            until_date,
            occurrence_count,
            after_date=current_date,
            limit=1,
        ),
        None,
    )
