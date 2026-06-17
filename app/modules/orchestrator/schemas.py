from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl, model_validator


RunStatus = Literal["queued", "running", "completed", "failed"]


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
    section_1: dict[str, Any] | None = None
    section_2: dict[str, Any] | None = None
    section_3: dict[str, Any] | None = None
    section_4: dict[str, Any] | None = None
    section_5: dict[str, Any] | None = None
    section_6: dict[str, Any] | None = None
    error_message: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
