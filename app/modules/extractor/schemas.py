from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.modules.extractor.models.knowledge_model import KnowledgeModel


class OverviewSection(BaseModel):
    one_line_summary: str = Field(..., max_length=160)
    system_name: str
    company: str
    domain: list[str] = Field(..., min_length=2, max_length=3)
    full_summary: str
    why_it_exists: str
    reading_time_min: int = Field(..., ge=1)


class KnowledgeModelRead(BaseModel):
    article_id: str
    source_url: str | None
    knowledge_model: KnowledgeModel
    created_at: datetime


class KnowledgeExtractionResponse(BaseModel):
    extraction: KnowledgeModelRead
    message: str = Field(default="extracted")


class KnowledgeModelValidationResponse(BaseModel):
    article_id: str
    valid: bool
    errors: list[str] = Field(default_factory=list)


class OverviewSectionResponse(BaseModel):
    article_id: str
    overview: OverviewSection
