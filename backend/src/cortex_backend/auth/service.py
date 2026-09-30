"""Authentication use cases over the shared database storage seam."""

import secrets
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings
from ..logs.models import ActivityLog
from ..storage import DatabaseStorage
from .errors import (
    AlreadyInitializedError,
    InvalidCredentialsError,
    InvalidCurrentPasswordError,
    InvalidMcpApiKeyConfigurationError,
    InvalidSetupSecretError,
    SetupNotConfiguredError,
    UnauthenticatedError,
)
from .models import AuthSession, McpApiKey, User
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
    display_name: str | None
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


@dataclass(frozen=True)
class McpAuth:
    user: UserRecord
    credential_type: str


@dataclass(frozen=True)
class McpApiKeyRecord:
    created_at: datetime
    updated_at: datetime
    revoked_at: datetime | None


def normalize_email(value: str) -> str:
    """Normalize the local email identity consistently across setup and login."""

    return value.strip().casefold()


def normalize_display_name(value: str | None) -> str | None:
    """Normalize an optional owner-facing display name."""

    if value is None:
        return None
    normalized = " ".join(value.strip().split())
    return normalized or None


def validate_setup_secret(settings: Settings, setup_secret: str | None) -> None:
    """Validate the configured installation secret without changing application state."""

    if settings.setup_secret is None:
        raise SetupNotConfiguredError()
    if setup_secret is None or not secrets.compare_digest(
        settings.setup_secret.get_secret_value(), setup_secret
    ):
        raise InvalidSetupSecretError()


def _user_record(user: User) -> UserRecord:
    return UserRecord(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        created_at=user.created_at,
    )


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


def _validate_mcp_key_source(
    settings: Settings,
    setup_secret: str | None,
    mcp_api_key: str | None,
    use_setup_secret_as_mcp_key: bool,
) -> tuple[str, str]:
    """Resolve and validate the one credential selected during setup."""

    if (mcp_api_key is not None) == use_setup_secret_as_mcp_key:
        raise InvalidMcpApiKeyConfigurationError()

    if use_setup_secret_as_mcp_key:
        if setup_secret is None:
            raise InvalidMcpApiKeyConfigurationError()
        return setup_secret, "setup_secret"

    if mcp_api_key is None or not 32 <= len(mcp_api_key) <= 256:
        raise InvalidMcpApiKeyConfigurationError()
    if settings.setup_secret is not None and secrets.compare_digest(
        settings.setup_secret.get_secret_value(), mcp_api_key
    ):
        raise InvalidMcpApiKeyConfigurationError()
    return mcp_api_key, "operator"


def _append_auth_activity(
    db: AsyncSession,
    user_id: str,
    event_type: str,
    metadata: dict[str, str],
    now: datetime,
) -> None:
    """Append credential lifecycle metadata within the owning transaction."""

    db.add(
        ActivityLog(
            id=str(uuid4()),
            user_id=user_id,
            event_type=event_type,
            entity_type="mcp_api_key",
            entity_id=None,
            metadata_json=metadata,
            created_at=now,
        )
    )


async def setup_owner(
    storage: DatabaseStorage,
    settings: Settings,
    email: str,
    display_name: str | None,
    password: str,
    setup_secret: str | None,
    mcp_api_key: str | None,
    use_setup_secret_as_mcp_key: bool,
) -> AuthResult:
    """Create the one local owner and immediately authenticate the browser."""

    validate_setup_secret(settings, setup_secret)

    resolved_mcp_key, mcp_key_source = _validate_mcp_key_source(
        settings,
        setup_secret,
        mcp_api_key,
        use_setup_secret_as_mcp_key,
    )
    normalized_email = normalize_email(email)
    normalized_display_name = normalize_display_name(display_name)
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
                    display_name=normalized_display_name,
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
                db.add(
                    McpApiKey(
                        id=str(uuid4()),
                        user_id=user.id,
                        key_hash=hash_token(resolved_mcp_key),
                        created_at=now,
                        updated_at=now,
                    )
                )
                _append_auth_activity(
                    db,
                    user.id,
                    "auth.mcp_key_created",
                    {"source": mcp_key_source},
                    now,
                )
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


