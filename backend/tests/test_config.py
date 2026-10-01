"""Configuration behavior tests."""

from pathlib import Path

import pytest

from cortex_backend.config import Settings


def test_settings_load_cortex_environment_variables(monkeypatch) -> None:
    monkeypatch.setenv("CORTEX_APP_NAME", "Configured Cortex")
    monkeypatch.setenv("CORTEX_ENVIRONMENT", "test")
    monkeypatch.setenv("CORTEX_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("CORTEX_DATABASE_PATH", "custom/cortex.db")
    monkeypatch.setenv("CORTEX_FILE_STORAGE_PATH", "custom/files")
    monkeypatch.setenv("CORTEX_FILE_MAX_SIZE_BYTES", "1234")

    settings = Settings(_env_file=None)

    assert settings.app_name == "Configured Cortex"
    assert settings.environment == "test"
    assert settings.log_level == "DEBUG"
    assert settings.database_path == Path("custom/cortex.db")
    assert settings.file_storage_path == Path("custom/files")
    assert settings.file_max_size_bytes == 1234


def test_settings_default_to_local_sqlite_path(monkeypatch) -> None:
    monkeypatch.delenv("CORTEX_DATABASE_PATH", raising=False)

    settings = Settings(_env_file=None)

    assert settings.database_path == Path("data/cortex.db")
    assert settings.file_storage_path == Path("data/files")
    assert settings.file_max_size_bytes == 25 * 1024 * 1024
    assert settings.embeddings_enabled is False
    assert settings.embedding_batch_size == 16
    assert settings.recurring_transaction_posting_enabled is True
    assert settings.recurring_transaction_posting_poll_seconds == 60.0


def test_production_settings_require_setup_secret() -> None:
    with pytest.raises(ValueError, match="CORTEX_SETUP_SECRET"):
        Settings(environment="production", _env_file=None)
