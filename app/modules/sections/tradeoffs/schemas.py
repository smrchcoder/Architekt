from __future__ import annotations

from pydantic import BaseModel, Field

from app.modules.sections._shared.enums import TradeoffCategory


class TradeoffEntry(BaseModel):
    description: str = Field(..., description="What tradeoff was made")
    benefit: str = Field(..., description="What was gained")
    cost: str = Field(..., description="What was given up or made harder")
    condition: str | None = Field(
        default=None, description="When this tradeoff holds vs breaks down"
    )
    category: TradeoffCategory | None = Field(
        default=None,
        description="Category classification: performance, consistency, cost, complexity, reliability, security, or other",
    )
    insight: str | None = Field(
        default=None, description="LLM-enriched insight: what the reader should learn from this tradeoff"
    )
    evidence: str | None = Field(
        default=None,
        description="Verbatim or near-verbatim excerpt from the article supporting this tradeoff. Used for citations and hover explanations in the UI.",
    )
    affected_entities: list[str] = Field(
        default_factory=list,
        description="Entity names from the architecture section that are involved in this tradeoff. Used for cross-section linking in the UI (e.g. highlighting affected nodes when a tradeoff is selected).",
    )
    affected_entity_ids: list[str] = Field(
        default_factory=list,
        description="Architecture node IDs (slugs) affected by this tradeoff. Used for deterministic cross-section visual linking — the UI can highlight nodes by slug without name matching.",
    )


class ConstraintEntry(BaseModel):
    description: str = Field(..., description="What the constraint is")
    impact: str | None = Field(
        default=None, description="LLM-enriched explanation of how this constraint shaped the design"
    )
    evidence: str | None = Field(
        default=None,
        description="Verbatim or near-verbatim excerpt from the article supporting this constraint. Used for citations and hover explanations.",
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
