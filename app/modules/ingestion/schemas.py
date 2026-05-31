from __future__ import annotations

from pydantic import BaseModel, Field, HttpUrl


class ArticleCreate(BaseModel):
    source_url: HttpUrl | None = None
    raw_text: str | None = None
    source_title: str | None = None
    source_domain: str | None = None


class ArticleRead(BaseModel):
    unique_id: str
    source_url: str | None
    raw_text: str | None
    word_count: int
    processing_time: int | None
    source_title: str | None
    source_domain: str | None


class ArticleIngestResponse(BaseModel):
    article: ArticleRead
    message: str = Field(default="ingested")

