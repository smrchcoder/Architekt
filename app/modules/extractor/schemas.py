from __future__ import annotations

from pydantic import BaseModel, Field


class OverviewSection(BaseModel):
    one_line_summary: str = Field(..., max_length=160)
    system_name: str
    company: str
    domain: list[str] = Field(..., min_length=2, max_length=3)
    full_summary: str
    why_it_exists: str
    reading_time_min: int = Field(..., ge=1)
