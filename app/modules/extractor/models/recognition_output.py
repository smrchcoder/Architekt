from __future__ import annotations

from pydantic import BaseModel, Field

from app.modules.extractor.models.knowledge_model import (
    ConceptDef,
    NamedEntity,
    QuoteSignal,
)


class RecognitionOutput(BaseModel):
    """Pass 1 — Recognition. Extracts entities, concepts, quotes, problems, and scale context."""

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
        description="Every explicitly named system, service, tool, protocol, company, or team that plays a meaningful role in the article",
    )
    concept_definitions: list[ConceptDef] = Field(
        default_factory=list,
        min_length=2,
        max_length=12,
        description="Load-bearing technical concepts a reader needs to understand to follow the article. Exclude concepts that are merely mentioned in passing.",
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
    confidence_score: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Self-assessed quality of this extraction. 1.0 = all fields richly populated, no ambiguity. 0.7 = most fields filled but some signals missing. 0.4 = article is sparse or vague.",
    )
