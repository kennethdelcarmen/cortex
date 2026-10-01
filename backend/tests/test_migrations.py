"""Schema migration tests."""

import os
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime
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
            "display_name",
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
        file_tag_columns = {row[1] for row in connection.execute("PRAGMA table_info(file_tags)")}
        assert file_tag_columns == {"file_id", "tag_id"}
        note_file_columns = {row[1] for row in connection.execute("PRAGMA table_info(note_files)")}
        task_file_columns = {row[1] for row in connection.execute("PRAGMA table_info(task_files)")}
        task_series_file_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(task_series_files)")
        }
        assert note_file_columns == {"note_id", "file_id", "position"}
        assert task_file_columns == {"task_id", "file_id", "position"}
        assert task_series_file_columns == {"series_id", "file_id", "position"}
        assert connection.execute(
            "SELECT type FROM sqlite_master WHERE name = 'notes_fts'"
        ).fetchone() == ("table",)
        assert connection.execute(
            "SELECT type FROM sqlite_master WHERE name = 'files_fts'"
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
        file_columns = {row[1] for row in connection.execute("PRAGMA table_info(files)")}
        assert file_columns == {
            "id",
            "user_id",
            "original_name",
            "storage_key",
            "size_bytes",
            "sha256",
            "created_at",
            "updated_at",
            "deleted_at",
        }
        context_job_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(file_context_jobs)")
        }
        assert context_job_columns == {
            "id",
            "user_id",
            "source_sha256",
            "status",
            "attempts",
            "available_at",
            "lease_expires_at",
            "last_error",
            "extractor_version",
            "created_at",
            "updated_at",
        }
        artifact_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(file_artifacts)")
        }
        assert artifact_columns == {
            "id",
            "user_id",
            "source_sha256",
            "artifact_kind",
            "storage_key",
            "size_bytes",
            "sha256",
            "extractor_version",
            "created_at",
        }
        chunk_columns = {row[1] for row in connection.execute("PRAGMA table_info(content_chunks)")}
        assert chunk_columns == {
            "id",
            "user_id",
            "source_type",
            "source_id",
            "source_version",
            "source_title",
            "ordinal",
            "text",
            "created_at",
            "updated_at",
        }
        assert connection.execute(
            "SELECT type FROM sqlite_master WHERE name = 'content_chunks_fts'"
        ).fetchone() == ("table",)
        embedding_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(content_chunk_embeddings)")
        }
        assert embedding_columns == {
            "chunk_id",
            "user_id",
            "source_version",
            "model_name",
            "model_version",
            "dimensions",
            "status",
            "attempts",
            "available_at",
            "lease_expires_at",
            "last_error",
            "created_at",
            "updated_at",
        }

        money_tables = {
            "money_accounts",
            "money_payees",
            "money_categories",
            "money_budgets",
            "money_transactions",
            "money_postings",
            "money_installment_plans",
            "money_installment_occurrences",
            "money_recurring_transactions",
            "money_recurring_postings",
            "money_recurring_occurrences",
        }
        assert money_tables <= tables
        assert {
            "id",
            "user_id",
            "name",
            "account_type",
            "institution_name",
            "last_four",
            "currency_code",
            "opening_balance",
            "credit_limit",
            "statement_close_day",
            "payment_due_day",
            "created_at",
            "updated_at",
            "archived_at",
        } == {row[1] for row in connection.execute("PRAGMA table_info(money_accounts)")}
        assert {
            "id",
            "user_id",
            "name",
            "created_at",
            "updated_at",
            "archived_at",
        } == {row[1] for row in connection.execute("PRAGMA table_info(money_payees)")}
        assert {
            "id",
            "user_id",
            "name",
            "kind",
            "created_at",
            "updated_at",
            "archived_at",
        } == {row[1] for row in connection.execute("PRAGMA table_info(money_categories)")}
        assert {
            "id",
            "user_id",
            "category_id",
            "period",
            "currency_code",
            "amount",
            "created_at",
            "updated_at",
        } == {row[1] for row in connection.execute("PRAGMA table_info(money_budgets)")}
        assert {
            "id",
            "user_id",
            "transaction_date",
            "name",
            "payee_id",
            "memo",
            "state",
            "reversal_of_id",
            "created_at",
            "updated_at",
            "voided_at",
        } == {row[1] for row in connection.execute("PRAGMA table_info(money_transactions)")}
        assert {
            "id",
            "user_id",
            "transaction_id",
            "account_id",
            "category_id",
            "currency_code",
            "amount",
            "reconciliation_state",
            "cleared_at",
            "reconciled_at",
        } == {row[1] for row in connection.execute("PRAGMA table_info(money_postings)")}
        assert {
            "id",
            "user_id",
            "account_id",
            "payee_id",
            "category_id",
            "currency_code",
            "purchase_date",
            "name",
            "memo",
            "total_amount",
            "fee_amount",
            "term_months",
            "status",
            "created_at",
            "updated_at",
        } == {row[1] for row in connection.execute("PRAGMA table_info(money_installment_plans)")}
        assert {
            "id",
            "user_id",
            "plan_id",
            "sequence_number",
            "charge_date",
            "amount",
            "status",
            "transaction_id",
            "charged_at",
        } == {
            row[1] for row in connection.execute("PRAGMA table_info(money_installment_occurrences)")
        }
        assert {
            "id",
            "user_id",
            "start_date",
            "name",
            "payee_id",
            "memo",
            "timezone",
            "rule",
            "until_date",
            "occurrence_count",
            "state",
            "next_occurrence_date",
            "next_occurrence_number",
            "created_at",
            "updated_at",
            "paused_at",
            "ended_at",
        } == {
            row[1] for row in connection.execute("PRAGMA table_info(money_recurring_transactions)")
        }
        assert {
            "id",
            "user_id",
            "recurring_transaction_id",
            "account_id",
            "category_id",
            "currency_code",
            "amount",
        } == {row[1] for row in connection.execute("PRAGMA table_info(money_recurring_postings)")}
        assert {
            "id",
            "user_id",
            "recurring_transaction_id",
            "sequence_number",
            "due_date",
            "status",
            "transaction_id",
            "processed_at",
        } == {
            row[1] for row in connection.execute("PRAGMA table_info(money_recurring_occurrences)")
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
            "ix_files_owner_deleted_created",
            "ix_file_tags_tag_id",
            "ix_file_context_jobs_claim",
            "ix_file_artifacts_owner_hash",
            "ix_note_files_file_id",
            "ix_note_files_note_position",
            "ix_task_files_file_id",
            "ix_task_files_task_position",
            "ix_task_series_files_file_id",
            "ix_task_series_files_series_position",
            "ix_content_chunks_owner_source",
            "ix_content_chunks_owner_version",
            "ix_money_accounts_owner_archived_name",
            "ix_money_payees_owner_archived_name",
            "ix_money_categories_owner_archived_name",
            "ix_money_budgets_owner_period_currency",
            "ix_money_transactions_owner_date_id",
            "ix_money_transactions_owner_payee_date",
            "ix_money_transactions_owner_state_date",
            "ix_money_postings_owner_account_transaction",
            "ix_money_postings_owner_category_transaction",
            "ix_money_postings_owner_reconciliation",
            "ix_money_installment_plans_owner_account_status",
            "ix_money_installment_plans_owner_purchase_date",
            "ix_money_installment_occurrences_owner_due_status",
            "ix_money_installment_occurrences_plan_status",
            "ix_money_recurring_transactions_owner_state_updated",
            "ix_money_recurring_transactions_owner_next_state",
            "ix_money_recurring_postings_owner_schedule",
            "ix_money_recurring_occurrences_owner_due_status",
            "ix_money_recurring_occurrences_schedule_status",
        } <= indexes

        for table, parent_table in (
            ("note_files", "notes"),
            ("task_files", "tasks"),
            ("task_series_files", "task_series"),
        ):
            foreign_keys = connection.execute(f"PRAGMA foreign_key_list({table})").fetchall()
            assert {row[2] for row in foreign_keys} == {"files", parent_table}
            assert all(row[6].upper() == "CASCADE" for row in foreign_keys)
            assert (
                connection.execute(
                    "SELECT sql FROM sqlite_master WHERE type = 'index' AND name = ?",
                    (f"uq_{table}_position",),
                ).fetchone()
                is not None
            )

        file_indexes = list(connection.execute("PRAGMA index_list(files)"))
        assert any(row[2] == 1 for row in file_indexes)


