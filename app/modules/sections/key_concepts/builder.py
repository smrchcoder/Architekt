from __future__ import annotations

import re
from collections import Counter

from app.modules.extractor.models.knowledge_model import (
    ConceptDef,
    EntityType,
    KnowledgeModel,
    NamedEntity,
)
from app.modules.sections.key_concepts.schemas import ConceptEntry, KeyConceptsSection
from app.storage.models import Article

GENERIC_TERMS: set[str] = {
    "api", "rest", "json", "http", "https", "microservice", "microservices",
    "database", "server", "client", "tcp", "udp", "rpc", "sdk", "sla",
    "load balancer", "cache", "docker", "kubernetes", "k8s",
}


class KeyConceptsBuilder:
    def build(
        self, knowledge_model: KnowledgeModel, article: Article
    ) -> KeyConceptsSection:
        if len(knowledge_model.concept_definitions) < 2:
            raise ValueError(
                "key concepts requires at least 2 concept_definitions in the KnowledgeModel"
            )

        entity_map = self._build_entity_map(knowledge_model.named_entities)
        relationship_refs = self._count_relationship_refs(knowledge_model)
        flow_refs = self._count_flow_refs(knowledge_model)

        scored: list[tuple[int, ConceptDef]] = []
        for concept in knowledge_model.concept_definitions:
            term_lower = concept.term.lower()
            is_generic = term_lower in GENERIC_TERMS
            ref_total = relationship_refs.get(concept.term, 0) + flow_refs.get(concept.term, 0)
            if is_generic and ref_total == 0 and concept.usage_count <= 2:
                continue
            score = concept.usage_count + (ref_total * 2)
            scored.append((score, concept))

        scored.sort(key=lambda x: x[0], reverse=True)
        selected = scored[:8]

        if len(selected) < 2:
            raise ValueError(
                "key concepts requires at least 2 load-bearing concepts after filtering"
            )

        entries: list[ConceptEntry] = []
        slug_counts: dict[str, int] = {}
        for _, concept in selected:
            slug = self._slugify(concept.term)
            slug_counts[slug] = slug_counts.get(slug, 0) + 1
            if slug_counts[slug] > 1:
                slug = f"{slug}-{slug_counts[slug]}"

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

        return KeyConceptsSection(concepts=entries)

    # ── helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _build_entity_map(entities: list[NamedEntity]) -> dict[str, NamedEntity]:
        out: dict[str, NamedEntity] = {}
        for e in entities:
            out[e.name.lower()] = e
            for alias in e.aliases:
                out[alias.lower()] = e
        return out

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
        for step in knowledge_model.flow_sequences:
            counts[step.actor] += 1
            if step.target:
                counts[step.target] += 1
        return dict(counts)

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

        for step in knowledge_model.flow_sequences:
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
