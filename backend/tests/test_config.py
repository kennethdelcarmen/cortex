"""Configuration behavior tests."""

from pathlib import Path

import pytest

from cortex_backend.config import Settings


def test_settings_load_cortex_environment_variables(monkeypatch) -> None:
    monkeypatch.setenv("CORTEX_APP_NAME", "Configured Cortex")
    monkeypatch.setenv("CORTEX_ENVIRONMENT", "test")
    monkeypatch.setenv("CORTEX_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("CORTEX_DATABASE_PATH", "custom/cortex.db")

    settings = Settings(_env_file=None)

    assert settings.app_name == "Configured Cortex"
    assert settings.environment == "test"
    assert settings.log_level == "DEBUG"
    assert settings.database_path == Path("custom/cortex.db")


def test_settings_default_to_local_sqlite_path(monkeypatch) -> None:
    monkeypatch.delenv("CORTEX_DATABASE_PATH", raising=False)

    settings = Settings(_env_file=None)

    assert settings.database_path == Path("data/cortex.db")


def test_production_settings_require_setup_secret() -> None:
    with pytest.raises(ValueError, match="CORTEX_SETUP_SECRET"):
        Settings(environment="production", _env_file=None)
