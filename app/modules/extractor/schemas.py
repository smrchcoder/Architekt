from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.modules.extractor.models.knowledge_model import KnowledgeModel


class KnowledgeModelRead(BaseModel):
    article_id: str
    source_url: str | None
    knowledge_model: KnowledgeModel
    created_at: datetime


class KnowledgeExtractionResponse(BaseModel):
    extraction: KnowledgeModelRead
    message: str = Field(default="extracted")
