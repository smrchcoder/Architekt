from __future__ import annotations

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator

from app.core.config import settings


class ArticleCreate(BaseModel):
    source_url: HttpUrl | None = None
    raw_text: str | None = Field(default=None, max_length=settings.max_raw_text_chars)
    source_title: str | None = Field(
        default=None, max_length=settings.max_source_title_chars
    )
    source_domain: str | None = Field(
        default=None, max_length=settings.max_source_domain_chars
    )

    @field_validator("raw_text", mode="before")
    @classmethod
    def _normalize_raw_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            return value
        return value if value.strip() else None

    @field_validator("source_title", "source_domain", mode="before")
    @classmethod
    def _normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def _exactly_one_input(self) -> "ArticleCreate":
        if bool(self.source_url) == bool(self.raw_text):
            raise ValueError("provide exactly one of source_url or raw_text")
        return self
