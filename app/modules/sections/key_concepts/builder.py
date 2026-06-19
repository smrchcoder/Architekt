from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any

from app.core.config import settings
from app.llm import LLMClient
from app.logging_config import get_logger
from app.modules.extractor.models.knowledge_model import (
    ConceptDef,
    ConceptKind,
    EntityType,
    KnowledgeModel,
    NamedEntity,
)
from app.modules.sections.key_concepts.prompts import (
    KEY_CONCEPTS_SYSTEM_PROMPT,
    build_key_concepts_user_prompt,
)
from app.modules.sections.key_concepts.schemas import (
    ConceptEnrichment,
    ConceptEntry,
    KeyConceptsEnrichment,
    KeyConceptsSection,
)
from app.storage.models import Article

GENERIC_TERMS: set[str] = {
    "api", "rest", "json", "http", "https", "microservice", "microservices",
    "database", "server", "client", "tcp", "udp", "rpc", "sdk", "sla",
    "load balancer", "cache", "docker", "kubernetes", "k8s",
}

CONCEPT_KIND_WEIGHTS: dict[ConceptKind, int] = {
    ConceptKind.ARCHITECTURAL_CONCERN: 12,
    ConceptKind.DESIGN_PATTERN: 8,
    ConceptKind.DOMAIN_ABSTRACTION: 5,
    ConceptKind.IMPLEMENTATION_DETAIL: 1,
}

_log = get_logger(__name__)


