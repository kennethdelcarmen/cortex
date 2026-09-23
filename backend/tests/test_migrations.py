"""Schema migration tests."""

import os
import sqlite3
import subprocess
import sys
from pathlib import Path


def upgrade_database(database_path: Path, monkeypatch, revision: str = "head") -> None:
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
            revision,
        ],
        cwd=backend_path,
        env=os.environ.copy(),
        check=True,
    )


def test_domain_migration_creates_schema_and_indexes(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "cortex.db"
    upgrade_database(database_path, monkeypatch)

    with sqlite3.connect(database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        assert {"alembic_version", "users", "sessions", "mcp_api_keys"} <= tables

        user_columns = {row[1] for row in connection.execute("PRAGMA table_info(users)")}
        session_columns = {row[1] for row in connection.execute("PRAGMA table_info(sessions)")}
        mcp_api_key_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(mcp_api_keys)")
        }
        task_columns = {row[1] for row in connection.execute("PRAGMA table_info(tasks)")}
        tag_columns = {row[1] for row in connection.execute("PRAGMA table_info(tags)")}
        task_tag_columns = {row[1] for row in connection.execute("PRAGMA table_info(task_tags)")}
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
        assert mcp_api_key_columns == {
            "id",
            "user_id",
            "key_hash",
            "created_at",
            "updated_at",
            "revoked_at",
        }
        assert task_columns == {
            "id",
            "user_id",
            "title",
            "description",
            "status",
            "priority",
            "position",
            "start_at",
            "due_at",
            "created_at",
            "updated_at",
            "deleted_at",
            "series_id",
            "occurrence_key",
            "series_exception",
            "skipped_at",
        }
        task_series_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(task_series)")
        }
        assert task_series_columns == {
            "id",
            "user_id",
            "title",
            "description",
            "status",
            "priority",
            "timezone",
            "anchor_at",
            "anchor_kind",
            "duration_seconds",
            "rule",
            "until_date",
            "occurrence_count",
            "state",
            "materialized_through_at",
            "created_at",
            "updated_at",
            "paused_at",
            "ended_at",
        }
        task_series_tag_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(task_series_tags)")
        }
        assert task_series_tag_columns == {"series_id", "tag_id"}
        assert tag_columns == {
            "id",
            "user_id",
            "name",
            "color",
            "created_at",
            "archived_at",
        }
        assert task_tag_columns == {"task_id", "tag_id"}
        note_columns = {row[1] for row in connection.execute("PRAGMA table_info(notes)")}
        assert note_columns == {
            "id",
            "user_id",
            "title",
            "body",
            "journal_date",
            "created_at",
            "updated_at",
            "deleted_at",
        }
        note_tag_columns = {row[1] for row in connection.execute("PRAGMA table_info(note_tags)")}
        assert note_tag_columns == {"note_id", "tag_id"}
        assert connection.execute(
            "SELECT type FROM sqlite_master WHERE name = 'notes_fts'"
        ).fetchone() == ("table",)
        activity_log_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(activity_logs)")
        }
        assert activity_log_columns == {
            "id",
            "user_id",
            "event_type",
            "entity_type",
            "entity_id",
            "metadata",
            "created_at",
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
            "uq_mcp_api_keys_user_id",
            "uq_mcp_api_keys_key_hash",
            "ix_tasks_owner_deleted_status",
            "ix_tasks_owner_deleted_status_position",
            "ix_tasks_owner_deleted_priority",
            "ix_tasks_owner_deleted_due_created",
            "ix_tags_user_id",
            "ix_tags_user_archived_name",
            "ix_task_tags_tag_id",
            "ix_activity_logs_user_created",
            "ix_activity_logs_user_event_created",
            "ix_activity_logs_user_entity_created",
            "ix_task_series_owner_state_updated",
            "ix_tasks_owner_series_occurrence",
            "ix_task_series_tags_tag_id",
            "ix_notes_owner_deleted_updated",
            "ix_notes_owner_deleted_journal",
            "ix_note_tags_tag_id",
        } <= indexes


def test_migrations_are_idempotent(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "cortex.db"
    upgrade_database(database_path, monkeypatch)
    upgrade_database(database_path, monkeypatch)

    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "0009_fixed_tags",
        )


def test_mcp_key_migration_upgrades_existing_database(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "cortex.db"
    upgrade_database(database_path, monkeypatch, "0007_notes_html_content")

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "INSERT INTO users "
            "(id, email, password_hash, is_active, is_owner, created_at, updated_at, "
            "password_changed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "00000000-0000-0000-0000-000000000001",
                "owner@example.com",
                "not-used",
                1,
                1,
                "2027-01-01T00:00:00+00:00",
                "2027-01-01T00:00:00+00:00",
                "2027-01-01T00:00:00+00:00",
            ),
        )
        connection.commit()

    upgrade_database(database_path, monkeypatch)

    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM users").fetchone() == (1,)
        assert connection.execute("SELECT COUNT(*) FROM mcp_api_keys").fetchone() == (0,)


