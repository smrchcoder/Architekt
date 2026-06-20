from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl, model_validator


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
    raw_text: str | None = None
    source_title: str | None = None
    source_domain: str | None = None

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
