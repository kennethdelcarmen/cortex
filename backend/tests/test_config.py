"""Configuration behavior tests."""

from cortex_backend.config import Settings


def test_settings_load_cortex_environment_variables(monkeypatch) -> None:
    monkeypatch.setenv("CORTEX_APP_NAME", "Configured Cortex")
    monkeypatch.setenv("CORTEX_ENVIRONMENT", "test")
    monkeypatch.setenv("CORTEX_LOG_LEVEL", "DEBUG")

    settings = Settings(_env_file=None)

    assert settings.app_name == "Configured Cortex"
    assert settings.environment == "test"
    assert settings.log_level == "DEBUG"
