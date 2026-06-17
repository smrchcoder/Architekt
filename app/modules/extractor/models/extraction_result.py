from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T", bound=BaseModel)


class ExtractionResult(BaseModel, Generic[T]):
    """Wrapper for per-pass extraction results with confidence metadata."""

    pass_name: str = Field(
        ...,
        description="Name of the extraction pass, e.g. 'recognition', 'structure', 'reasoning'",
    )
    self_reported_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence score self-assessed by the LLM during extraction",
    )
    structural_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Deterministic structural quality score computed after extraction",
    )
    combined_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="min(self_reported_score, structural_score)",
    )
    data: T = Field(
        ...,
        description="The extracted Pydantic model instance for this pass",
    )
    retry_count: int = Field(
        default=0,
        ge=0,
        description="Number of retry attempts performed (0 = first attempt succeeded)",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Warnings generated during this pass (e.g. low field population, retry exhaustion)",
    )
