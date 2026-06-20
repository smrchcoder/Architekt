from __future__ import annotations

from pydantic import BaseModel, Field

from app.modules.extractor.models.knowledge_model import InteractionType


class FlowStep(BaseModel):
    id: str = Field(
        ...,
        description="Stable slug, e.g. 'flow_write_path_step_1'. Used as React keys and for transition edge references.",
    )
    order: int = Field(..., description="1-based step position within the flow")
    actor: str = Field(..., description="Entity performing this step")
    action: str = Field(..., description="What the actor does")
    target: str | None = Field(default=None, description="Entity receiving the action")
    data: str | None = Field(default=None, description="Data or payload involved")
    description: str | None = Field(
        default=None, description="LLM-enriched natural language description of this step"
    )
    interaction_type: InteractionType | None = Field(
        default=None,
        description="Type of interaction: sync_call, async_event, data_flow, config_read, deploys_to, or contains. Inferred from the architecture relationship between actor and target.",
    )
    actor_node_id: str | None = Field(
        default=None,
        description="Architecture node ID (slug) of the actor entity, for direct UI linking to architecture nodes",
    )
    target_node_id: str | None = Field(
        default=None,
        description="Architecture node ID (slug) of the target entity, for direct UI linking to architecture nodes",
    )
    evidence: str | None = Field(
        default=None,
        description="Supporting excerpt from the article for this step. Used for citations and hover explanations.",
    )


class FlowTransition(BaseModel):
    """Explicit directed edge between consecutive flow steps.

    Together with FlowStep.id, this makes the flow a proper graph that can be
    rendered directly as a flow diagram without inferring edges from ordering.
    """

    id: str = Field(
        ...,
        description="Stable slug, e.g. 'flow_write_path_t1'",
    )
    from_step_id: str = Field(
        ..., description="ID of the source step"
    )
    to_step_id: str = Field(
        ..., description="ID of the target step"
    )
    label: str | None = Field(
        default=None,
        description="What triggers the transition to the next step, if described",
    )
    condition: str | None = Field(
        default=None,
        description="Branching condition for this transition, if applicable. Null for sequential flows.",
    )


class FlowWalkthrough(BaseModel):
    id: str = Field(
        ...,
        description="Stable slug preserved from the KnowledgeModel, e.g. 'flow_write_path'",
    )
    flow_name: str = Field(..., description="Name of this flow")
    entry_point: str = Field(
        ...,
        description="What triggers or initiates this flow. Structured field for rendering a trigger node before step 1.",
    )
    exit_point: str = Field(
        ...,
        description="What state or output the flow produces when complete. Structured field for rendering a result node after the last step.",
    )
    overview: str = Field(
        ..., description="2-3 sentence overview of what this flow does and why it matters"
    )
    steps: list[FlowStep] = Field(
        default_factory=list, min_length=1, max_length=15,
        description="Ordered steps with stable IDs, interaction types, and architecture node links",
    )
    transitions: list[FlowTransition] = Field(
        default_factory=list,
        description="Explicit directed edges between consecutive steps. Rendered directly as flow diagram edges.",
    )
    evidence: str | None = Field(
        default=None,
        description="Supporting excerpt from the article for this flow. Used for citations and hover explanations.",
    )


class FlowStepEnrichment(BaseModel):
    """LLM enrichment for a single step — narrative only, no structural fields."""

    order: int = Field(..., description="Step order for matching to deterministic step")
    description: str = Field(
        ..., description="LLM-enriched natural language description of this step"
    )


class FlowWalkthroughEnrichment(BaseModel):
    """LLM enrichment for a single flow — narrative only, no structural fields."""

    flow_name: str = Field(..., description="Flow name for matching to deterministic flow")
    overview: str = Field(
        ..., description="LLM-enriched 2-3 sentence overview"
    )
    steps: list[FlowStepEnrichment] = Field(
        default_factory=list,
        description="Enriched step descriptions, matched by order",
    )


class FlowEnrichment(BaseModel):
    """LLM enrichment response — narrative fields only.

    All structural data (IDs, entry/exit points, interaction types, node links,
    transitions) comes from the deterministic phase. The LLM only produces
    overview and step descriptions.
    """

    flows: list[FlowWalkthroughEnrichment] = Field(
        default_factory=list, min_length=1, max_length=5,
        description="Enriched flow walkthroughs with overviews and step descriptions",
    )


class FlowSection(BaseModel):
    flows: list[FlowWalkthrough] = Field(
        default_factory=list, min_length=1, max_length=5,
        description="End-to-end flow walkthroughs with graph-ready steps and transitions",
    )
