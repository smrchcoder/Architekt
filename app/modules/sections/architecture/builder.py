from __future__ import annotations

import json
import re
from typing import Any

from app.core.config import settings
from app.llm import LLMClient
from app.logging_config import get_logger
from app.modules.extractor.models.knowledge_model import (
    EntityType,
    KnowledgeModel,
    SectionRelevance,
)
from app.modules.sections.architecture.prompts import (
    ARCHITECTURE_SYSTEM_PROMPT,
    build_architecture_user_prompt,
)
from app.modules.sections.architecture.schemas import (
    ArchitectureEnrichment,
    ArchitectureLayer,
    ArchitectureNode,
    ArchitectureSection,
)
from app.storage.models import Article

_log = get_logger(__name__)


class ArchitectureBuilder:
    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self._llm = llm_client or LLMClient()

    def build(
        self, knowledge_model: KnowledgeModel, article: Article
    ) -> ArchitectureSection:
        log = _log.bind(
            article_id=article.article_id,
            title=(article.source_title or "")[:60],
        )

        if len(knowledge_model.named_entities) < 2:
            raise ValueError("architecture requires at least 2 named entities")
        if len(knowledge_model.relationships) < 1:
            raise ValueError("architecture requires at least 1 relationship")

        # ── Phase 1: deterministic node/layer extraction ────────────────
        nodes = self._build_nodes(knowledge_model)
        layers = self._build_layers(knowledge_model, nodes)
        relationships_text = self._format_relationships(knowledge_model)
        entities_json = json.dumps([
            {"name": n.name, "type": n.entity_type, "description": n.description}
            for n in nodes
        ], indent=2, ensure_ascii=False)
        layers_json = json.dumps([
            {"name": l.name, "order": l.order, "nodes": [
                n.name for n in nodes if n.layer == l.name
            ]}
            for l in layers
        ], indent=2, ensure_ascii=False) if layers else ""

        key_quotes_text = self._format_arch_quotes(knowledge_model)

        # ── Phase 2: LLM enrichment ────────────────────────────────────
        try:
            enrichment = self._llm.extract_structured(
                system_prompt=ARCHITECTURE_SYSTEM_PROMPT,
                user_prompt=build_architecture_user_prompt(
                    entities_json=entities_json,
                    relationships_text=relationships_text,
                    layers_json=layers_json,
                    key_quotes=key_quotes_text,
                    article_title=article.source_title or "Untitled",
                    article_domain=article.source_domain or "Unknown",
                ),
                response_model=ArchitectureEnrichment,
                temperature=0.4,
                validation_retries=2,
                model=settings.section_model,
            )
        except Exception:
            enrichment = None
            log.opt.warning("section_4:phase_2_failed | falling_back_to_deterministic")

        # ── Phase 3: assemble ──────────────────────────────────────────
        if enrichment:
            narrative = enrichment.overview_narrative
            layers = self._merge_layer_enrichments(layers, enrichment.layers)
        else:
            narrative = self._build_deterministic_narrative(knowledge_model, nodes, layers)

        primary = next((n for n in nodes if n.is_primary), nodes[0] if nodes else None)
        key_relationships = self._top_relationships(knowledge_model)

        result = ArchitectureSection(
            overview_narrative=narrative,
            nodes=nodes,
            layers=layers,
            key_relationships=key_relationships,
        )
        return result

    # ── Phase 1 helpers ─────────────────────────────────────────────────

    def _build_nodes(self, knowledge_model: KnowledgeModel) -> list[ArchitectureNode]:
        nodes: list[ArchitectureNode] = []
        node_ids: set[str] = set()
        for entity in knowledge_model.named_entities:
            slug = self._slugify(entity.name)
            if slug in node_ids:
                slug = f"{slug}-{len(node_ids)}"
            node_ids.add(slug)
            layer = self._find_layer(entity.name, knowledge_model)
            nodes.append(
                ArchitectureNode(
                    id=slug,
                    name=entity.name,
                    entity_type=entity.entity_type.value,
                    description=entity.description,
                    layer=layer,
                    is_primary=entity.is_primary,
                    connected_to=[],
                )
            )

        name_to_id = {n.name: n.id for n in nodes}
        for rel in knowledge_model.relationships:
            src_id = name_to_id.get(rel.source)
            tgt_id = name_to_id.get(rel.target)
            if src_id and tgt_id:
                for node in nodes:
                    if node.id == src_id and tgt_id not in node.connected_to:
                        node.connected_to.append(tgt_id)

        return nodes

    @staticmethod
    def _find_layer(entity_name: str, knowledge_model: KnowledgeModel) -> str | None:
        for layer in knowledge_model.layer_signals:
            if entity_name in layer.entities_in_layer:
                return layer.layer_name
        return None

    def _build_layers(
        self,
        knowledge_model: KnowledgeModel,
        nodes: list[ArchitectureNode],
    ) -> list[ArchitectureLayer]:
        layers: list[ArchitectureLayer] = []
        seen: set[str] = set()
        for signal in knowledge_model.layer_signals:
            if signal.layer_name in seen:
                continue
            seen.add(signal.layer_name)
            layers.append(
                ArchitectureLayer(
                    name=signal.layer_name,
                    order=signal.order_hint,
                    description=None,
                )
            )
        if not layers and len(nodes) >= 4:
            default_nodes = [n.name for n in nodes[:4]]
            layers.append(
                ArchitectureLayer(
                    name="System layer",
                    order=0,
                    description=None,
                )
            )
        return layers

    @staticmethod
    def _format_relationships(knowledge_model: KnowledgeModel) -> str:
        lines: list[str] = []
        for rel in knowledge_model.relationships:
            direction = "↔" if rel.is_bidirectional else "→"
            lines.append(f"{rel.source} {direction} {rel.target}: {rel.label}")
        return "\n".join(lines)

    @staticmethod
    def _format_arch_quotes(knowledge_model: KnowledgeModel) -> str:
        arch_quotes = [
            q for q in knowledge_model.key_quotes
            if SectionRelevance.ARCHITECTURE in q.section_relevance
        ]
        if not arch_quotes:
            return ""
        return "\n".join(f'"{q.text}"' for q in arch_quotes[:3])

    # ── Phase 3 helpers ─────────────────────────────────────────────────

    @staticmethod
    def _merge_layer_enrichments(
        layers: list[ArchitectureLayer],
        enriched: list[ArchitectureLayer],
    ) -> list[ArchitectureLayer]:
        enriched_map = {e.name: e.description for e in enriched}
        for layer in layers:
            if layer.name in enriched_map and enriched_map[layer.name]:
                layer.description = enriched_map[layer.name]
        return layers

    def _build_deterministic_narrative(
        self,
        knowledge_model: KnowledgeModel,
        nodes: list[ArchitectureNode],
        layers: list[ArchitectureLayer],
    ) -> str:
        parts: list[str] = []

        primary = next((n for n in nodes if n.is_primary), nodes[0] if nodes else None)
        if primary:
            parts.append(
                f"The system described in this article is built around "
                f"{primary.name}, a {primary.entity_type} that serves as "
                f"the central component of the architecture."
            )

        if layers:
            layer_names = [l.name for l in sorted(layers, key=lambda l: l.order)]
            parts.append(
                f"The architecture is organized into {len(layers)} layers: "
                f"{', '.join(layer_names)}."
            )

        components = knowledge_model.named_entities
        if len(components) > 2:
            other_names = [
                e.name for e in components[:6] if e.name != (primary.name if primary else "")
            ]
            if other_names:
                parts.append(
                    f"Key components include: {', '.join(other_names[:5])}."
                )

        parts.append(
            f"The article describes {len(knowledge_model.relationships)} "
            f"relationships between these components, forming a connected "
            f"architectural graph."
        )

        return " ".join(parts)

    @staticmethod
    def _top_relationships(knowledge_model: KnowledgeModel) -> list[str]:
        rels: list[str] = []
        for rel in knowledge_model.relationships[:10]:
            direction = "↔" if rel.is_bidirectional else "→"
            rels.append(f"{rel.source} {direction} {rel.target}: {rel.label}")
        return rels

    @staticmethod
    def _slugify(text: str) -> str:
        slug = text.lower().strip()
        slug = re.sub(r"[^a-z0-9]+", "-", slug)
        return slug.strip("-")
