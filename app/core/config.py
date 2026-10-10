"""Application configuration via pydantic-settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All settings are read from environment variables or .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Upload limits
    max_upload_mb: int = 50

    # Storage paths
    upload_dir: str = "storage/uploads"
    extract_dir: str = "storage/extracted"

    # Database
    database_url: str = "sqlite:///./geospatial.db"

    # Logging
    log_level: str = "INFO"

    @property
    def max_upload_bytes(self) -> int:
        """Return max upload size in bytes."""
        return self.max_upload_mb * 1024 * 1024


settings = Settings()