async def update_profile(
    storage: DatabaseStorage,
    user_id: str,
    display_name: str | None,
) -> UserRecord:
    """Update the authenticated owner's profile fields."""

    now = utc_now()
    async with storage.session() as db:
        async with db.begin():
            user = await db.get(User, user_id)
            if user is None or not user.is_active:
                raise UnauthenticatedError()
            user.display_name = normalize_display_name(display_name)
            user.updated_at = now
            await db.flush()
            return _user_record(user)


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


async def authenticate_mcp_token(storage: DatabaseStorage, token: str) -> McpAuth:
    """Authenticate an MCP bearer token as either a session or static key."""

    try:
        session_auth = await authenticate_session(storage, token)
    except UnauthenticatedError:
        token_hash = hash_token(token)
        async with storage.session() as db:
            async with db.begin():
                api_key = await db.scalar(
                    select(McpApiKey).where(
                        McpApiKey.key_hash == token_hash,
                        McpApiKey.revoked_at.is_(None),
                    )
                )
                if api_key is None:
                    raise UnauthenticatedError() from None
                user = await db.get(User, api_key.user_id)
                if user is None or not user.is_active:
                    raise UnauthenticatedError() from None
                return McpAuth(user=_user_record(user), credential_type="api_key")
    return McpAuth(user=session_auth.user, credential_type="session")


def _mcp_api_key_record(api_key: McpApiKey) -> McpApiKeyRecord:
    return McpApiKeyRecord(
        created_at=api_key.created_at,
        updated_at=api_key.updated_at,
        revoked_at=api_key.revoked_at,
    )


async def get_mcp_api_key(
    storage: DatabaseStorage,
    user_id: str,
) -> McpApiKeyRecord | None:
    """Return MCP key metadata without exposing credential material."""

    async with storage.session() as db:
        api_key = await db.scalar(select(McpApiKey).where(McpApiKey.user_id == user_id))
        return _mcp_api_key_record(api_key) if api_key is not None else None


async def replace_mcp_api_key(
    storage: DatabaseStorage,
    user_id: str,
    key: str,
) -> McpApiKeyRecord:
    """Create or replace an owner-scoped MCP bearer key."""

    if not 32 <= len(key) <= 256:
        raise InvalidMcpApiKeyConfigurationError()

    now = utc_now()
    async with storage.session() as db:
        async with db.begin():
            api_key = await db.scalar(select(McpApiKey).where(McpApiKey.user_id == user_id))
            if api_key is None:
                api_key = McpApiKey(
                    id=str(uuid4()),
                    user_id=user_id,
                    key_hash=hash_token(key),
                    created_at=now,
                    updated_at=now,
                )
                db.add(api_key)
                event_type = "auth.mcp_key_created"
            else:
                api_key.key_hash = hash_token(key)
                api_key.updated_at = now
                api_key.revoked_at = None
                event_type = "auth.mcp_key_rotated"
            _append_auth_activity(db, user_id, event_type, {"source": "owner_settings"}, now)
            await db.flush()
            return _mcp_api_key_record(api_key)


async def revoke_mcp_api_key(storage: DatabaseStorage, user_id: str) -> None:
    """Revoke the owner-scoped MCP bearer key without changing sessions."""

    now = utc_now()
    async with storage.session() as db:
        async with db.begin():
            api_key = await db.scalar(select(McpApiKey).where(McpApiKey.user_id == user_id))
            if api_key is None or api_key.revoked_at is not None:
                return
            api_key.revoked_at = now
            api_key.updated_at = now
            _append_auth_activity(
                db,
                user_id,
                "auth.mcp_key_revoked",
                {"source": "owner_settings"},
                now,
            )
            await db.flush()


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
