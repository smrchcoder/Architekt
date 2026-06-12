from __future__ import annotations
from enum import Enum
from pydantic import BaseModel, Field


class EntityType(str, Enum):
    COMPANY = "company"
    INTERNAL_SYSTEM = "internal_system"
    EXTERNAL_TOOL = "external_tool"
    DATA_STORE = "data_store"
    PROTOCOL = "protocol"
    TEAM = "team"
    CONCEPT = "concept"


class InteractionType(str, Enum):
    SYNC_CALL = "sync_call"
    ASYNC_EVENT = "async_event"
    DATA_FLOW = "data_flow"
    CONFIG_READ = "config_read"
    DEPLOYS_TO = "deploys_to"
    CONTAINS = "contains"


class CategoryHint(str, Enum):
    INFRASTRUCTURE = "infrastructure"
    PATTERN = "pattern"
    DATA_MODEL = "data_model"
    PROTOCOL = "protocol"
    TOOL = "tool"
    ALGORITHM = "algorithm"


class DifficultyHint(str, Enum):
    FOUNDATIONAL = "foundational"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class TemporalSignalType(str, Enum):
    PREVIOUS_SYSTEM = "previous_system"
    MIGRATION = "migration"
    EVOLUTION = "evolution"
    MOTIVATION = "motivation"


class NamedEntity(BaseModel):
    name: str = Field(..., description="Exactly as appears in article")
    entity_type: EntityType = Field(..., description="The type of entity")
    is_primary: bool = Field(
        default=False, description="Is this the main system the article is about?"
    )
    first_mention_context: str = Field(
        ..., description="The sentence where this entity first appears"
    )
    aliases: list[str] = Field(
        default_factory=list, description="Alternative names used in the article"
    )


class Relationship(BaseModel):
    source: str = Field(
        ..., description="Name of source entity (must match a NamedEntity.name)"
    )
    target: str = Field(
        ..., description="Name of target entity (must match a NamedEntity.name)"
    )
    interaction_type: InteractionType = Field(..., description="The interaction type")
    label: str = Field(
        ..., description="Human-readable description, e.g. 'sends Objective name'"
    )
    is_bidirectional: bool = Field(default=False)


class FlowStep(BaseModel):
    step_order: int = Field(..., ge=1, description="1-based sequential order")
    actor: str = Field(..., description="Entity name performing this step")
    action: str = Field(..., description="What the actor does")
    data_involved: str | None = Field(
        default=None, description="What data is passed/transformed"
    )
    target: str | None = Field(
        default=None, description="Entity receiving the action (if any)"
    )


class ConceptDef(BaseModel):
    term: str = Field(..., description="The technical term")
    inline_definition: str | None = Field(
        default=None, description="Definition found in article text"
    )
    category_hint: CategoryHint = Field(
        ..., description="Category classification for UI icon selection"
    )
    difficulty_hint: DifficultyHint = Field(
        ..., description="Difficulty rating for readers"
    )
    usage_count: int = Field(
        default=1, ge=1, description="Approximate count of mentions"
    )


class LayerSignal(BaseModel):
    layer_name: str = Field(..., description="e.g. 'Client layer', 'Data plane'")
    entities_in_layer: list[str] = Field(
        ..., description="Names of entities belonging to this layer"
    )
    order_hint: int = Field(
        default=0, description="Suggested rendering order (0 = top)"
    )


class TemporalSignal(BaseModel):
    signal_type: TemporalSignalType = Field(
        ..., description="Type of evolution/temporal event"
    )
    description: str = Field(..., description="The extracted temporal statement")
    before_entity: str | None = Field(
        default=None, description="System being replaced (if applicable)"
    )
    after_entity: str | None = Field(
        default=None, description="System replacing it (if applicable)"
    )


class KnowledgeModel(BaseModel):
    named_entities: list[NamedEntity] = Field(
        default_factory=list,
        min_length=2,
        max_length=20,
        description="Every explicitly named system, service, tool, concept, or company",
    )
    relationships: list[Relationship] = Field(
        default_factory=list,
        min_length=1,
        max_length=30,
        description="Directional relationships stated explicitly in the article",
    )
    problem_signals: list[str] = Field(
        default_factory=list,
        min_length=1,
        max_length=8,
        description="Phrases indicating failure modes, pain points, or constraints",
    )
    constraint_signals: list[str] = Field(
        default_factory=list,
        max_length=5,
        description="Non-negotiable requirements the solution had to satisfy",
    )
    tradeoff_signals: list[str] = Field(
        default_factory=list,
        max_length=8,
        description="Phrases indicating cost/benefit trade-offs or design choices",
    )
    flow_sequences: list[FlowStep] = Field(
        default_factory=list,
        max_length=15,
        description="Ordered steps explicitly describing a sequence of operations or request flow",
    )
    scale_context_signals: list[str] = Field(
        default_factory=list,
        max_length=4,
        description="Phrases/metrics showing scale context (throughput, data size, nodes)",
    )
    concept_definitions: list[ConceptDef] = Field(
        default_factory=list,
        min_length=2,
        max_length=8,
        description="Glossary of load-bearing technical concepts needing definitions",
    )
    layer_signals: list[LayerSignal] = Field(
        default_factory=list,
        max_length=5,
        description="Signals indicating architectural tier/layering",
    )
    temporal_signals: list[TemporalSignal] = Field(
        default_factory=list,
        max_length=6,
        description="How the system evolved over time (before/after, migration)",
    )
    confidence_score: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Self-assessed extraction quality score",
    )
    extraction_warnings: list[str] = Field(
        default_factory=list,
        description="Any warnings generated during the extraction pass",
    )
