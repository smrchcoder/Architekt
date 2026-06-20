from __future__ import annotations
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


# ── Enums ──────────────────────────────────────────────────────────────────────


class EntityType(str, Enum):
    COMPANY = "company"
    PRODUCT = "product"
    INTERNAL_SYSTEM = "internal_system"
    EXTERNAL_TOOL = "external_tool"
    VENDOR_TOOL = "vendor_tool"
    FRAMEWORK = "framework"
    DATA_STORE = "data_store"
    PROTOCOL = "protocol"
    TEAM = "team"
    CONCEPT = "concept"


class ArchitectureRole(str, Enum):
    SERVICE = "service"
    DATASTORE = "datastore"
    QUEUE = "queue"
    WORKER = "worker"
    SCHEDULER = "scheduler"
    API = "api"
    CLIENT = "client"
    BATCH_JOB = "batch_job"
    STREAM_PROCESSOR = "stream_processor"
    INFRASTRUCTURE_COMPONENT = "infrastructure_component"
    GATEWAY = "gateway"
    CACHE = "cache"
    ORCHESTRATOR = "orchestrator"
    PROXY = "proxy"
    AGENT = "agent"


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


class ConceptKind(str, Enum):
    DOMAIN_ABSTRACTION = "domain_abstraction"
    ARCHITECTURAL_CONCERN = "architectural_concern"
    DESIGN_PATTERN = "design_pattern"
    IMPLEMENTATION_DETAIL = "implementation_detail"


class TemporalSignalType(str, Enum):
    PREVIOUS_SYSTEM = "previous_system"
    MIGRATION = "migration"
    EVOLUTION = "evolution"
    MOTIVATION = "motivation"


class SectionRelevance(str, Enum):
    OVERVIEW = "overview"
    PROBLEM = "problem"
    CONCEPTS = "concepts"
    ARCHITECTURE = "architecture"
    FLOW = "flow"
    TRADEOFFS = "tradeoffs"


# ── Pass 1 sub-models — Recognition ────────────────────────────────────────────


class NamedEntity(BaseModel):
    id: str = Field(
        ...,
        description="Stable machine identifier for visual systems. Pattern: 'ent_{slugified_name}' e.g. 'ent_apache_cassandra'. Must be deterministic from the entity name.",
    )
    name: str = Field(
        ...,
        description="Canonical name of the entity. If the article uses multiple names for the same thing, pick the most precise one and list alternatives in aliases.",
    )
    entity_type: EntityType = Field(
        ...,
        description="Classification of what kind of entity this is",
    )
    architecture_role: ArchitectureRole | None = Field(
        default=None,
        description="The architectural role this entity plays — service, datastore, queue, worker, scheduler, api, client, batch_job, stream_processor, infrastructure_component, gateway, cache, orchestrator, proxy, or agent. Set to null if the role is not discernible.",
    )
    importance: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Relative importance of this entity in the architecture on a scale of 1 (minor) to 10 (central). Based on: centrality in relationships, frequency of mentions, role in the architecture, and participation across flows.",
    )
    description: str = Field(
        ...,
        description="One sentence describing what this entity does within the context of this article",
    )
    is_primary: bool = Field(
        default=False,
        description="True only for the main system or subject the article is about. At most one entity should be primary.",
    )
    first_mention_context: str = Field(
        ...,
        description="The verbatim sentence where this entity first appears in the article",
    )
    aliases: list[str] = Field(
        default_factory=list,
        description="Alternative names or abbreviations used for this entity elsewhere in the article. Consolidate all references to the same thing here.",
    )
    evidence: str | None = Field(
        default=None,
        description="A supporting excerpt from the article that establishes or justifies this entity's existence and role. Used for citations, source highlighting, and hover explanations in the UI.",
    )


