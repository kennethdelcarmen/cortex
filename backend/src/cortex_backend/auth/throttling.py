"""Bounded process-local login abuse protection."""

from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class _ThrottleRecord:
    failures: int
    first_failure_at: datetime
    locked_until: datetime | None = None


class LoginThrottle:
    """Track short-lived failed-login windows without persisting client addresses."""

    def __init__(
        self,
        *,
        max_entries: int = 10_000,
        failure_window: timedelta = timedelta(minutes=15),
        lockout_duration: timedelta = timedelta(minutes=1),
        max_failures: int = 5,
    ) -> None:
        self._records: OrderedDict[str, _ThrottleRecord] = OrderedDict()
        self._max_entries = max_entries
        self._failure_window = failure_window
        self._lockout_duration = lockout_duration
        self._max_failures = max_failures

    def is_blocked(self, key: str, now: datetime) -> bool:
        """Return whether a key is currently locked out."""

        self._cleanup(now)
        record = self._records.get(key)
        if record is None:
            return False
        self._records.move_to_end(key)
        return record.locked_until is not None and record.locked_until > now

    def record_failure(self, key: str, now: datetime) -> None:
        """Record a failure and apply a short lockout at the threshold."""

        self._cleanup(now)
        record = self._records.get(key)
        if record is None or now - record.first_failure_at > self._failure_window:
            record = _ThrottleRecord(failures=0, first_failure_at=now)
            self._records[key] = record
        record.failures += 1
        if record.failures >= self._max_failures:
            record.locked_until = now + self._lockout_duration
        self._records.move_to_end(key)
        self._trim()

    def record_success(self, key: str) -> None:
        """Forget failures after a successful login."""

        self._records.pop(key, None)

    def _cleanup(self, now: datetime) -> None:
        stale = [
            key
            for key, record in self._records.items()
            if (record.locked_until is not None and record.locked_until <= now)
            or (
                record.locked_until is None and now - record.first_failure_at > self._failure_window
            )
        ]
        for key in stale:
            self._records.pop(key, None)

    def _trim(self) -> None:
        while len(self._records) > self._max_entries:
            self._records.popitem(last=False)
