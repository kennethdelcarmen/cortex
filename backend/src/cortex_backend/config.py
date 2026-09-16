"""Typed environment-backed backend settings."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
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
    database_path: Path = Path("data/cortex.db")
    setup_secret: SecretStr | None = None
    cors_origins: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_production_setup_secret(self) -> "Settings":
        """Refuse a production configuration that cannot bootstrap its owner."""

        if self.environment == "production" and self.setup_secret is None:
            raise ValueError("CORTEX_SETUP_SECRET is required in production.")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings instance for the default app."""

    return Settings()
