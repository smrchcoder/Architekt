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
    llm_provider: str = "openai"  # "openai", "gemini", etc.
    openai_api_key: str | None = None
    openai_api_base: str | None = (
        None  # to support custom endpoints (Ollama, OpenRouter, etc.)
    )
    gemini_api_key: str | None = None
    llm_model: str = "gpt-4o"


settings = Settings()