class ConceptDef(BaseModel):
    id: str = Field(
        ...,
        description="Stable machine identifier for visual systems. Pattern: 'con_{slugified_term}' e.g. 'con_eventual_consistency'. Must be deterministic from the term.",
    )
    term: str = Field(
        ...,
        description="The technical term exactly as used in the article",
    )
    inline_definition: str = Field(
        ...,
        description="Definition of the term as used in this article. If the article does not define it explicitly, infer the definition from usage context. Never leave blank.",
    )
    category_hint: CategoryHint = Field(
        ...,
        description="Category classification used for UI icon and grouping decisions downstream",
    )
    difficulty_hint: DifficultyHint = Field(
        ...,
        description="Estimated difficulty level for a reader encountering this term",
    )
    concept_kind: ConceptKind = Field(
        default=ConceptKind.DOMAIN_ABSTRACTION,
        description="Whether this concept is a domain abstraction, architectural concern, design pattern, or implementation detail",
    )
    usage_count: int = Field(
        default=1,
        ge=1,
        description="Approximate number of times this term appears or is referenced in the article",
    )
    evidence: str | None = Field(
        default=None,
        description="A supporting excerpt from the article that demonstrates this concept in use. Used for citations and hover explanations in the UI.",
    )


class QuoteSignal(BaseModel):
    text: str = Field(
        ...,
        description="Verbatim sentence or short passage from the article that expresses something precisely and would be lost in paraphrase",
    )
    section_relevance: list[SectionRelevance] = Field(
        ...,
        min_length=1,
        description="Which output sections this quote would most strengthen",
    )


# ── Pass 2 sub-models — Structure ──────────────────────────────────────────────


class Relationship(BaseModel):
    id: str = Field(
        ...,
        description="Stable machine identifier for visual systems. Pattern: 'rel_{source}_{target}' e.g. 'rel_cassandra_kafka'. Must be deterministic from source and target names.",
    )
    source: str = Field(
        ...,
        description="Name of the source entity. Must exactly match a NamedEntity.name from Pass 1.",
    )
    target: str = Field(
        ...,
        description="Name of the target entity. Must exactly match a NamedEntity.name from Pass 1.",
    )
    interaction_type: InteractionType = Field(
        ...,
        description="The nature of the interaction between source and target",
    )
    label: str = Field(
        ...,
        description="Human-readable description of what crosses this relationship, e.g. 'sends task payload', 'reads config on startup'",
    )
    is_bidirectional: bool = Field(
        default=False,
        description="True if the interaction flows in both directions with equal significance",
    )


class FlowStep(BaseModel):
    step_order: int = Field(
        ...,
        ge=1,
        description="1-based position of this step within its parent flow sequence",
    )
    actor: str = Field(
        ...,
        description="Name of the entity performing this step. Should match a NamedEntity.name where possible.",
    )
    action: str = Field(
        ...,
        description="What the actor does in this step, written as an active verb phrase",
    )
    data_involved: str | None = Field(
        default=None,
        description="The data, message, or payload being passed or transformed in this step, if any",
    )
    target: str | None = Field(
        default=None,
        description="The entity receiving the action in this step, if any. Should match a NamedEntity.name where possible.",
    )


class FlowSequence(BaseModel):
    id: str = Field(
        ...,
        description="Stable machine identifier for visual systems. Pattern: 'flow_{slugified_flow_name}' e.g. 'flow_write_path'. Must be deterministic from the flow name.",
    )
    flow_name: str = Field(
        ...,
        description="Short descriptive name for this flow, e.g. 'Write path', 'Auth handshake', 'Failure recovery'",
    )
    entry_point: str = Field(
        ...,
        description="What triggers or initiates this flow",
    )
    exit_point: str = Field(
        ...,
        description="What state or output the flow produces when complete",
    )
    steps: list[FlowStep] = Field(
        ...,
        min_length=1,
        max_length=15,
        description="Ordered steps of this flow. Each flow is self-contained — do not mix steps from different flows.",
    )


class LayerSignal(BaseModel):
    layer_name: str = Field(
        ...,
        description="Name of the architectural tier, e.g. 'Client layer', 'Data plane', 'Orchestration layer'",
    )
    entities_in_layer: list[str] = Field(
        ...,
        description="Names of entities belonging to this layer. Each name must match a NamedEntity.name from Pass 1.",
    )
    order_hint: int = Field(
        default=0,
        description="Suggested top-to-bottom rendering order for this layer. 0 = topmost layer.",
    )


