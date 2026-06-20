from __future__ import annotations

import json
from typing import Any

from app.core.config import settings
from app.llm import LLMClient
from app.logging_config import get_logger
from app.modules.extractor.models.knowledge_model import KnowledgeModel, SectionRelevance
from app.modules.sections._shared.entity_resolver import (
    build_name_to_slug_map,
    resolve_entity_refs_in_text,
)
from app.modules.sections.tradeoffs.prompts import (
    TRADEOFFS_SYSTEM_PROMPT,
    build_tradeoffs_user_prompt,
)
from app.modules.sections.tradeoffs.schemas import (
    ConstraintEntry,
    TradeoffEntry,
    TradeoffsEnrichment,
    TradeoffsSection,
)
from app.storage.models import Article

_log = get_logger(__name__)


class TradeoffsBuilder:
    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self._llm = llm_client or LLMClient()

    def build(
        self, knowledge_model: KnowledgeModel, article: Article
    ) -> TradeoffsSection:
        log = _log.bind(
            article_id=article.article_id,
            title=(article.source_title or "")[:60],
        )

        # ── Phase 1: deterministic extraction ──────────────────────────
        tradeoffs_json = self._build_tradeoffs_json(knowledge_model)
        constraints_json = self._build_constraints_json(knowledge_model)

        # ── Phase 2: LLM enrichment ────────────────────────────────────
        try:
            enrichment = self._llm.extract_structured(
                system_prompt=TRADEOFFS_SYSTEM_PROMPT,
                user_prompt=build_tradeoffs_user_prompt(
                    tradeoffs_json=tradeoffs_json,
                    constraints_json=constraints_json,
                    article_title=article.source_title or "Untitled",
                    article_domain=article.source_domain or "Unknown",
                ),
                response_model=TradeoffsEnrichment,
                temperature=0.4,
                validation_retries=2,
                model=settings.section_model,
            )
        except Exception:
            enrichment = None
            log.opt.warning("tradeoffs:phase_2_failed | falling_back_to_deterministic")

        # ── Phase 3: assemble ──────────────────────────────────────────
        if enrichment:
            tradeoffs = enrichment.tradeoffs
            constraints = enrichment.constraints
            takeaways = enrichment.takeaways
        else:
            tradeoffs = self._build_deterministic_tradeoffs(knowledge_model)
            constraints = self._build_deterministic_constraints(knowledge_model)
            takeaways = self._build_deterministic_takeaways(knowledge_model)

        # Enrich tradeoffs with evidence and entity links from the KM
        tradeoffs = self._enrich_tradeoffs(tradeoffs, knowledge_model)

        result = TradeoffsSection(
            tradeoffs=tradeoffs,
            constraints=constraints,
            takeaways=takeaways,
        )
        return result

    # ── Phase 1 helpers ─────────────────────────────────────────────────

    @staticmethod
    def _build_tradeoffs_json(knowledge_model: KnowledgeModel) -> str:
        payload: list[dict[str, Any]] = []
        for t in knowledge_model.tradeoff_signals:
            payload.append({
                "description": t.description,
                "benefit": t.benefit,
                "cost": t.cost,
                "condition": t.condition,
            })
        return json.dumps(payload, indent=2, ensure_ascii=False)

    @staticmethod
    def _build_constraints_json(knowledge_model: KnowledgeModel) -> str:
        payload: list[dict[str, Any]] = []
        for c in knowledge_model.constraint_signals:
            payload.append({"description": c})
        return json.dumps(payload, indent=2, ensure_ascii=False)

    # ── Phase 3 fallback helpers ────────────────────────────────────────

    @staticmethod
    def _build_deterministic_tradeoffs(
        knowledge_model: KnowledgeModel
    ) -> list[TradeoffEntry]:
        return [
            TradeoffEntry(
                description=t.description,
                benefit=t.benefit,
                cost=t.cost,
                condition=t.condition,
                category=None,
                insight=None,
                evidence=t.evidence,
            )
            for t in knowledge_model.tradeoff_signals
        ]

    @staticmethod
    def _build_deterministic_constraints(
        knowledge_model: KnowledgeModel
    ) -> list[ConstraintEntry]:
        return [
            ConstraintEntry(description=c, impact=None)
            for c in knowledge_model.constraint_signals
        ]

    def _build_deterministic_takeaways(
        self, knowledge_model: KnowledgeModel
    ) -> str:
        parts: list[str] = []
        if knowledge_model.tradeoff_signals:
            parts.append(
                f"The article describes {len(knowledge_model.tradeoff_signals)} "
                f"explicit design tradeoffs that shaped the system's architecture."
            )
        if knowledge_model.constraint_signals:
            parts.append(
                f"The design was governed by {len(knowledge_model.constraint_signals)} "
                f"hard constraints that limited the solution space."
            )
        if not parts:
            parts.append(
                "The article's engineering decisions reflect common tradeoffs "
                "between performance, cost, complexity, and reliability."
            )
        return " ".join(parts)

    @staticmethod
    def _enrich_tradeoffs(
        tradeoffs: list[TradeoffEntry], knowledge_model: KnowledgeModel
    ) -> list[TradeoffEntry]:
        """Populate evidence, affected_entities, and affected_entity_ids.

        Evidence is copied from the KM's tradeoff_signals for deterministic
        entries, or backfilled from SectionRelevance.TRADEOFFS quotes (previously
        unused). Affected entities are resolved by finding entity names mentioned
        in each tradeoff's description, benefit, and cost text. affected_entity_ids
        stores the architecture node slugs for deterministic cross-section linking.
        """
        # Build a map from KM tradeoff description → evidence for deterministic fallback
        km_evidence_map: dict[str, str] = {}
        for t in knowledge_model.tradeoff_signals:
            if t.evidence:
                km_evidence_map[t.description] = t.evidence

        # Collect TRADEOFFS-relevant quotes (previously unused) for evidence backfill
        tradeoff_quotes = [
            q.text
            for q in knowledge_model.key_quotes
            if SectionRelevance.TRADEOFFS in q.section_relevance
        ]

        # Build name → slug map using the shared utility (same collision handling
        # as ArchitectureBuilder, so slugs match architecture node IDs exactly)
        name_to_slug = build_name_to_slug_map(knowledge_model)

        for tradeoff in tradeoffs:
            # Fill evidence from KM if not already set by enrichment
            if not tradeoff.evidence:
                tradeoff.evidence = km_evidence_map.get(tradeoff.description)

            # Backfill evidence from TRADEOFFS-relevant quotes if still missing
            if not tradeoff.evidence and tradeoff_quotes:
                search_text = f"{tradeoff.description} {tradeoff.benefit} {tradeoff.cost}".lower()
                for quote in tradeoff_quotes:
                    if any(word in quote.lower() for word in search_text.split()[:3]):
                        tradeoff.evidence = quote
                        break

            # Find affected entities by substring matching in tradeoff text
            search_text = f"{tradeoff.description} {tradeoff.benefit} {tradeoff.cost}"
            affected_ids = resolve_entity_refs_in_text(search_text, name_to_slug)

            # Map slugs back to entity names for affected_entities
            slug_to_name: dict[str, str] = {}
            for entity in knowledge_model.named_entities:
                slug = name_to_slug.get(entity.name)
                if slug:
                    slug_to_name[slug] = entity.name

            tradeoff.affected_entity_ids = affected_ids
            tradeoff.affected_entities = [
                slug_to_name[s] for s in affected_ids if s in slug_to_name
            ]

        return tradeoffs
