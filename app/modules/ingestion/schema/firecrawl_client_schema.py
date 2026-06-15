from __future__ import annotations

from pydantic import BaseModel, Field


class FirecrawlScrapeRequest(BaseModel):
    url: str = Field(min_length=1)
    formats: list[str] = Field(default_factory=lambda: ["markdown"], min_length=1)


class FirecrawlMediaItem(BaseModel):
    media_type: str = Field(..., description="'image', 'audio', or 'video'")
    url: str = Field(min_length=1)
    alt_text: str | None = None


class FirecrawlScrapeResult(BaseModel):
    url: str = Field(min_length=1)
    markdown: str = Field(min_length=1)
    elapsed_ms: int = Field(ge=0)
    source_title: str | None = None
    source_description: str | None = None
    language: str | None = None
    media_items: list[FirecrawlMediaItem] = Field(default_factory=list)
    extraction_warnings: list[str] = Field(default_factory=list)
