"""Authentication use cases over the shared database storage seam."""

import secrets
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError

from ..config import Settings
from ..storage import DatabaseStorage
from .errors import (
    AlreadyInitializedError,
    InvalidCredentialsError,
    InvalidCurrentPasswordError,
    InvalidSetupSecretError,
    SetupNotConfiguredError,
    UnauthenticatedError,
)
from .models import AuthSession, User
from .security import (
    hash_password,
    hash_token,
    new_token,
    refreshed_idle_expiry,
    session_expiries,
    utc_now,
    verify_password,
)
from .throttling import LoginThrottle


@dataclass(frozen=True)
class UserRecord:
    id: str
    email: str
    created_at: datetime


@dataclass(frozen=True)
class AuthResult:
    user: UserRecord
    session_id: str
    session_token: str
    csrf_token: str
    absolute_expires_at: datetime


@dataclass(frozen=True)
class CurrentAuth:
    user: UserRecord
    session_id: str
    csrf_token_hash: str


def normalize_email(value: str) -> str:
    """Normalize the local email identity consistently across setup and login."""

    return value.strip().casefold()


def _user_record(user: User) -> UserRecord:
    return UserRecord(id=user.id, email=user.email, created_at=user.created_at)


def _new_session(user_id: str, now: datetime) -> tuple[AuthSession, str, str]:
    session_token = new_token()
    csrf_token = new_token()
    idle_expires_at, absolute_expires_at = session_expiries(now)
    session = AuthSession(
        id=str(uuid4()),
        user_id=user_id,
        token_hash=hash_token(session_token),
        csrf_token_hash=hash_token(csrf_token),
        created_at=now,
        last_seen_at=now,
        idle_expires_at=idle_expires_at,
        absolute_expires_at=absolute_expires_at,
    )
    return session, session_token, csrf_token


async def setup_owner(
    storage: DatabaseStorage,
    settings: Settings,
    email: str,
    password: str,
    setup_secret: str | None,
) -> AuthResult:
    """Create the one local owner and immediately authenticate the browser."""

    if settings.setup_secret is None:
        raise SetupNotConfiguredError()
    if setup_secret is None:
        raise InvalidSetupSecretError()

    if not secrets.compare_digest(settings.setup_secret.get_secret_value(), setup_secret):
        raise InvalidSetupSecretError()

    normalized_email = normalize_email(email)
    now = utc_now()
    password_hash = hash_password(password)

    try:
        async with storage.session() as db:
            async with db.begin():
                existing_owner = await db.scalar(
                    select(User.id).where(User.is_owner.is_(True)).limit(1)
                )
                if existing_owner is not None:
                    raise AlreadyInitializedError()

                user = User(
                    id=str(uuid4()),
                    email=normalized_email,
                    password_hash=password_hash,
                    is_active=True,
                    is_owner=True,
                    created_at=now,
                    updated_at=now,
                    password_changed_at=now,
                )
                db.add(user)
                await db.flush()
                session, session_token, csrf_token = _new_session(user.id, now)
                db.add(session)
                await db.flush()
                result = AuthResult(
                    user=_user_record(user),
                    session_id=session.id,
                    session_token=session_token,
                    csrf_token=csrf_token,
                    absolute_expires_at=session.absolute_expires_at,
                )
    except AlreadyInitializedError:
        raise
    except IntegrityError as exc:
        raise AlreadyInitializedError() from exc
    return result


