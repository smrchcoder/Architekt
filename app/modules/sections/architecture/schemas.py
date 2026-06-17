from __future__ import annotations

from pydantic import BaseModel, Field


class ArchitectureNode(BaseModel):
    id: str = Field(..., description="URL-safe slug, e.g. 'ai-gateway'")
    name: str = Field(..., description="Entity name as it appears in the article")
    entity_type: str = Field(..., description="company, product, internal_system, external_tool, vendor_tool, framework, data_store, protocol, team")
    description: str = Field(..., description="1-2 sentence description of this node's role")
    layer: str | None = Field(default=None, description="Architectural layer this node belongs to")
    is_primary: bool = Field(default=False)
    connected_to: list[str] = Field(default_factory=list, description="Node IDs this node is connected to")


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
    layers: list[ArchitectureLayer] = Field(
        default_factory=list, max_length=5,
        description="Architectural layers with their nodes and rendering order",
    )
    key_relationships: list[str] = Field(
        default_factory=list, max_length=10,
        description="Top 10 most significant relationships, as human-readable labels",
    )