def test_migrations_are_idempotent(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "cortex.db"
    upgrade_database(database_path, monkeypatch)
    upgrade_database(database_path, monkeypatch)

    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "0021_money_recurring_transactions",
        )


def test_recurring_money_migration_downgrades_cleanly(tmp_path, monkeypatch) -> None:
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
            "0020_credit_card_installments",
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
        assert (
            not {
                "money_recurring_transactions",
                "money_recurring_postings",
                "money_recurring_occurrences",
            }
            & tables
        )
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "0020_credit_card_installments",
        )


def test_embedding_migration_seeds_existing_chunks(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "cortex.db"
    upgrade_database(database_path, monkeypatch, "0018_owner_display_name")

    timestamp = datetime.now(UTC).isoformat()
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "INSERT INTO users "
            "(id, email, display_name, password_hash, is_active, is_owner, created_at, "
            "updated_at, password_changed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "user-embedding",
                "embedding@example.com",
                None,
                "hash",
                1,
                1,
                timestamp,
                timestamp,
                timestamp,
            ),
        )
        connection.execute(
            "INSERT INTO content_chunks "
            "(id, user_id, source_type, source_id, source_version, source_title, ordinal, "
            "text, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "chunk-embedding",
                "user-embedding",
                "note",
                "note-embedding",
                "source-v1",
                "Embedding note",
                0,
                "Existing chunk text",
                timestamp,
                timestamp,
            ),
        )

    upgrade_database(database_path, monkeypatch)

    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT user_id, source_version, model_name, dimensions, status, attempts "
            "FROM content_chunk_embeddings WHERE chunk_id = ?",
            ("chunk-embedding",),
        ).fetchone() == (
            "user-embedding",
            "source-v1",
            "BAAI/bge-small-en-v1.5",
            384,
            "pending",
            0,
        )


