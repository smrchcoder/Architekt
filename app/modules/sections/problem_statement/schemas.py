from __future__ import annotations

from pydantic import BaseModel, Field


class ProblemSection(BaseModel):
    headline: str = Field(
        ..., description="Punchy past-tense problem headline derived from strongest problem signal"
    )
    context: str = Field(
        ..., description="Pre-solution state combining temporal signals and scale pressure"
    )
    pain_points: list[str] = Field(
        ...,
        min_length=1,
        description="Standalone sentences describing each pain point, ordered by severity",
    )
    constraints: list[str] = Field(
        default_factory=list,
        description="Non-negotiable requirements framed as 'the solution had to...' statements",
    )
    scale_context: str | None = Field(
        default=None, description="Most impactful quantitative scale signal"
    )
    prior_approach: str | None = Field(
        default=None, description="Previous system or approach that was replaced"
    )
