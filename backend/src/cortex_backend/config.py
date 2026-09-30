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
    file_storage_path: Path = Path("data/files")
    file_max_size_bytes: int = Field(default=25 * 1024 * 1024, gt=0)
    file_processing_enabled: bool = True
    file_processing_poll_seconds: float = Field(default=1.0, gt=0)
    file_processing_lease_seconds: int = Field(default=300, gt=0)
    file_processing_max_attempts: int = Field(default=3, ge=1, le=10)
    file_processing_timeout_seconds: float = Field(default=120.0, gt=0)
    file_converter_command: str = "soffice"
    file_ocr_command: str = "tesseract"
    file_ocr_language: str = Field(default="eng", pattern=r"^[A-Za-z0-9_+.-]{1,64}$")
    embeddings_enabled: bool = False
    embedding_model_cache_path: Path = Path("data/models")
    embedding_batch_size: int = Field(default=16, ge=1, le=128)
    embedding_poll_seconds: float = Field(default=1.0, gt=0)
    embedding_lease_seconds: int = Field(default=300, gt=0)
    embedding_max_attempts: int = Field(default=3, ge=1, le=10)
    installment_charging_enabled: bool = True
    installment_charging_poll_seconds: float = Field(default=60.0, gt=0)
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