def test_fixed_tags_migration_defaults_existing_tags_and_preserves_memberships(
    tmp_path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "cortex.db"
    upgrade_database(database_path, monkeypatch, "0008_mcp_api_keys")

    with sqlite3.connect(database_path) as connection:
        user_id = "00000000-0000-0000-0000-000000000001"
        connection.execute(
            "INSERT INTO users "
            "(id, email, password_hash, is_active, is_owner, created_at, updated_at, "
            "password_changed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                user_id,
                "owner@example.com",
                "not-used",
                1,
                1,
                "2027-01-01T00:00:00+00:00",
                "2027-01-01T00:00:00+00:00",
                "2027-01-01T00:00:00+00:00",
            ),
        )
        connection.execute(
            "INSERT INTO tags (id, user_id, name, created_at) VALUES (?, ?, ?, ?)",
            (
                "00000000-0000-0000-0000-000000000010",
                user_id,
                "work",
                "2027-01-01T00:00:00+00:00",
            ),
        )
        connection.execute(
            "INSERT INTO tasks "
            "(id, user_id, title, status, priority, position, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "00000000-0000-0000-0000-000000000020",
                user_id,
                "Existing task",
                "backlog",
                "none",
                0,
                "2027-01-01T00:00:00+00:00",
                "2027-01-01T00:00:00+00:00",
            ),
        )
        connection.execute(
            "INSERT INTO notes (id, user_id, body, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (
                "00000000-0000-0000-0000-000000000030",
                user_id,
                "Existing note",
                "2027-01-01T00:00:00+00:00",
                "2027-01-01T00:00:00+00:00",
            ),
        )
        connection.execute(
            "INSERT INTO task_tags (task_id, tag_id) VALUES (?, ?)",
            (
                "00000000-0000-0000-0000-000000000020",
                "00000000-0000-0000-0000-000000000010",
            ),
        )
        connection.execute(
            "INSERT INTO note_tags (note_id, tag_id) VALUES (?, ?)",
            (
                "00000000-0000-0000-0000-000000000030",
                "00000000-0000-0000-0000-000000000010",
            ),
        )
        connection.commit()

    upgrade_database(database_path, monkeypatch)

    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT color, archived_at FROM tags WHERE name = 'work'"
        ).fetchone() == ("slate", None)
        assert connection.execute("SELECT COUNT(*) FROM task_tags").fetchone() == (1,)
        assert connection.execute("SELECT COUNT(*) FROM note_tags").fetchone() == (1,)


def test_notes_migration_converts_bodies_and_rebuilds_search_index(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "cortex.db"
    monkeypatch.setenv("CORTEX_DATABASE_PATH", str(database_path))
    backend_path = Path(__file__).parents[1]
    environment = os.environ.copy()
    subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            str(backend_path / "alembic.ini"),
            "upgrade",
            "0006_notes_foundation",
        ],
        cwd=backend_path,
        env=environment,
        check=True,
    )
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "INSERT INTO users "
            "(id, email, password_hash, is_active, is_owner, created_at, updated_at, "
            "password_changed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "00000000-0000-0000-0000-000000000001",
                "owner@example.com",
                "not-used",
                1,
                1,
                "2027-01-01T00:00:00+00:00",
                "2027-01-01T00:00:00+00:00",
                "2027-01-01T00:00:00+00:00",
            ),
        )
        connection.execute(
            "INSERT INTO notes "
            "(id, user_id, title, body, journal_date, created_at, updated_at, deleted_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "00000000-0000-0000-0000-000000000002",
                "00000000-0000-0000-0000-000000000001",
                "Legacy",
                "# Legacy\n\nSearchable **body**.",
                None,
                "2027-01-01T00:00:00+00:00",
                "2027-01-01T00:00:00+00:00",
                None,
            ),
        )
        connection.commit()

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
        env=environment,
        check=True,
    )

    with sqlite3.connect(database_path) as connection:
        body = connection.execute("SELECT body FROM notes").fetchone()[0]
        indexed = connection.execute(
            "SELECT body FROM notes_fts WHERE notes_fts MATCH ?", ("Searchable",)
        ).fetchone()[0]
        assert body == "<h1>Legacy</h1>\n<p>Searchable <strong>body</strong>.</p>"
        assert indexed == "Legacy Searchable body."


def test_tasks_migration_downgrade_removes_task_schema(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "cortex.db"
    upgrade_database(database_path, monkeypatch)
    backend_path = Path(__file__).parents[1]
    subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            str(backend_path / "alembic.ini"),
            "downgrade",
            "0001_auth_foundation",
        ],
        cwd=backend_path,
        env=os.environ.copy(),
        check=True,
    )

    with sqlite3.connect(database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        assert {"users", "sessions"} <= tables
        assert (
            not {
                "tasks",
                "tags",
                "task_tags",
                "activity_logs",
                "task_series",
                "task_series_tags",
                "notes",
                "note_tags",
                "notes_fts",
            }
            & tables
        )


def test_activity_logs_migration_downgrade_removes_only_activity_schema(
    tmp_path, monkeypatch
) -> None:
    database_path = tmp_path / "cortex.db"
    upgrade_database(database_path, monkeypatch)
    backend_path = Path(__file__).parents[1]
    subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            str(backend_path / "alembic.ini"),
            "downgrade",
            "0003_task_positions",
        ],
        cwd=backend_path,
        env=os.environ.copy(),
        check=True,
    )

    with sqlite3.connect(database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        assert "activity_logs" not in tables
        assert {"users", "sessions", "tasks", "tags", "task_tags"} <= tables


def test_notes_migration_downgrade_removes_only_notes_schema(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "cortex.db"
    upgrade_database(database_path, monkeypatch)
    backend_path = Path(__file__).parents[1]
    subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            str(backend_path / "alembic.ini"),
            "downgrade",
            "0005_task_recurrencies",
        ],
        cwd=backend_path,
        env=os.environ.copy(),
        check=True,
    )

    with sqlite3.connect(database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        assert {"users", "sessions", "tasks", "tags", "task_tags"} <= tables
        assert not {"notes", "note_tags", "notes_fts"} & tables
