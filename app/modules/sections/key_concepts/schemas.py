from __future__ import annotations

from pydantic import BaseModel, Field

from app.modules.extractor.models.knowledge_model import CategoryHint, DifficultyHint


class ConceptEntry(BaseModel):
    id: str = Field(..., description="URL-safe slug, e.g. 'routing-key'")
    name: str = Field(..., description="User-facing label, e.g. 'Routing Key'")
    short_def: str = Field(..., description="Concise definition, 1-2 sentences")
    why_it_matters: str = Field(
        ..., description="Why this concept matters in this specific article's context"
    )
    category: CategoryHint
    difficulty: DifficultyHint
    architecture_node_refs: list[str] = Field(
        default_factory=list,
        description="Architecture node IDs that reference this concept (Section 4 cross-ref)",
    )


class ConceptEnrichment(BaseModel):
    id: str = Field(..., description="Matching slug from the input concept")
    short_def: str = Field(
        ..., description="LLM-enriched definition, 1-2 sentences, grounded in article context"
    )
    why_it_matters: str = Field(
        ...,
        description="LLM-enriched explanation of why this concept matters for this specific system",
    )


class KeyConceptsEnrichment(BaseModel):
    concepts: list[ConceptEnrichment] = Field(
        ..., min_length=2, max_length=8, description="Enriched concepts in the same order as input"
    )


class KeyConceptsSection(BaseModel):
    concepts: list[ConceptEntry] = Field(
        ...,
        min_length=2,
        max_length=8,
        description="Ranked list of load-bearing concepts for this article",
    )
