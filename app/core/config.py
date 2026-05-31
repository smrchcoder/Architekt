# from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Mental Model Generator"
    environment: str = "dev"
    database_url: str = "sqlite:///./data/mental_model_generator.db"


settings = Settings()

