from __future__ import annotations

from pydantic import BaseModel, Field


class TradeoffEntry(BaseModel):
    description: str = Field(..., description="What tradeoff was made")
    benefit: str = Field(..., description="What was gained")
    cost: str = Field(..., description="What was given up or made harder")
    condition: str | None = Field(
        default=None, description="When this tradeoff holds vs breaks down"
    )
    category: str | None = Field(
        default=None,
        description="performance, consistency, cost, complexity, reliability, security, or other",
    )
    insight: str | None = Field(
        default=None, description="LLM-enriched insight: what the reader should learn from this tradeoff"
    )


class ConstraintEntry(BaseModel):
    description: str = Field(..., description="What the constraint is")
    impact: str | None = Field(
        default=None, description="LLM-enriched explanation of how this constraint shaped the design"
    )


class TradeoffsEnrichment(BaseModel):
    takeaways: str = Field(
        ...,
        description="1-2 paragraph synthesis of the key engineering lessons from all tradeoffs and constraints",
    )
    tradeoffs: list[TradeoffEntry] = Field(
        default_factory=list, max_length=8,
        description="Enriched tradeoffs with insight and categorization",
    )
    constraints: list[ConstraintEntry] = Field(
        default_factory=list, max_length=5,
        description="Enriched constraints with impact explanations",
    )


class TradeoffsSection(BaseModel):
    tradeoffs: list[TradeoffEntry] = Field(
        default_factory=list, max_length=8,
        description="Design tradeoffs with benefits, costs, and insights",
    )
    constraints: list[ConstraintEntry] = Field(
        default_factory=list, max_length=5,
        description="Non-negotiable constraints that shaped the design",
    )
    takeaways: str = Field(
        ...,
        description="1-2 paragraph synthesis of key learnings for the reader",
    )
