from __future__ import annotations

from pydantic import BaseModel, Field

from app.modules.extractor.models.knowledge_model import (
    ArchitectureRole,
    EntityType,
    InteractionType,
)


class ArchitectureEdge(BaseModel):
    id: str = Field(..., description="Deterministic slug, e.g. 'rel_cassandra_kafka'")
    source_id: str = Field(..., description="Slug of the source architecture node")
    target_id: str = Field(..., description="Slug of the target architecture node")
    interaction_type: InteractionType = Field(
        ...,
        description="Type of interaction: sync_call, async_event, data_flow, config_read, deploys_to, or contains",
    )
    label: str = Field(..., description="Human-readable description of what crosses this edge")
    is_bidirectional: bool = Field(default=False, description="True if interaction flows both ways")
    evidence: str | None = Field(
        default=None,
        description="Supporting excerpt from the article for this relationship. Used for citations and hover explanations.",
    )


class ArchitectureNode(BaseModel):
    id: str = Field(..., description="URL-safe slug, e.g. 'ai-gateway'")
    name: str = Field(..., description="Entity name as it appears in the article")
    entity_type: EntityType = Field(
        ...,
        description="Classification: company, product, internal_system, external_tool, vendor_tool, framework, data_store, protocol, team, or concept",
    )
    description: str = Field(..., description="1-2 sentence description of this node's role")
    layer: str | None = Field(
        default=None,
        description="Architectural layer this node belongs to. Must match an ArchitectureLayer.name.",
    )
    is_primary: bool = Field(default=False)
    connected_to: list[str] = Field(default_factory=list, description="Node IDs this node is connected to")
    architecture_role: ArchitectureRole | None = Field(
        default=None,
        description="Technical role: service, datastore, queue, worker, scheduler, api, client, batch_job, stream_processor, infrastructure_component, gateway, cache, orchestrator, proxy, or agent",
    )
    importance: int = Field(
        default=5, ge=1, le=10,
        description="Relative importance 1-10. Based on relationship centrality, mention frequency, and flow participation.",
    )
    parent_id: str | None = Field(
        default=None,
        description="Slug of the parent node for system hierarchy / containment boundaries. Populated from relationships with interaction_type 'contains'.",
    )
    evidence: str | None = Field(
        default=None,
        description="Supporting excerpt from the article for citations and hover explanations",
    )


class ArchitectureLayer(BaseModel):
    name: str = Field(..., description="Layer name, e.g. 'Platform layer'")
    order: int = Field(..., description="Top-to-bottom rendering order, 0 = topmost")
    description: str | None = Field(default=None, description="Brief description of this layer's responsibility")


class ArchitectureEnrichment(BaseModel):
    overview_narrative: str = Field(
        ...,
        description="2-3 paragraph narrative describing the architecture: what major components exist, how they are organized, and the key architectural patterns",
    )
    layers: list[ArchitectureLayer] = Field(
        default_factory=list, max_length=5,
        description="Architectural layers with descriptions",
    )


class ArchitectureSection(BaseModel):
    overview_narrative: str = Field(
        ...,
        description="2-3 paragraph narrative describing the architecture at a high level",
    )
    nodes: list[ArchitectureNode] = Field(
        default_factory=list, min_length=2, max_length=40,
        description="All architectural nodes extracted from the KnowledgeModel",
    )
    edges: list[ArchitectureEdge] = Field(
        default_factory=list,
        description="Graph-ready directed edges between architecture nodes. Rendered directly as React Flow edges without further parsing.",
    )
    layers: list[ArchitectureLayer] = Field(
        default_factory=list, max_length=5,
        description="Architectural layers with their nodes and rendering order",
    )
    key_relationships: list[str] = Field(
        default_factory=list, max_length=10,
        description="Top 10 most significant relationships, as human-readable labels",
    )
