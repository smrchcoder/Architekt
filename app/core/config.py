# from __future__ import annotations

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
    firecrawl_api_key: str | None = None
    firecrawl_formats: str

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
    cors_origins: str | None = None

    # Confidence Gating
    extraction_confidence_threshold: float = 0.75
    extraction_max_retries_per_pass: int = 3


settings = Settings()
