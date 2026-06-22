from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator

from app.core.config import settings


RunStatus = Literal["queued", "running", "completed", "failed"]

SECTION_ORDER: list[str] = [
    "overview",
    "key_concepts",
    "problem_statement",
    "architecture",
    "flow",
    "tradeoffs",
]


class PipelineRunCreate(BaseModel):
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
    def _exactly_one_input(self) -> "PipelineRunCreate":
        if bool(self.source_url) == bool(self.raw_text):
            raise ValueError("provide exactly one of source_url or raw_text")
        return self


class ProcessingRunRead(BaseModel):
    run_id: str
    status: RunStatus
    current_step: str
    progress_percent: int = Field(..., ge=0, le=100)
    article_id: str | None = None
    section_order: list[str] = Field(
        default=SECTION_ORDER,
        description="Ordered list of section keys for UI rendering sequence",
    )
    overview: dict[str, Any] | None = None
    key_concepts: dict[str, Any] | None = None
    problem_statement: dict[str, Any] | None = None
    architecture: dict[str, Any] | None = None
    flow: dict[str, Any] | None = None
    tradeoffs: dict[str, Any] | None = None
    error_message: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
