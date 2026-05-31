from __future__ import annotations

from pydantic import BaseModel, Field


class FirecrawlScrapeRequest(BaseModel):
    url: str = Field(min_length=1)
    formats: list[str] = Field(default_factory=lambda: ["markdown"], min_length=1)


class FirecrawlScrapeResult(BaseModel):
    url: str = Field(min_length=1)
    markdown: str = Field(min_length=1)
    elapsed_ms: int = Field(ge=0)
