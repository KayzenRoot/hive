import math
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
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
    repository_max_files: int = Field(default=10_000, validation_alias="HIVE_REPOSITORY_MAX_FILES")
    repository_max_file_bytes: int = Field(
        default=10 * 1024 * 1024, validation_alias="HIVE_REPOSITORY_MAX_FILE_BYTES"
    )
    repository_max_total_bytes: int = Field(
        default=100 * 1024 * 1024, validation_alias="HIVE_REPOSITORY_MAX_TOTAL_BYTES"
    )
    embedding_enabled: bool = Field(default=False, validation_alias="HIVE_EMBEDDING_ENABLED")
    embedding_base_url: str | None = Field(default=None, validation_alias="HIVE_EMBEDDING_BASE_URL")
    embedding_model: str | None = Field(default=None, validation_alias="HIVE_EMBEDDING_MODEL")
    embedding_model_revision: str | None = Field(
        default=None, validation_alias="HIVE_EMBEDDING_MODEL_REVISION"
    )
    embedding_dimensions: int | None = Field(
        default=None, validation_alias="HIVE_EMBEDDING_DIMENSIONS"
    )
    embedding_api_key: SecretStr | None = Field(
        default=None, validation_alias="HIVE_EMBEDDING_API_KEY"
    )
    embedding_timeout_seconds: float = Field(
        default=10.0, validation_alias="HIVE_EMBEDDING_TIMEOUT_SECONDS"
    )
    embedding_batch_size: int = Field(default=16, validation_alias="HIVE_EMBEDDING_BATCH_SIZE")
    embedding_max_input_chars: int = Field(
        default=6000, validation_alias="HIVE_EMBEDDING_MAX_INPUT_CHARS"
    )
    embedding_max_dimensions: int = Field(
        default=2000, validation_alias="HIVE_EMBEDDING_MAX_DIMENSIONS"
    )
    embedding_candidate_pool: int = Field(
        default=20, validation_alias="HIVE_EMBEDDING_CANDIDATE_POOL"
    )
    embedding_rrf_k: int = Field(default=60, validation_alias="HIVE_EMBEDDING_RRF_K")
    embedding_lexical_weight: float = Field(
        default=1.0, validation_alias="HIVE_EMBEDDING_LEXICAL_WEIGHT"
    )
    embedding_semantic_weight: float = Field(
        default=1.0, validation_alias="HIVE_EMBEDDING_SEMANTIC_WEIGHT"
    )
    rerank_enabled: bool = Field(default=False, validation_alias="HIVE_RERANK_ENABLED")
    rerank_base_url: str | None = Field(default=None, validation_alias="HIVE_RERANK_BASE_URL")
    rerank_model: str | None = Field(default=None, validation_alias="HIVE_RERANK_MODEL")
    rerank_model_revision: str | None = Field(
        default=None, validation_alias="HIVE_RERANK_MODEL_REVISION"
    )
    rerank_api_key: SecretStr | None = Field(default=None, validation_alias="HIVE_RERANK_API_KEY")
    rerank_timeout_seconds: float = Field(
        default=10.0, validation_alias="HIVE_RERANK_TIMEOUT_SECONDS"
    )
    rerank_candidate_pool: int = Field(default=20, validation_alias="HIVE_RERANK_CANDIDATE_POOL")
    rerank_max_document_chars: int = Field(
        default=6000, validation_alias="HIVE_RERANK_MAX_DOCUMENT_CHARS"
    )
    rerank_max_query_chars: int = Field(default=512, validation_alias="HIVE_RERANK_MAX_QUERY_CHARS")
    rerank_max_response_bytes: int = Field(
        default=2_000_000, validation_alias="HIVE_RERANK_MAX_RESPONSE_BYTES"
    )

    @field_validator("embedding_dimensions", mode="before")
    @classmethod
    def empty_embedding_dimensions_are_unset(cls, value: object) -> object:
        return None if isinstance(value, str) and not value.strip() else value

    @field_validator("embedding_api_key", mode="before")
    @classmethod
    def empty_embedding_api_key_is_unset(cls, value: object) -> object:
        return None if isinstance(value, str) and not value.strip() else value

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

    def validate_repository_limits(self) -> None:
        if self.repository_max_files <= 0:
            raise ValueError("HIVE_REPOSITORY_MAX_FILES must be positive")
        if self.repository_max_file_bytes <= 0:
            raise ValueError("HIVE_REPOSITORY_MAX_FILE_BYTES must be positive")
        if self.repository_max_total_bytes <= 0:
            raise ValueError("HIVE_REPOSITORY_MAX_TOTAL_BYTES must be positive")
        if self.repository_max_total_bytes < self.repository_max_file_bytes:
            raise ValueError(
                "HIVE_REPOSITORY_MAX_TOTAL_BYTES must be at least HIVE_REPOSITORY_MAX_FILE_BYTES"
            )

    def validate_embedding_limits(self) -> None:
        if self.embedding_timeout_seconds <= 0 or self.embedding_timeout_seconds > 120:
            raise ValueError("HIVE_EMBEDDING_TIMEOUT_SECONDS must be between 0 and 120")
        if not 1 <= self.embedding_batch_size <= 128:
            raise ValueError("HIVE_EMBEDDING_BATCH_SIZE must be between 1 and 128")
        if not 1 <= self.embedding_max_input_chars <= 100_000:
            raise ValueError("HIVE_EMBEDDING_MAX_INPUT_CHARS must be between 1 and 100000")
        if not 1 <= self.embedding_max_dimensions <= 2000:
            raise ValueError("HIVE_EMBEDDING_MAX_DIMENSIONS must be between 1 and 2000")
        if not 1 <= self.embedding_candidate_pool <= 100:
            raise ValueError("HIVE_EMBEDDING_CANDIDATE_POOL must be between 1 and 100")
        if not 1 <= self.embedding_rrf_k <= 10_000:
            raise ValueError("HIVE_EMBEDDING_RRF_K must be between 1 and 10000")
        if self.embedding_lexical_weight < 0 or self.embedding_semantic_weight < 0:
            raise ValueError("embedding fusion weights must not be negative")
        if self.embedding_base_url and not self.embedding_base_url.strip():
            raise ValueError("HIVE_EMBEDDING_BASE_URL must not be blank")
        if self.embedding_enabled:
            if not self.embedding_base_url or not self.embedding_base_url.strip():
                raise ValueError("HIVE_EMBEDDING_BASE_URL is required when embeddings are enabled")
            if not self.embedding_model or not self.embedding_model.strip():
                raise ValueError("HIVE_EMBEDDING_MODEL is required when embeddings are enabled")
            if self.embedding_dimensions is None:
                raise ValueError(
                    "HIVE_EMBEDDING_DIMENSIONS is required when embeddings are enabled"
                )
        if self.embedding_dimensions is not None and not (
            1 <= self.embedding_dimensions <= self.embedding_max_dimensions
        ):
            raise ValueError(
                "HIVE_EMBEDDING_DIMENSIONS must be between 1 and HIVE_EMBEDDING_MAX_DIMENSIONS"
            )

    def validate_rerank_limits(self) -> None:
        if (
            not math.isfinite(self.rerank_timeout_seconds)
            or self.rerank_timeout_seconds <= 0
            or self.rerank_timeout_seconds > 120
        ):
            raise ValueError("HIVE_RERANK_TIMEOUT_SECONDS must be between 0 and 120")
        if not 1 <= self.rerank_candidate_pool <= 100:
            raise ValueError("HIVE_RERANK_CANDIDATE_POOL must be between 1 and 100")
        if not 1 <= self.rerank_max_document_chars <= 100_000:
            raise ValueError("HIVE_RERANK_MAX_DOCUMENT_CHARS must be between 1 and 100000")
        if not 1 <= self.rerank_max_query_chars <= 512:
            raise ValueError("HIVE_RERANK_MAX_QUERY_CHARS must be between 1 and 512")
        if not 1 <= self.rerank_max_response_bytes <= 2_000_000:
            raise ValueError("HIVE_RERANK_MAX_RESPONSE_BYTES must be between 1 and 2000000")
        if self.rerank_base_url is not None and not self.rerank_base_url.strip():
            raise ValueError("HIVE_RERANK_BASE_URL must not be blank")
        if self.rerank_enabled:
            if not self.rerank_base_url or not self.rerank_base_url.strip():
                raise ValueError("HIVE_RERANK_BASE_URL is required when reranking is enabled")
            if not self.rerank_model or not self.rerank_model.strip():
                raise ValueError("HIVE_RERANK_MODEL is required when reranking is enabled")


@lru_cache
def get_settings() -> Settings:
    return Settings()
