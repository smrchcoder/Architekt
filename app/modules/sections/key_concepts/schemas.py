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


class KeyConceptsSection(BaseModel):
    concepts: list[ConceptEntry] = Field(
        ...,
        min_length=2,
        max_length=8,
        description="Ranked list of load-bearing concepts for this article",
    )