def test_transaction_name_migration_backfills_legacy_records(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "cortex.db"
    upgrade_database(database_path, monkeypatch, "0016_money_foundation")

    with sqlite3.connect(database_path) as connection:
        timestamp = datetime.now(UTC).isoformat()
        connection.execute(
            "INSERT INTO users (id, email, password_hash, created_at, updated_at, "
            "password_changed_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("user-1", "owner@example.com", "hash", timestamp, timestamp, timestamp),
        )
        connection.execute(
            "INSERT INTO money_payees (id, user_id, name, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            ("payee-1", "user-1", "Legacy payee", timestamp, timestamp),
        )
        for transaction_id, payee_id, memo in (
            ("transaction-1", "payee-1", "Legacy memo"),
            ("transaction-2", None, "  Trimmed memo  "),
            ("transaction-3", None, None),
        ):
            connection.execute(
                "INSERT INTO money_transactions "
                "(id, user_id, transaction_date, payee_id, memo, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (transaction_id, "user-1", "2026-09-01", payee_id, memo, timestamp, timestamp),
            )
        connection.commit()

    upgrade_database(database_path, monkeypatch)

    with sqlite3.connect(database_path) as connection:
        rows = connection.execute("SELECT id, name FROM money_transactions ORDER BY id").fetchall()
        assert rows == [
            ("transaction-1", "Legacy payee"),
            ("transaction-2", "Trimmed memo"),
            ("transaction-3", "Untitled transaction"),
        ]
        name_column = next(
            row
            for row in connection.execute("PRAGMA table_info(money_transactions)")
            if row[1] == "name"
        )
        assert name_column[3] == 1


def test_file_search_migration_requeues_ready_context_and_backfills_metadata(
    tmp_path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "cortex.db"
    upgrade_database(database_path, monkeypatch, "0012_normalize_file_context_timestamps")
    user_id = "00000000-0000-0000-0000-000000000001"
    file_id = "00000000-0000-0000-0000-000000000010"
    source_hash = "a" * 64
    timestamp = "2027-01-01 00:00:00"

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "INSERT INTO users "
            "(id, email, password_hash, is_active, is_owner, created_at, updated_at, "
            "password_changed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, "owner@example.com", "not-used", 1, 1, timestamp, timestamp, timestamp),
        )
        connection.execute(
            "INSERT INTO files "
            "(id, user_id, original_name, storage_key, size_bytes, sha256, created_at, "
            "updated_at, deleted_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                file_id,
                user_id,
                "project-notes.txt",
                "a" * 32 + ".blob",
                4,
                source_hash,
                timestamp,
                timestamp,
                None,
            ),
        )
        connection.execute(
            "INSERT INTO file_context_jobs "
            "(id, user_id, source_sha256, status, attempts, available_at, lease_expires_at, "
            "last_error, extractor_version, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "00000000-0000-0000-0000-000000000020",
                user_id,
                source_hash,
                "ready",
                3,
                timestamp,
                timestamp,
                "old_error",
                "v1",
                timestamp,
                timestamp,
            ),
        )
        connection.commit()

    upgrade_database(database_path, monkeypatch)

    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT status, attempts, lease_expires_at, last_error "
            "FROM file_context_jobs WHERE id = ?",
            ("00000000-0000-0000-0000-000000000020",),
        ).fetchone()[:2] == ("pending", 0)
        assert connection.execute(
            "SELECT lease_expires_at, last_error FROM file_context_jobs WHERE id = ?",
            ("00000000-0000-0000-0000-000000000020",),
        ).fetchone() == (None, None)
        assert connection.execute(
            "SELECT file_id, name, content, tags FROM files_fts"
        ).fetchone() == (file_id, "project-notes.txt", "", "")