class TemporalSignal(BaseModel):
    signal_type: TemporalSignalType = Field(
        ...,
        description="Whether this signal describes a previous system, a migration event, a system evolution, or a historical motivation",
    )
    description: str = Field(
        ...,
        description="The extracted statement about how the system changed or why it was built",
    )
    before_entity: str | None = Field(
        default=None,
        description="The system or approach that existed before, if applicable",
    )
    after_entity: str | None = Field(
        default=None,
        description="The system or approach that replaced it, if applicable",
    )


# ── Pass 3 sub-models — Reasoning ──────────────────────────────────────────────


class TradeoffItem(BaseModel):
    id: str = Field(
        ...,
        description="Stable machine identifier for visual systems. Pattern: 'trade_{slugified_description_short}' e.g. 'trade_eventual_consistency'. Must be deterministic from the description.",
    )
    description: str = Field(
        ...,
        description="The tradeoff as stated or implied in the article. One sentence capturing the tension.",
    )
    benefit: str = Field(
        ...,
        description="What was gained by accepting this tradeoff",
    )
    cost: str = Field(
        ...,
        description="What was given up, made harder, or made more complex as a result",
    )
    condition: str | None = Field(
        default=None,
        description="The condition or scale threshold under which this tradeoff holds or breaks down, if mentioned",
    )
    evidence: str | None = Field(
        default=None,
        description="A supporting excerpt from the article that describes this tradeoff. Used for citations, source highlighting, and hover explanations in the UI.",
    )


# ── Root model ─────────────────────────────────────────────────────────────────


class KnowledgeModel(BaseModel):

    schema_version: Literal[3] = 3

    # -- Pass 1 fields -----------------------------------------------------------

    article_summary: str = Field(
        ...,
        description="2 to 3 sentence synthesis of what the article argues or explains. Written in plain language. Not a list of topics — a compressed argument.",
    )
    core_problem: str = Field(
        ...,
        description="Single sentence stating the central problem or challenge the article addresses. This is the 'why does this article exist' statement.",
    )
    named_entities: list[NamedEntity] = Field(
        default_factory=list,
        min_length=2,
        max_length=20,
        description="Canonicalized list of every explicitly named system, service, tool, protocol, company, or team. No duplicate entities — each entity appears exactly once with its canonical name and alternative names stored in aliases. Each entity has a stable ID, architecture role, importance score, and supporting evidence.",
    )
    concept_definitions: list[ConceptDef] = Field(
        default_factory=list,
        min_length=2,
        max_length=12,
        description="Load-bearing technical concepts a reader needs to understand to follow the article. Each concept has a stable ID and supporting evidence. Exclude concepts that are merely mentioned in passing.",
    )
    key_quotes: list[QuoteSignal] = Field(
        default_factory=list,
        max_length=6,
        description="Verbatim sentences from the article that express something precisely and would lose meaning if paraphrased. Prioritize quotes about the problem and tradeoffs.",
    )
    problem_signals: list[str] = Field(
        default_factory=list,
        min_length=1,
        max_length=8,
        description="Phrases or sentences from the article indicating failure modes, pain points, or motivating constraints. Extracted verbatim or near-verbatim.",
    )
    scale_context_signals: list[str] = Field(
        default_factory=list,
        max_length=4,
        description="Phrases or metrics from the article that establish the scale context, e.g. throughput numbers, data volumes, node counts, user counts",
    )

    # -- Pass 2 fields -----------------------------------------------------------

    relationships: list[Relationship] = Field(
        default_factory=list,
        min_length=1,
        max_length=30,
        description="Structured, graph-ready edges between named entities. Each relationship has a stable ID, explicit source and target (matching NamedEntity names), interaction type, and a concise label. These are directly renderable as React Flow edges without further parsing.",
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

    # -- Pass 3 fields -----------------------------------------------------------

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
        description="Self-assessed quality of this extraction. Score below 0.6 indicates the article was ambiguous, too short, or too opinionated to extract reliable structure. Set after all three passes are complete.",
    )
    extraction_warnings: list[str] = Field(
        default_factory=list,
        description="Any issues encountered during extraction: missing sections, ambiguous entity names, flows that could not be ordered, tradeoffs with no clear cost or benefit. Metadata for diagnostics — not currently consumed by section builders.",
    )
