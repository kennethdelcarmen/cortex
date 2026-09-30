"""SQLAlchemy models owned by the authentication domain."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative metadata used by Alembic and auth persistence."""


class User(Base):
    """The single local owner supported by the first auth slice."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_owner: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    password_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    sessions: Mapped[list["AuthSession"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    mcp_api_key: Mapped["McpApiKey | None"] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
    )


Index(
    "ix_users_email",
    User.email,
    unique=True,
)
Index(
    "uq_users_single_owner",
    User.is_owner,
    unique=True,
    sqlite_where=text("is_owner = 1"),
)


class AuthSession(Base):
    """A revocable opaque browser session."""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    csrf_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    idle_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    absolute_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="sessions")


Index("ix_sessions_user_id", AuthSession.user_id)
Index("ix_sessions_token_hash", AuthSession.token_hash, unique=True)
Index(
    "ix_sessions_expiry_cleanup",
    AuthSession.idle_expires_at,
    AuthSession.absolute_expires_at,
)


class McpApiKey(Base):
    """A revocable, owner-scoped bearer credential for MCP clients."""

    __tablename__ = "mcp_api_keys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="mcp_api_key")


Index("uq_mcp_api_keys_user_id", McpApiKey.user_id, unique=True)
Index("uq_mcp_api_keys_key_hash", McpApiKey.key_hash, unique=True)
