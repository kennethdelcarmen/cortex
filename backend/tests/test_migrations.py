"""Schema migration tests."""

import os
import sqlite3
import subprocess
import sys
from pathlib import Path


def upgrade_database(database_path: Path, monkeypatch) -> None:
    """Apply the checked-in migrations to a temporary database."""

    monkeypatch.setenv("CORTEX_DATABASE_PATH", str(database_path))
    backend_path = Path(__file__).parents[1]
    subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            str(backend_path / "alembic.ini"),
            "upgrade",
            "head",
        ],
        cwd=backend_path,
        env=os.environ.copy(),
        check=True,
    )


def test_auth_migration_creates_schema_and_indexes(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "cortex.db"
    upgrade_database(database_path, monkeypatch)

    with sqlite3.connect(database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        assert {"alembic_version", "users", "sessions"} <= tables

        user_columns = {row[1] for row in connection.execute("PRAGMA table_info(users)")}
        session_columns = {row[1] for row in connection.execute("PRAGMA table_info(sessions)")}
        assert user_columns == {
            "id",
            "email",
            "password_hash",
            "is_active",
            "is_owner",
            "created_at",
            "updated_at",
            "password_changed_at",
        }
        assert session_columns == {
            "id",
            "user_id",
            "token_hash",
            "csrf_token_hash",
            "created_at",
            "last_seen_at",
            "idle_expires_at",
            "absolute_expires_at",
            "revoked_at",
        }

        indexes = {
            row[1]
            for row in connection.execute(
                "SELECT type, name FROM sqlite_master WHERE type = 'index'"
            )
        }
        assert {
            "ix_users_email",
            "uq_users_single_owner",
            "ix_sessions_token_hash",
            "ix_sessions_user_id",
            "ix_sessions_expiry_cleanup",
        } <= indexes


def test_auth_migration_is_idempotent(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "cortex.db"
    upgrade_database(database_path, monkeypatch)
    upgrade_database(database_path, monkeypatch)

    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "0001_auth_foundation",
        )