async def login(
    storage: DatabaseStorage,
    throttle: LoginThrottle,
    email: str,
    password: str,
    client_host: str,
) -> AuthResult:
    """Verify credentials and create a fresh revocable session."""

    normalized_email = normalize_email(email)
    key = f"{normalized_email}\x00{client_host}"
    now = utc_now()
    if throttle.is_blocked(key, now):
        raise InvalidCredentialsError()

    async with storage.session() as db:
        user = await db.scalar(select(User).where(User.email == normalized_email).limit(1))

    password_valid = verify_password(password, user.password_hash if user is not None else None)
    if user is None or not user.is_active or not password_valid:
        verify_password(password, None)
        throttle.record_failure(key, now)
        raise InvalidCredentialsError()

    async with storage.session() as db:
        async with db.begin():
            current_user = await db.get(User, user.id)
            if current_user is None or not current_user.is_active:
                throttle.record_failure(key, now)
                raise InvalidCredentialsError()
            session, session_token, csrf_token = _new_session(current_user.id, now)
            db.add(session)
            await db.execute(
                delete(AuthSession).where(
                    AuthSession.user_id == current_user.id,
                    (AuthSession.revoked_at.is_not(None))
                    | (AuthSession.absolute_expires_at <= now),
                )
            )
            await db.flush()
            result = AuthResult(
                user=_user_record(current_user),
                session_id=session.id,
                session_token=session_token,
                csrf_token=csrf_token,
                absolute_expires_at=session.absolute_expires_at,
            )

    throttle.record_success(key)
    return result


async def authenticate_session(storage: DatabaseStorage, session_token: str) -> CurrentAuth:
    """Resolve and slide a valid session, rejecting expired or revoked credentials."""

    if len(session_token) > 128:
        raise UnauthenticatedError()
    now = utc_now()
    token_hash = hash_token(session_token)
    async with storage.session() as db:
        async with db.begin():
            session = await db.scalar(
                select(AuthSession).where(AuthSession.token_hash == token_hash).limit(1)
            )
            if session is None:
                raise UnauthenticatedError()
            user = await db.get(User, session.user_id)
            if (
                user is None
                or not user.is_active
                or session.revoked_at is not None
                or session.idle_expires_at <= now
                or session.absolute_expires_at <= now
            ):
                raise UnauthenticatedError()

            session.last_seen_at = now
            session.idle_expires_at = refreshed_idle_expiry(now, session.absolute_expires_at)
            await db.flush()
            return CurrentAuth(
                user=_user_record(user),
                session_id=session.id,
                csrf_token_hash=session.csrf_token_hash,
            )


async def refresh_csrf_token(storage: DatabaseStorage, auth: CurrentAuth) -> str:
    """Rotate the readable CSRF token for an authenticated session."""

    now = utc_now()
    async with storage.session() as db:
        async with db.begin():
            session = await db.get(AuthSession, auth.session_id)
            if (
                session is None
                or session.revoked_at is not None
                or session.absolute_expires_at <= now
            ):
                raise UnauthenticatedError()
            token = new_token()
            session.csrf_token_hash = hash_token(token)
            await db.flush()
            return token


async def logout(storage: DatabaseStorage, auth: CurrentAuth) -> None:
    """Revoke the current session."""

    async with storage.session() as db:
        async with db.begin():
            session = await db.get(AuthSession, auth.session_id)
            if session is not None and session.revoked_at is None:
                session.revoked_at = utc_now()
                await db.flush()


async def change_password(
    storage: DatabaseStorage,
    auth: CurrentAuth,
    current_password: str,
    new_password: str,
) -> AuthResult:
    """Change the password, revoke every old session, and issue a fresh one."""

    async with storage.session() as db:
        user = await db.get(User, auth.user.id)
    if user is None or not verify_password(current_password, user.password_hash):
        raise InvalidCurrentPasswordError()

    now = utc_now()
    password_hash = hash_password(new_password)
    async with storage.session() as db:
        async with db.begin():
            current_user = await db.get(User, auth.user.id)
            if current_user is None or not current_user.is_active:
                raise UnauthenticatedError()
            current_user.password_hash = password_hash
            current_user.updated_at = now
            current_user.password_changed_at = now
            await db.execute(
                update(AuthSession)
                .where(AuthSession.user_id == current_user.id)
                .values(revoked_at=now)
            )
            session, session_token, csrf_token = _new_session(current_user.id, now)
            db.add(session)
            await db.flush()
            return AuthResult(
                user=_user_record(current_user),
                session_id=session.id,
                session_token=session_token,
                csrf_token=csrf_token,
                absolute_expires_at=session.absolute_expires_at,
            )
