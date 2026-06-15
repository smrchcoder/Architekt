from __future__ import annotations

from pydantic import BaseModel, Field

from app.modules.extractor.models.knowledge_model import TradeoffItem


class ReasoningOutput(BaseModel):
    """Pass 3 — Reasoning. Extracts tradeoffs, constraints, and overall warnings."""

    tradeoff_signals: list[TradeoffItem] = Field(
        default_factory=list,
        max_length=8,
        description="Design decisions that involved accepting a cost in exchange for a benefit. Each tradeoff must have both a benefit and a cost. Do not include tradeoffs that are only partially described in the article.",
    )
    constraint_signals: list[str] = Field(
        default_factory=list,
        max_length=5,
        description="Non-negotiable requirements the solution had to satisfy, e.g. latency budgets, consistency guarantees, compliance requirements",
    )
    confidence_score: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Self-assessed quality of this extraction. 1.0 = all fields richly populated, no ambiguity. 0.7 = most fields filled but some signals missing. 0.4 = article is sparse or vague.",
    )
    extraction_warnings: list[str] = Field(
        default_factory=list,
        description="Any issues encountered during extraction: missing sections, tradeoffs with no clear cost or benefit. Used by section generators to decide when to fall back to article snippets.",
    )
