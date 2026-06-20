from __future__ import annotations

from pydantic import BaseModel, Field

from app.modules.sections._shared.enums import Severity


class ProblemSignal(BaseModel):
    description: str = Field(
        ..., description="A specific pain point, failure mode, or constraint from the article"
    )
    severity: Severity = Field(
        ..., description="Severity level: critical, major, or minor — based on the article's framing"
    )
    scale_dimension: str | None = Field(
        default=None, description="latency, throughput, cost, reliability, complexity, or other"
    )
    evidence: str | None = Field(
        default=None,
        description="Verbatim or near-verbatim quote from the article supporting this signal",
    )
    affected_entity_ids: list[str] = Field(
        default_factory=list,
        description="Architecture node IDs (slugs) related to this problem signal. Used for cross-section visual linking — the UI can highlight affected nodes when a problem signal is selected.",
    )


class ProblemStatementEnrichment(BaseModel):
    problem_narrative: str = Field(
        ...,
        description="2-3 paragraph narrative describing the problem context, its impact, and why existing solutions fell short",
    )
    signals: list[ProblemSignal] = Field(
        default_factory=list,
        max_length=6,
        description="Enriched problem signals with severity and classification",
    )


class ProblemStatementSection(BaseModel):
    problem_narrative: str = Field(
        ...,
        description="2-3 paragraph narrative describing the problem the article addresses",
    )
    signals: list[ProblemSignal] = Field(
        default_factory=list,
        min_length=1,
        max_length=6,
        description="Categorized problem signals with severity, evidence, and architecture node links",
    )
    core_problem: str = Field(
        ..., description="Single-sentence distillation of the central technical challenge"
    )
    why_it_hurt: str = Field(
        ...,
        description="Explanation of why the problem was urgent or impactful — what was at stake",
    )
