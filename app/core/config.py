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


settings = Settings()
