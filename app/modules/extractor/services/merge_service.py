from __future__ import annotations

from app.modules.extractor.models.extraction_result import ExtractionResult
from app.modules.extractor.models.knowledge_model import KnowledgeModel
from app.modules.extractor.models.recognition_output import RecognitionOutput
from app.modules.extractor.models.structure_output import StructureOutput
from app.modules.extractor.models.reasoning_output import ReasoningOutput


class MergeService:
    """Deterministic composition of three pass outputs into a KnowledgeModel.

    No LLM calls, no transformations, no normalization. Each field in the
    final KnowledgeModel maps directly to a field in one of the three pass
    output models. The merge trusts the passes — the design ensures each
    pass produces the exact sub-models and field names the KnowledgeModel
    constructor expects.

    The overall confidence_score for the merged model is the minimum of the
    three pass combined scores (weakest-link principle). Extraction warnings
    are aggregated from Pass 3 (reasoning) and any cross-pass validation
    failures passed in by the caller.

    Usage::

        km = MergeService.merge(pass_1_result, pass_2_result, pass_3_result,
                                cross_pass_warnings=["relationships[0].source missing"])
        # km is a fully populated KnowledgeModel ready for downstream use
    """

    @staticmethod
    def merge(
        pass_1: ExtractionResult[RecognitionOutput],
        pass_2: ExtractionResult[StructureOutput],
        pass_3: ExtractionResult[ReasoningOutput],
        cross_pass_warnings: list[str] | None = None,
    ) -> KnowledgeModel:
        """Assemble the final KnowledgeModel from three independent pass results.

        Fields are assigned by source:
          - **Recognition** → article_summary, core_problem, named_entities,
            concept_definitions, key_quotes, problem_signals, scale_context_signals
          - **Structure** → relationships, flow_sequences, layer_signals,
            temporal_signals
          - **Reasoning** → tradeoff_signals, constraint_signals
          - **Computed** → confidence_score = min(p1, p2, p3 combined scores);
            extraction_warnings = reasoning warnings + cross_pass_warnings

        Args:
            pass_1: The recognition extraction result (entities, concepts, etc.)
            pass_2: The structure extraction result (relationships, flows, etc.)
            pass_3: The reasoning extraction result (tradeoffs, constraints, etc.)
            cross_pass_warnings: Optional list of referential-integrity errors
                from the cross-pass validator that should be surfaced to
                downstream components.

        Returns:
            A fully composed KnowledgeModel with schema_version=2, ready for
            validation and section generation.
        """
        p1 = pass_1.data
        p2 = pass_2.data
        p3 = pass_3.data

        merged_warnings: list[str] = []
        merged_warnings.extend(p3.extraction_warnings)
        if cross_pass_warnings:
            merged_warnings.extend(cross_pass_warnings)

        return KnowledgeModel(
            schema_version=2,
            # Pass 1 — Recognition
            article_summary=p1.article_summary,
            core_problem=p1.core_problem,
            named_entities=p1.named_entities,
            concept_definitions=p1.concept_definitions,
            key_quotes=p1.key_quotes,
            problem_signals=p1.problem_signals,
            scale_context_signals=p1.scale_context_signals,
            # Pass 2 — Structure
            relationships=p2.relationships,
            flow_sequences=p2.flow_sequences,
            layer_signals=p2.layer_signals,
            temporal_signals=p2.temporal_signals,
            # Pass 3 — Reasoning
            tradeoff_signals=p3.tradeoff_signals,
            constraint_signals=p3.constraint_signals,
            # Computed
            confidence_score=min(
                pass_1.combined_score,
                pass_2.combined_score,
                pass_3.combined_score,
            ),
            extraction_warnings=merged_warnings,
        )
