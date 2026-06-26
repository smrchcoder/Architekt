from __future__ import annotations

from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str
    environment: str
    database_url: str
    host: str
    port: int
    backend_api_key: str | None = None
    firecrawl_api_key: str | None = None
    firecrawl_formats: str
    enable_file_logging: bool | None = None
    db_pool_size: int = 5
    db_max_overflow: int = 5
    db_pool_recycle: int = 1800

    # LLM Settings
    llm_provider: str = "openai"
    openai_api_key: str | None = None
    openai_api_base: str | None = None
    gemini_api_key: str | None = None
    llm_model: str = "gpt-4o"
    extraction_model: str = "gpt-4o"
    extraction_model_pass_1: str | None = None
    extraction_model_pass_2: str | None = None
    extraction_model_pass_3: str | None = None
    section_model: str = "gpt-4o-mini"
    cors_origins: list[str] | None = None
    expose_api_docs: bool | None = None
    max_raw_text_chars: int = 120_000
    max_source_title_chars: int = 200
    max_source_domain_chars: int = 255

    # Confidence Gating
    extraction_confidence_threshold: float = 0.75
    extraction_max_retries_per_pass: int = 1

    @field_validator("environment", mode="before")
    @classmethod
    def _normalize_environment(cls, value: Any) -> str:
        if value is None:
            return "development"
        return str(value).strip().lower() or "development"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, value: Any) -> list[str] | None:
        if value is None:
            return None
        if isinstance(value, str):
            origins = [item.strip() for item in value.split(",")]
            return [item for item in origins if item]
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        raise TypeError("cors_origins must be a comma-delimited string or list")

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    @property
    def api_docs_enabled(self) -> bool:
        if self.expose_api_docs is not None:
            return self.expose_api_docs
        return self.is_development

    @property
    def file_logging_enabled(self) -> bool:
        if self.enable_file_logging is not None:
            return self.enable_file_logging
        return self.is_development

    @property
    def normalized_cors_origins(self) -> list[str]:
        return self.cors_origins or []

    def validate_runtime(self) -> None:
        if not self.is_development and not self.backend_api_key:
            raise RuntimeError(
                "BACKEND_API_KEY must be configured outside development"
            )
        if not self.is_development and "*" in self.normalized_cors_origins:
            raise RuntimeError(
                "Wildcard CORS origins are not allowed outside development"
            )


settings = Settings()
