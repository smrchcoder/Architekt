from __future__ import annotations

from pydantic import BaseModel, Field, HttpUrl, model_validator


class ArticleCreate(BaseModel):
    source_url: HttpUrl | None = None
    raw_text: str | None = None
    source_title: str | None = None
    source_domain: str | None = None

    @model_validator(mode="after")
    def _exactly_one_input(self) -> "ArticleCreate":
        if bool(self.source_url) == bool(self.raw_text):
            raise ValueError("provide exactly one of source_url or raw_text")
        return self


class ArticleRead(BaseModel):
    unique_id: str
    source_url: str | None
    raw_text: str | None
    cleaned_text: str | None
    word_count: int
    processing_time: int | None
    source_title: str | None
    source_domain: str | None


class ArticleIngestResponse(BaseModel):
    article: ArticleRead
    message: str = Field(default="ingested")
