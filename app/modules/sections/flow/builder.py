from __future__ import annotations

import json
from typing import Any

from app.core.config import settings
from app.llm import LLMClient
from app.logging_config import get_logger
from app.modules.extractor.models.knowledge_model import (
    InteractionType,
    KnowledgeModel,
    SectionRelevance,
)
from app.modules.sections._shared.entity_resolver import (
    build_name_to_slug_map,
)
from app.modules.sections.flow.prompts import (
    FLOW_SYSTEM_PROMPT,
    build_flow_user_prompt,
)
from app.modules.sections.flow.schemas import (
    FlowEnrichment,
    FlowSection,
    FlowStep,
    FlowWalkthroughEnrichment,
    FlowTransition,
    FlowWalkthrough,
)
from app.storage.models import Article

_log = get_logger(__name__)


class FlowBuilder:
    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self._llm = llm_client or LLMClient()

    def build(
        self, knowledge_model: KnowledgeModel, article: Article
    ) -> FlowSection:
        log = _log.bind(
            article_id=article.article_id,
            title=(article.source_title or "")[:60],
        )

        if len(knowledge_model.flow_sequences) < 1:
            raise ValueError("flow section requires at least 1 flow sequence")

        # Collect layer names so entities matching layer names are skipped
        # (matching ArchitectureBuilder behavior — prevents dangling slugs)
        layer_names: set[str] = {
            layer_signal.layer_name for layer_signal in knowledge_model.layer_signals
        }

        # Build entity name → slug map using the shared utility.
        # This uses the SAME collision handling as ArchitectureBuilder,
        # so flow node IDs match architecture node IDs exactly.
        name_to_slug = build_name_to_slug_map(
            knowledge_model, skip_layer_names=True, layer_names=layer_names
        )

        # Build a lookup for interaction types from KM relationships
        interaction_lookup = self._build_interaction_lookup(knowledge_model)

        # Build a lookup for entity evidence
        evidence_lookup = self._build_evidence_lookup(knowledge_model)

        # Collect flow-relevant quotes for flow-level evidence
        flow_quotes = self._collect_flow_quotes(knowledge_model)

        # ── Phase 1: deterministic structural extraction ───────────────
        deterministic_flows = self._build_deterministic_flows(
            knowledge_model,
            name_to_slug,
            interaction_lookup,
            evidence_lookup,
            flow_quotes,
        )

        # ── Phase 2: LLM enrichment (narrative only) ───────────────────
        flows_json = self._build_enrichment_input(deterministic_flows)

        try:
            enrichment = self._llm.extract_structured(
                system_prompt=FLOW_SYSTEM_PROMPT,
                user_prompt=build_flow_user_prompt(
                    flows_json=flows_json,
                    article_title=article.source_title or "Untitled",
                    article_domain=article.source_domain or "Unknown",
                ),
                response_model=FlowEnrichment,
                temperature=0.4,
                validation_retries=2,
                model=settings.section_model,
            )
        except Exception:
            enrichment = None
            log.opt.warning("flow:phase_2_failed | falling_back_to_deterministic")

        # ── Phase 3: merge LLM narrative into deterministic structure ──
        if enrichment:
            flows = self._merge_enrichment(deterministic_flows, enrichment)
        else:
            flows = self._apply_deterministic_descriptions(deterministic_flows, knowledge_model)

        result = FlowSection(flows=flows)
        return result

    # ── Phase 1: deterministic structural extraction ─────────────────────

    def _build_deterministic_flows(
        self,
        knowledge_model: KnowledgeModel,
        name_to_slug: dict[str, str],
        interaction_lookup: dict[tuple[str, str], InteractionType],
        evidence_lookup: dict[str, str | None],
        flow_quotes: list[str],
    ) -> list[FlowWalkthrough]:
        """Build complete FlowWalkthrough objects with all structural fields.

        Node IDs are resolved here from the ORIGINAL KM data — not after LLM
        enrichment — so LLM entity renaming cannot break the links.
        """
        flows: list[FlowWalkthrough] = []
        for seq in knowledge_model.flow_sequences:
            flow_id = seq.id

            steps: list[FlowStep] = []
            for step in seq.steps:
                step_id = f"{flow_id}_step_{step.step_order}"
                actor_slug = name_to_slug.get(step.actor)
                target_slug = name_to_slug.get(step.target) if step.target else None

                # Infer interaction type from KM relationships
                interaction_type = interaction_lookup.get(
                    (step.actor, step.target) if step.target else (step.actor, ""),
                )
                if interaction_type is None:
                    interaction_type = InteractionType.DATA_FLOW

                steps.append(
                    FlowStep(
                        id=step_id,
                        order=step.step_order,
                        actor=step.actor,
                        action=step.action,
                        target=step.target,
                        data=step.data_involved,
                        description=None,  # filled by LLM or deterministic fallback
                        interaction_type=interaction_type,
                        actor_node_id=actor_slug,
                        target_node_id=target_slug,
                        evidence=evidence_lookup.get(step.actor),
                    )
                )

            # Build explicit transitions between consecutive steps
            transitions = self._build_transitions(flow_id, steps)

            # Match flow-relevant quotes to this flow for evidence
            flow_evidence = self._match_flow_evidence(seq.flow_name, flow_quotes)

            flows.append(
                FlowWalkthrough(
                    id=flow_id,
                    flow_name=seq.flow_name,
                    entry_point=seq.entry_point,
                    exit_point=seq.exit_point,
                    overview="",  # filled by LLM or deterministic fallback
                    steps=steps,
                    transitions=transitions,
                    evidence=flow_evidence,
                )
            )
        return flows

    @staticmethod
    def _build_transitions(flow_id: str, steps: list[FlowStep]) -> list[FlowTransition]:
        """Build explicit directed edges between consecutive steps."""
        transitions: list[FlowTransition] = []
        for i in range(len(steps) - 1):
            transitions.append(
                FlowTransition(
                    id=f"{flow_id}_t{i + 1}",
                    from_step_id=steps[i].id,
                    to_step_id=steps[i + 1].id,
                )
            )
        return transitions

    @staticmethod
    def _build_interaction_lookup(
        knowledge_model: KnowledgeModel,
    ) -> dict[tuple[str, str], InteractionType]:
        """Build a (source, target) → interaction_type lookup from KM relationships."""
        lookup: dict[tuple[str, str], InteractionType] = {}
        for rel in knowledge_model.relationships:
            lookup[(rel.source, rel.target)] = rel.interaction_type
            if rel.is_bidirectional:
                lookup[(rel.target, rel.source)] = rel.interaction_type
        return lookup

    @staticmethod
    def _build_evidence_lookup(
        knowledge_model: KnowledgeModel,
    ) -> dict[str, str | None]:
        """Build entity name → evidence lookup from KM named entities."""
        lookup: dict[str, str | None] = {}
        for entity in knowledge_model.named_entities:
            lookup[entity.name] = entity.evidence
            for alias in entity.aliases:
                lookup[alias] = entity.evidence
        return lookup

    @staticmethod
    def _collect_flow_quotes(knowledge_model: KnowledgeModel) -> list[str]:
        """Collect quotes tagged with SectionRelevance.FLOW (previously unused)."""
        flow_quotes = [
            q.text
            for q in knowledge_model.key_quotes
            if SectionRelevance.FLOW in q.section_relevance
        ]
        return flow_quotes

    @staticmethod
    def _match_flow_evidence(flow_name: str, flow_quotes: list[str]) -> str | None:
        """Match flow-relevant quotes to a flow by substring matching."""
        flow_name_lower = flow_name.lower()
        for quote in flow_quotes:
            if flow_name_lower in quote.lower():
                return quote
        return flow_quotes[0] if flow_quotes else None

    # ── Phase 2: LLM enrichment input ────────────────────────────────────

    @staticmethod
    def _build_enrichment_input(flows: list[FlowWalkthrough]) -> str:
        """Build JSON input for the LLM — structural context only, no return fields."""
        payload: list[dict[str, Any]] = []
        for flow in flows:
            payload.append({
                "flow_name": flow.flow_name,
                "entry_point": flow.entry_point,
                "exit_point": flow.exit_point,
                "steps": [
                    {
                        "order": step.order,
                        "actor": step.actor,
                        "action": step.action,
                        "target": step.target,
                        "data": step.data,
                    }
                    for step in flow.steps
                ],
            })
        return json.dumps(payload, indent=2, ensure_ascii=False)

    # ── Phase 3: merge enrichment ─────────────────────────────────────────

    @staticmethod
    def _merge_enrichment(
        deterministic_flows: list[FlowWalkthrough],
        enrichment: FlowEnrichment,
    ) -> list[FlowWalkthrough]:
        """Merge LLM narrative (overview, descriptions) into deterministic flows.

        All structural fields (id, entry_point, exit_point, interaction_type,
        node IDs, transitions) are preserved from the deterministic phase.
        Only overview and step descriptions come from the LLM.
        """
        # Build lookup by flow_name for matching
        enriched_by_name: dict[str, FlowWalkthroughEnrichment] = {
            e.flow_name: e for e in enrichment.flows
        }

        for flow in deterministic_flows:
            enriched = enriched_by_name.get(flow.flow_name)
            if enriched:
                flow.overview = enriched.overview
                # Match step descriptions by order
                desc_by_order: dict[int, str] = {
                    s.order: s.description for s in enriched.steps
                }
                for step in flow.steps:
                    if step.order in desc_by_order:
                        step.description = desc_by_order[step.order]
            else:
                # No enrichment for this flow — use deterministic fallback
                flow.overview = FlowBuilder._build_flow_overview(flow)
                for step in flow.steps:
                    if step.description is None:
                        step.description = FlowBuilder._describe_step(step)

        return deterministic_flows

    def _apply_deterministic_descriptions(
        self, flows: list[FlowWalkthrough], knowledge_model: KnowledgeModel
    ) -> list[FlowWalkthrough]:
        """Fill in overview and descriptions when LLM enrichment fails."""
        for flow in flows:
            flow.overview = self._build_flow_overview(flow)
            for step in flow.steps:
                if step.description is None:
                    step.description = self._describe_step(step)
        return flows

    @staticmethod
    def _describe_step(step: FlowStep) -> str:
        parts = [f"{step.actor} {step.action}"]
        if step.target:
            parts.append(f"to {step.target}")
        if step.data:
            parts.append(f"({step.data})")
        return " ".join(parts)

    @staticmethod
    def _build_flow_overview(flow: FlowWalkthrough) -> str:
        return (
            f"The {flow.flow_name} flow is triggered by {flow.entry_point} "
            f"and results in {flow.exit_point}. "
            f"It involves {len(flow.steps)} steps."
        )
