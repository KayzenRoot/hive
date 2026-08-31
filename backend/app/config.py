from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    app_name: str = "HIVE API"
    version: str = "0.0.1-bootstrap"
    environment: str = Field(default="development", validation_alias="HIVE_ENVIRONMENT")
    data_root: Path = Field(default=Path(".hive-data"), validation_alias="HIVE_DATA_ROOT")
    projects_root: Path = Field(
        default=Path(".hive-projects"), validation_alias="HIVE_PROJECTS_ROOT"
    )
    postgres_dsn: str = Field(
        default="postgresql://hive:hive@localhost:5432/hive",
        validation_alias="POSTGRES_DSN",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", validation_alias="REDIS_URL")
    cors_origins: str = Field(
        default="http://localhost:3000,http://127.0.0.1:3000",
        validation_alias="CORS_ORIGINS",
    )
    task_max_upload_bytes: int = Field(
        default=10 * 1024 * 1024, validation_alias="HIVE_TASK_MAX_UPLOAD_BYTES"
    )
    task_max_pdf_pages: int = Field(default=100, validation_alias="HIVE_TASK_MAX_PDF_PAGES")
    task_max_extracted_text_bytes: int = Field(
        default=2 * 1024 * 1024, validation_alias="HIVE_TASK_MAX_EXTRACTED_TEXT_BYTES"
    )
    task_max_structured_text_bytes: int = Field(
        default=1 * 1024 * 1024, validation_alias="HIVE_TASK_MAX_STRUCTURED_TEXT_BYTES"
    )
    cas_zstd_level: int = Field(default=3, validation_alias="HIVE_CAS_ZSTD_LEVEL")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def resolved_data_root(self) -> Path:
        return self.data_root.expanduser().resolve()

    @property
    def resolved_projects_root(self) -> Path:
        return self.projects_root.expanduser().resolve()

    def ensure_data_root(self) -> Path:
        root = self.resolved_data_root
        root.mkdir(parents=True, exist_ok=True)
        return root

    def validate_intake_limits(self) -> None:
        if self.task_max_upload_bytes <= 0:
            raise ValueError("HIVE_TASK_MAX_UPLOAD_BYTES must be positive")
        if self.task_max_pdf_pages <= 0:
            raise ValueError("HIVE_TASK_MAX_PDF_PAGES must be positive")
        if self.task_max_extracted_text_bytes <= 0:
            raise ValueError("HIVE_TASK_MAX_EXTRACTED_TEXT_BYTES must be positive")
        if self.task_max_structured_text_bytes <= 0:
            raise ValueError("HIVE_TASK_MAX_STRUCTURED_TEXT_BYTES must be positive")
        if not 1 <= self.cas_zstd_level <= 22:
            raise ValueError("HIVE_CAS_ZSTD_LEVEL must be between 1 and 22")


@lru_cache
def get_settings() -> Settings:
    return Settings()