class KeyConceptsBuilder:
    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self._llm = llm_client or LLMClient()

    def build(
        self, knowledge_model: KnowledgeModel, article: Article
    ) -> KeyConceptsSection:
        log = _log.bind(
            article_id=article.article_id,
            title=(article.source_title or "")[:60],
        )

        if len(knowledge_model.concept_definitions) < 2:
            raise ValueError(
                "key concepts requires at least 2 concept_definitions in the KnowledgeModel"
            )

        entity_map = self._build_entity_map(knowledge_model.named_entities)
        relationship_refs = self._count_relationship_refs(knowledge_model)
        flow_refs = self._count_flow_refs(knowledge_model)

        concept_score_list: list[tuple[int, ConceptDef]] = []
        for concept in knowledge_model.concept_definitions:
            term_lower = concept.term.lower()
            is_generic = term_lower in GENERIC_TERMS
            ref_total = relationship_refs.get(concept.term, 0) + flow_refs.get(concept.term, 0)
            if is_generic and ref_total == 0 and concept.usage_count <= 2:
                continue
            base_weight = CONCEPT_KIND_WEIGHTS.get(concept.concept_kind, 3)
            score = base_weight + concept.usage_count + ref_total
            concept_score_list.append((score, concept))

        concept_score_list.sort(key=lambda x: x[0], reverse=True)
        selected = concept_score_list[:12]

        if len(selected) < 2:
            raise ValueError(
                "key concepts requires at least 2 load-bearing concepts after filtering"
            )

        # ── Phase 2: LLM enrichment of narrative fields ─────────────────
        concepts_json = self._build_enrichment_input(selected, knowledge_model, entity_map)
        context_snippets = self._gather_context_snippets(selected, knowledge_model, entity_map)

        try:
            enrichment = self._llm.extract_structured(
                system_prompt=KEY_CONCEPTS_SYSTEM_PROMPT,
                user_prompt=build_key_concepts_user_prompt(
                    concepts_json=concepts_json,
                    article_title=article.source_title or "Untitled",
                    article_domain=article.source_domain or "Unknown",
                    article_context_snippets=context_snippets,
                ),
                response_model=KeyConceptsEnrichment,
                temperature=0.4,
                validation_retries=2,
                model=settings.section_model,
            )
            enriched_map: dict[str, ConceptEnrichment] = {
                e.id: e for e in enrichment.concepts
            }
        except Exception:
            enriched_map = {}
            log.opt.warning(
                "section_2:phase_2_failed | falling_back_to_deterministic | selected=%d",
                len(selected),
            )

        # ── Phase 3: assemble final entries ─────────────────────────────
        entries: list[ConceptEntry] = []
        slug_counts: dict[str, int] = {}
        for _, concept in selected:
            slug = self._slugify(concept.term)
            slug_counts[slug] = slug_counts.get(slug, 0) + 1
            if slug_counts[slug] > 1:
                slug = f"{slug}-{slug_counts[slug]}"

            enriched = enriched_map.get(slug)
            if enriched:
                short_def = enriched.short_def
                why_it_matters = enriched.why_it_matters
            else:
                short_def = self._resolve_definition(concept, knowledge_model, entity_map)
                why_it_matters = self._build_why_it_matters(
                    concept, knowledge_model, relationship_refs, flow_refs
                )

            arch_refs = self._resolve_architecture_refs(concept, knowledge_model)

            entries.append(
                ConceptEntry(
                    id=slug,
                    name=concept.term,
                    short_def=short_def,
                    why_it_matters=why_it_matters,
                    category=concept.category_hint,
                    difficulty=concept.difficulty_hint,
                    architecture_node_refs=arch_refs,
                )
            )

        result = KeyConceptsSection(concepts=entries)
        return result
    def _build_entity_map(self, entities: list[NamedEntity]) -> dict[str, NamedEntity]:
        entity_map: dict[str, NamedEntity] = {}
        for e in entities:
            entity_map[e.name.lower()] = e
            for alias in e.aliases:
                entity_map[alias.lower()] = e
        return entity_map

    @staticmethod
    def _count_relationship_refs(knowledge_model: KnowledgeModel) -> dict[str, int]:
        counts: Counter[str] = Counter()
        for rel in knowledge_model.relationships:
            counts[rel.source] += 1
            counts[rel.target] += 1
        return dict(counts)

    @staticmethod
    def _count_flow_refs(knowledge_model: KnowledgeModel) -> dict[str, int]:
        counts: Counter[str] = Counter()
        for sequence in knowledge_model.flow_sequences:
            for step in sequence.steps:
                counts[step.actor] += 1
                if step.target:
                    counts[step.target] += 1
        return dict(counts)

    # ── Phase 2 helpers ─────────────────────────────────────────────────

    def _build_enrichment_input(
        self,
        scored: list[tuple[int, ConceptDef]],
        knowledge_model: KnowledgeModel,
        entity_map: dict[str, NamedEntity],
    ) -> str:
        payload: list[dict[str, Any]] = []
        for _, concept in scored:
            slug = self._slugify(concept.term)
            entity = entity_map.get(concept.term.lower())
            relevant_rels = [
                f"{rel.source} → {rel.target}: {rel.label}"
                for rel in knowledge_model.relationships
                if rel.source.lower() == concept.term.lower()
                or rel.target.lower() == concept.term.lower()
            ]
            relevant_flows = [
                f"Step {step.step_order}: {step.actor} → {step.target or '—'}: {step.action}"
                for sequence in knowledge_model.flow_sequences
                for step in sequence.steps
                if step.actor.lower() == concept.term.lower()
                or (step.target and step.target.lower() == concept.term.lower())
            ]
            payload.append({
                "id": slug,
                "term": concept.term,
                "category": concept.category_hint.value,
                "difficulty": concept.difficulty_hint.value,
                "concept_kind": concept.concept_kind.value,
                "usage_count": concept.usage_count,
                "inline_definition": concept.inline_definition,
                "first_mention_context": entity.first_mention_context if entity else None,
                "relationships": relevant_rels[:3],
                "flow_steps": relevant_flows[:3],
            })
        return json.dumps(payload, indent=2, ensure_ascii=False)

    def _gather_context_snippets(
        self,
        scored: list[tuple[int, ConceptDef]],
        knowledge_model: KnowledgeModel,
        entity_map: dict[str, NamedEntity],
    ) -> str:
        seen: set[str] = set()
        snippets: list[str] = []
        for _, concept in scored:
            entity = entity_map.get(concept.term.lower())
            if entity and entity.first_mention_context not in seen:
                seen.add(entity.first_mention_context)
                snippets.append(f"[{entity.name}] {entity.first_mention_context}")

            for rel in knowledge_model.relationships:
                if (rel.source.lower() == concept.term.lower()
                        or rel.target.lower() == concept.term.lower()):
                    text = f"[{rel.source} ↔ {rel.target}] {rel.label}"
                    if text not in seen:
                        seen.add(text)
                        snippets.append(text)

            for sequence in knowledge_model.flow_sequences:
                for step in sequence.steps:
                    if (step.actor.lower() == concept.term.lower()
                            or (step.target and step.target.lower() == concept.term.lower())):
                        text = f"[Flow step {step.step_order}] {step.actor} → {step.target or '—'}: {step.action}"
                        if text not in seen:
                            seen.add(text)
                            snippets.append(text)

        return "\n".join(snippets)

    # ── Phase 3 & fallback helpers ──────────────────────────────────────

    def _resolve_definition(
        self,
        concept: ConceptDef,
        knowledge_model: KnowledgeModel,
        entity_map: dict[str, NamedEntity],
    ) -> str:
        if concept.inline_definition:
            return self._sentence(concept.inline_definition)

        entity = entity_map.get(concept.term.lower())
        if entity:
            return self._sentence(entity.first_mention_context)

        for rel in knowledge_model.relationships:
            if rel.source.lower() == concept.term.lower():
                return self._sentence(
                    f"{concept.term} interacts with {rel.target}: {rel.label}"
                )
            if rel.target.lower() == concept.term.lower():
                return self._sentence(
                    f"{rel.source} interacts with {concept.term}: {rel.label}"
                )

        for sequence in knowledge_model.flow_sequences:
            for step in sequence.steps:
                if step.actor.lower() == concept.term.lower():
                    return self._sentence(f"{concept.term} performs: {step.action}")
                if step.target and step.target.lower() == concept.term.lower():
                    return self._sentence(
                        f"{concept.term} receives: {step.action} from {step.actor}"
                    )

        return self._sentence(
            f"{concept.term} is a key concept in this system architecture"
        )

    def _build_why_it_matters(
        self,
        concept: ConceptDef,
        knowledge_model: KnowledgeModel,
        relationship_refs: dict[str, int],
        flow_refs: dict[str, int],
    ) -> str:
        term = concept.term
        parts: list[str] = []

        relevant_rels = [
            rel
            for rel in knowledge_model.relationships
            if rel.source.lower() == term.lower()
            or rel.target.lower() == term.lower()
        ]
        if relevant_rels:
            parts.append(relevant_rels[0].label)

        flow_count = flow_refs.get(term, 0)
        if flow_count > 0:
            parts.append(
                f"It participates in {flow_count} step{'s' if flow_count > 1 else ''} of the request/data flow"
            )

        if parts:
            return self._sentence("; ".join(parts))

        return self._sentence(self._category_fallback(concept))

    @staticmethod
    def _category_fallback(concept: ConceptDef) -> str:
        category = concept.category_hint.value
        fallbacks = {
            "infrastructure": f"{concept.term} is an infrastructure component enabling the system's operation",
            "pattern": f"{concept.term} is an architectural pattern used in the system design",
            "data_model": f"{concept.term} is a data model that structures information flow in the system",
            "protocol": f"{concept.term} is a protocol governing communication between system components",
            "tool": f"{concept.term} is a tool used by the engineering team",
            "algorithm": f"{concept.term} is an algorithm critical to the system's behavior",
        }
        return fallbacks.get(
            category,
            f"{concept.term} is essential to understanding this system's architecture",
        )

    def _resolve_architecture_refs(
        self, concept: ConceptDef, knowledge_model: KnowledgeModel
    ) -> list[str]:
        term_lower = concept.term.lower()
        refs: list[str] = []
        for entity in knowledge_model.named_entities:
            if entity.entity_type in {
                EntityType.INTERNAL_SYSTEM,
                EntityType.EXTERNAL_TOOL,
                EntityType.DATA_STORE,
            }:
                if entity.name.lower() == term_lower or any(
                    alias.lower() == term_lower for alias in entity.aliases
                ):
                    refs.append(self._slugify(entity.name))
        return refs

    @staticmethod
    def _slugify(text: str) -> str:
        slug = text.lower().strip()
        slug = re.sub(r"[^a-z0-9]+", "-", slug)
        return slug.strip("-")

    @staticmethod
    def _sentence(text: str) -> str:
        cleaned = " ".join(text.strip().split())
        if not cleaned:
            return cleaned
        return cleaned if cleaned.endswith((".", "!", "?")) else f"{cleaned}."
