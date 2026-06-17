from __future__ import annotations

from app.modules.extractor.models.extraction_result import ExtractionResult
from app.modules.extractor.models.knowledge_model import (
    EntityType,
    KnowledgeModel,
    NamedEntity,
)
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

    Entity backfill: When Pass 2 (structure) references entities not found
    in Pass 1's inventory (common in dense articles where Pass 1 misses
    infrastructure/tool entities), the merger promotes them into the entity
    list as vendor_tool or external_tool entities. This reduces cross-pass
    validation failures without requiring a re-run of Pass 1.

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

        Entity backfill promotes entities found in Pass 2 references but
        missing from Pass 1's inventory into the named_entities list.

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

        named_entities = MergeService._backfill_entities(p1.named_entities, p2)

        return KnowledgeModel(
            schema_version=2,
            # Pass 1 — Recognition
            article_summary=p1.article_summary,
            core_problem=p1.core_problem,
            named_entities=named_entities,
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

    @staticmethod
    def _backfill_entities(
        existing_entities: list[NamedEntity],
        p2: StructureOutput,
    ) -> list[NamedEntity]:
        """Promote entity names found in Pass 2 references into the entity list.

        Collects all entity names referenced in relationships (source/target),
        flow steps (actor/target), layer signals (entities_in_layer), and
        temporal signals (before_entity/after_entity). Any names not already
        in the Pass 1 entity inventory are added as stub NamedEntity entries
        with sane defaults.
        """
        entity_names: set[str] = {e.name for e in existing_entities}
        referenced: set[str] = set()

        for rel in p2.relationships:
            referenced.add(rel.source)
            referenced.add(rel.target)

        for seq in p2.flow_sequences:
            for step in seq.steps:
                referenced.add(step.actor)
                if step.target:
                    referenced.add(step.target)

        for layer in p2.layer_signals:
            for name in layer.entities_in_layer:
                referenced.add(name)

        for signal in p2.temporal_signals:
            if signal.before_entity:
                referenced.add(signal.before_entity)
            if signal.after_entity:
                referenced.add(signal.after_entity)

        new_entities: list[NamedEntity] = list(existing_entities)
        for name in sorted(referenced):
            if name and name not in entity_names:
                new_entities.append(
                    NamedEntity(
                        name=name,
                        entity_type=MergeService._infer_entity_type(name),
                        description=f"Referenced in the article's architecture as {name}",
                        is_primary=False,
                        first_mention_context=f"Referenced as {name}",
                        aliases=[],
                    )
                )

        return new_entities

    @staticmethod
    def _infer_entity_type(name: str) -> EntityType:
        """Infer an entity type from name patterns for backfilled entities."""
        name_lower = name.lower()
        vendor_tool_signals = {
            "jira", "gitlab", "github", "sentry", "elasticsearch",
            "prometheus", "grafana", "datadog", "pagerduty", "slack",
            "google workspace", "confluence", "bitbucket", "circleci",
            "jenkins", "terraform", "ansible",
        }
        framework_signals = {
            "react", "angular", "vue", "django", "rails", "spring",
            "bazel", "next.js", "nuxt", "svelte", "flutter",
        }
        product_signals = {
            "cloudflare access", "workers", "durable objects", "ai gateway",
            "workers ai", "agents sdk", "sandbox sdk", "workflows",
            "dynamic workers", "mcp portal", "mcp server portal",
        }

        if any(signal in name_lower for signal in vendor_tool_signals):
            return EntityType.VENDOR_TOOL
        if any(signal in name_lower for signal in framework_signals):
            return EntityType.FRAMEWORK
        if any(signal in name_lower for signal in product_signals):
            return EntityType.PRODUCT
        if any(kw in name_lower for kw in ["server", "service", "proxy", "worker", "agent", "api"]):
            return EntityType.INTERNAL_SYSTEM
        if any(kw in name_lower for kw in ["db", "database", "cache", "queue", "store", "sql"]):
            return EntityType.DATA_STORE
        return EntityType.EXTERNAL_TOOL
