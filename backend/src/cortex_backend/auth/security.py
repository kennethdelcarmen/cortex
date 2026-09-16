"""Password, token, cookie, and request-origin security helpers."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import Request

from ..config import Settings
from .errors import CsrfValidationError

SESSION_COOKIE_NAME = "cortex_session"
CSRF_COOKIE_NAME = "cortex_csrf"
CSRF_HEADER_NAME = "X-CSRF-Token"
SESSION_IDLE_DAYS = 30
SESSION_ABSOLUTE_DAYS = 90

_password_hasher = PasswordHasher()
# A valid fixed hash keeps unknown-email login attempts on the same verification path.
_DUMMY_PASSWORD_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$"
    "0j9cmqOFJKnvJxUKF4WvUg$"
    "2APBzM3Ah9Tm0aaRXD9v2/HsyoonUHmZrS8g9ATKMJ4"
)


def utc_now() -> datetime:
    """Return a naive UTC timestamp suitable for SQLite DateTime columns."""

    return datetime.now(UTC).replace(tzinfo=None)


def hash_password(password: str) -> str:
    """Hash a password using Argon2id's maintained default parameters."""

    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    """Verify a password without exposing hash or verification details."""

    candidate_hash = password_hash or _DUMMY_PASSWORD_HASH
    try:
        return _password_hasher.verify(candidate_hash, password)
    except (InvalidHashError, VerificationError, VerifyMismatchError):
        return False


def new_token() -> str:
    """Return a 256-bit URL-safe random token."""

    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Hash a bearer value before persistence or comparison."""

    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def session_expiries(now: datetime) -> tuple[datetime, datetime]:
    """Return idle and absolute expiry timestamps for a new session."""

    idle = now + timedelta(days=SESSION_IDLE_DAYS)
    absolute = now + timedelta(days=SESSION_ABSOLUTE_DAYS)
    return idle, absolute


def refreshed_idle_expiry(now: datetime, absolute_expiry: datetime) -> datetime:
    """Slide idle expiry without ever extending the absolute session limit."""

    return min(now + timedelta(days=SESSION_IDLE_DAYS), absolute_expiry)


def validate_request_origin(request: Request, settings: Settings, *, required: bool) -> None:
    """Allow same-origin or explicitly configured frontend origins."""

    origin = request.headers.get("origin")
    if origin is None:
        if required:
            raise CsrfValidationError()
        return

    parsed = urlsplit(origin)
    host = request.headers.get("host")
    same_origin = bool(parsed.scheme and parsed.netloc and host) and origin == (
        f"{request.url.scheme}://{host}"
    )
    if same_origin or origin in settings.cors_origins:
        return
    raise CsrfValidationError()


def validate_csrf(request: Request, expected_hash: str) -> None:
    """Validate the double-submit token against the server-side session hash."""

    header_token = request.headers.get(CSRF_HEADER_NAME)
    cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
    if not header_token or not cookie_token:
        raise CsrfValidationError()
    if not secrets.compare_digest(header_token, cookie_token):
        raise CsrfValidationError()
    if not secrets.compare_digest(hash_token(header_token), expected_hash):
        raise CsrfValidationError()
