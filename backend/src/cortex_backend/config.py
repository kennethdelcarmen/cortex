"""Typed environment-backed backend settings."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from ``CORTEX_`` environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="CORTEX_",
        extra="ignore",
    )

    app_name: str = "Cortex Backend"
    environment: Literal["local", "test", "staging", "production"] = "local"
    log_level: str = "INFO"
    service_version: str = "0.1.0"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings instance for the default app."""

    return Settings()
