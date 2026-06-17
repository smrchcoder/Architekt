from __future__ import annotations

from pydantic import BaseModel, Field


class FlowStep(BaseModel):
    order: int = Field(..., description="1-based step position")
    actor: str = Field(..., description="Entity performing this step")
    action: str = Field(..., description="What the actor does")
    target: str | None = Field(default=None, description="Entity receiving the action")
    data: str | None = Field(default=None, description="Data or payload involved")
    description: str | None = Field(
        default=None, description="LLM-enriched natural language description of this step"
    )


class FlowWalkthrough(BaseModel):
    flow_name: str = Field(..., description="Name of this flow")
    overview: str = Field(
        ..., description="2-3 sentence overview of what this flow does and why it matters"
    )
    steps: list[FlowStep] = Field(
        default_factory=list, min_length=1, max_length=15,
        description="Enriched steps with natural language descriptions",
    )


class FlowEnrichment(BaseModel):
    flows: list[FlowWalkthrough] = Field(
        default_factory=list, min_length=1, max_length=5,
        description="Enriched flow walkthroughs with overviews and step descriptions",
    )


class FlowSection(BaseModel):
    flows: list[FlowWalkthrough] = Field(
        default_factory=list, min_length=1, max_length=5,
        description="End-to-end flow walkthroughs from the KnowledgeModel",
    )
