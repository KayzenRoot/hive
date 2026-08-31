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
    )

    app_name: str = "HIVE API"
    version: str = "0.0.1-bootstrap"
    environment: str = Field(default="development", validation_alias="HIVE_ENVIRONMENT")
    data_root: Path = Field(default=Path(".hive-data"), validation_alias="HIVE_DATA_ROOT")
    postgres_dsn: str = Field(
        default="postgresql://hive:hive@localhost:5432/hive",
        validation_alias="POSTGRES_DSN",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", validation_alias="REDIS_URL")
    cors_origins: str = Field(
        default="http://localhost:3000,http://127.0.0.1:3000",
        validation_alias="CORS_ORIGINS",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def resolved_data_root(self) -> Path:
        return self.data_root.expanduser().resolve()

    def ensure_data_root(self) -> Path:
        root = self.resolved_data_root
        root.mkdir(parents=True, exist_ok=True)
        return root


@lru_cache
def get_settings() -> Settings:
    return Settings()