def test_file_context_migration_backfills_one_pending_job_per_source_hash(
    tmp_path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "cortex.db"
    upgrade_database(database_path, monkeypatch, "0010_files_foundation")

    user_id = "00000000-0000-0000-0000-000000000001"
    source_hash = "a" * 64
    other_hash = "b" * 64
    with sqlite3.connect(database_path) as connection:
        timestamp = "2027-01-01T00:00:00+00:00"
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
                timestamp,
                timestamp,
                timestamp,
            ),
        )
        for file_id, digest in (
            ("00000000-0000-0000-0000-000000000010", source_hash),
            ("00000000-0000-0000-0000-000000000011", source_hash),
            ("00000000-0000-0000-0000-000000000012", other_hash),
        ):
            connection.execute(
                "INSERT INTO files "
                "(id, user_id, original_name, storage_key, media_type, size_bytes, sha256, "
                "created_at, updated_at, deleted_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    file_id,
                    user_id,
                    "source.txt",
                    f"{file_id.replace('-', '')}.blob",
                    "text/plain",
                    4,
                    digest,
                    timestamp,
                    timestamp,
                    None,
                ),
            )
        connection.commit()

    upgrade_database(database_path, monkeypatch)

    with sqlite3.connect(database_path) as connection:
        jobs = connection.execute(
            "SELECT user_id, source_sha256, status, attempts, extractor_version "
            "FROM file_context_jobs ORDER BY source_sha256"
        ).fetchall()
        assert jobs == [
            (user_id, source_hash, "pending", 0, "v1"),
            (user_id, other_hash, "pending", 0, "v1"),
        ]
        timestamps = connection.execute(
            "SELECT available_at, created_at, updated_at, lease_expires_at FROM file_context_jobs"
        ).fetchall()
        assert all("T" not in value and "+" not in value for row in timestamps for value in row[:3])
        assert all(
            row[3] is None or ("T" not in row[3] and "+" not in row[3]) for row in timestamps
        )
        claim_time = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")
        assert connection.execute(
            "SELECT COUNT(*) FROM file_context_jobs WHERE status = 'pending' AND available_at <= ?",
            (claim_time,),
        ).fetchone() == (2,)
        assert "media_type" not in {
            row[1] for row in connection.execute("PRAGMA table_info(files)")
        }


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
