from __future__ import annotations

from pydantic import BaseModel, Field

from app.modules.extractor.models.knowledge_model import (
    FlowSequence,
    LayerSignal,
    Relationship,
    TemporalSignal,
)


class StructureOutput(BaseModel):
    """Pass 2 — Structure. Extracts relationships, flows, layers, and temporal signals."""

    relationships: list[Relationship] = Field(
        default_factory=list,
        min_length=1,
        max_length=30,
        description="Directional relationships between named entities that are explicitly stated or clearly implied by the article. Source and target must match NamedEntity names.",
    )
    flow_sequences: list[FlowSequence] = Field(
        default_factory=list,
        max_length=5,
        description="Named operational flows described in the article. Each flow is self-contained with its own ordered steps. Use separate FlowSequence objects for distinct paths such as write path, read path, and failure path.",
    )
    layer_signals: list[LayerSignal] = Field(
        default_factory=list,
        max_length=5,
        description="Signals indicating how entities are grouped into architectural tiers or layers. Used to inform diagram layout downstream.",
    )
    temporal_signals: list[TemporalSignal] = Field(
        default_factory=list,
        max_length=6,
        description="Statements about how the system evolved over time, what it replaced, or what motivated its creation",
    )
    confidence_score: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Self-assessed quality of this extraction. 1.0 = all fields richly populated, no ambiguity. 0.7 = most fields filled but some signals missing. 0.4 = article is sparse or vague.",
    )
