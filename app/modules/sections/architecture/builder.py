from __future__ import annotations

import json
from collections import Counter
from typing import Any

from app.core.config import settings
from app.llm import LLMClient
from app.logging_config import get_logger
from app.modules.extractor.models.knowledge_model import (
    EntityType,
    InteractionType,
    KnowledgeModel,
    SectionRelevance,
)
from app.modules.sections._shared.entity_resolver import (
    build_name_to_slug_map,
    slugify,
)
from app.modules.sections.architecture.prompts import (
    ARCHITECTURE_SYSTEM_PROMPT,
    build_architecture_user_prompt,
)
from app.modules.sections.architecture.schemas import (
    ArchitectureEdge,
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

        # Collect layer names so backfilled entities that are architectural
        # tiers (e.g. "Network Layer") are not rendered as nodes.
        layer_names: set[str] = {l.layer_name for l in knowledge_model.layer_signals}

        # ── Phase 1: deterministic node/layer extraction ────────────────
        nodes, name_to_slug = self._build_nodes(knowledge_model, layer_names)
        edges = self._build_edges(knowledge_model, name_to_slug, layer_names)
        layers = self._build_layers(knowledge_model, nodes)
        relationships_text = self._format_relationships(knowledge_model, layer_names)
        entities_json = json.dumps([
            {
                "name": n.name,
                "type": n.entity_type,
                "role": n.architecture_role,
                "importance": n.importance,
                "description": n.description,
            }
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
            log.opt.warning("architecture:phase_2_failed | falling_back_to_deterministic")

        # ── Phase 3: assemble ──────────────────────────────────────────
        if enrichment:
            narrative = enrichment.overview_narrative
            layers = self._merge_layer_enrichments(layers, enrichment.layers)
        else:
            narrative = self._build_deterministic_narrative(knowledge_model, nodes, layers)

        # Ensure the primary entity is an internal system, not the company
        nodes = self._correct_primary_entity(nodes)
        key_relationships = self._top_relationships(knowledge_model, layer_names)

        result = ArchitectureSection(
            overview_narrative=narrative,
            nodes=nodes,
            edges=edges,
            layers=layers,
            key_relationships=key_relationships,
        )
        return result

    # ── Phase 1 helpers ─────────────────────────────────────────────────

    def _build_nodes(
        self, knowledge_model: KnowledgeModel, layer_names: set[str]
    ) -> tuple[list[ArchitectureNode], dict[str, str]]:
        # Use the shared slug utility — same collision handling as all other builders
        name_to_slug = build_name_to_slug_map(
            knowledge_model, skip_layer_names=True, layer_names=layer_names
        )

        nodes: list[ArchitectureNode] = []
        for entity in knowledge_model.named_entities:
            if entity.name in layer_names:
                continue

            slug = name_to_slug.get(entity.name)
            if slug is None:
                continue

            layer = self._find_layer(entity.name, knowledge_model)
            nodes.append(
                ArchitectureNode(
                    id=slug,
                    name=entity.name,
                    entity_type=entity.entity_type,
                    description=entity.description,
                    layer=layer,
                    is_primary=entity.is_primary,
                    connected_to=[],
                    architecture_role=entity.architecture_role,
                    importance=entity.importance,
                    evidence=entity.evidence,
                )
            )

        # Populate connected_to from relationships
        for rel in knowledge_model.relationships:
            if rel.source in layer_names or rel.target in layer_names:
                continue
            src_id = name_to_slug.get(rel.source)
            tgt_id = name_to_slug.get(rel.target)
            if src_id and tgt_id:
                for node in nodes:
                    if node.id == src_id and tgt_id not in node.connected_to:
                        node.connected_to.append(tgt_id)

        # Populate parent_id from CONTAINS relationships (containment hierarchy)
        for rel in knowledge_model.relationships:
            if rel.interaction_type != InteractionType.CONTAINS:
                continue
            parent_slug = name_to_slug.get(rel.source)
            child_slug = name_to_slug.get(rel.target)
            if parent_slug and child_slug:
                for node in nodes:
                    if node.id == child_slug:
                        node.parent_id = parent_slug

        # Infer layers for unassigned entities based on connected neighbors
        nodes = self._infer_layers_for_unassigned(nodes, knowledge_model)

        # Default any remaining null-layer entities to "Infrastructure"
        for node in nodes:
            if node.layer is None:
                node.layer = "Infrastructure"

        return nodes, name_to_slug

    @staticmethod
    def _build_edges(
        knowledge_model: KnowledgeModel,
        name_to_slug: dict[str, str],
        layer_names: set[str],
    ) -> list[ArchitectureEdge]:
        """Build graph-ready ArchitectureEdge objects from KM relationships."""
        edges: list[ArchitectureEdge] = []
        seen: set[str] = set()
        for rel in knowledge_model.relationships:
            if rel.source in layer_names or rel.target in layer_names:
                continue
            src_slug = name_to_slug.get(rel.source)
            tgt_slug = name_to_slug.get(rel.target)
            if not src_slug or not tgt_slug:
                continue
            edge_id = f"rel_{src_slug}_{tgt_slug}"
            if edge_id in seen:
                continue
            seen.add(edge_id)
            edges.append(
                ArchitectureEdge(
                    id=edge_id,
                    source_id=src_slug,
                    target_id=tgt_slug,
                    interaction_type=rel.interaction_type,
                    label=rel.label,
                    is_bidirectional=rel.is_bidirectional,
                )
            )
        return edges

    @staticmethod
    def _infer_layers_for_unassigned(
        nodes: list[ArchitectureNode],
        knowledge_model: KnowledgeModel,
    ) -> list[ArchitectureNode]:
        """Assign layers to entities that have no explicit layer assignment.

        If an entity connects to entities in a known layer (via relationships),
        it inherits that layer. This prevents most entities from appearing
        as unlayered orphans in the diagram.
        """
        # Build name → layer from KM layer_signals
        known_layer: dict[str, str] = {}
        for layer in knowledge_model.layer_signals:
            for entity_name in layer.entities_in_layer:
                known_layer[entity_name] = layer.layer_name

        # Build name → node lookup
        name_map: dict[str, ArchitectureNode] = {n.name: n for n in nodes}

        # For unassigned nodes, check their connected_to neighbors
        for node in nodes:
            if node.layer is not None:
                continue  # Already assigned
            # Find neighbor layers via connected_to
            neighbor_layers: list[str] = []
            for connected_id in node.connected_to:
                neighbor = next(
                    (n for n in nodes if n.id == connected_id),
                    None,
                )
                if neighbor and neighbor.layer:
                    neighbor_layers.append(neighbor.layer)
            if neighbor_layers:
                # Assign the most common layer among neighbors
                from collections import Counter
                most_common = Counter(neighbor_layers).most_common(1)
                if most_common:
                    node.layer = most_common[0][0]
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
        return layers

    @staticmethod
    def _correct_primary_entity(nodes: list[ArchitectureNode]) -> list[ArchitectureNode]:
        """Ensure the primary entity is an internal system, not the company.

        The LLM often marks the company (e.g. "Netflix") as primary because
        it's central to the article's context. But for diagram purposes the
        primary entity should be the actual system (internal_system type).
        """
        # If current primary is not internal_system, find one to promote
        current_primary = next((n for n in nodes if n.is_primary), None)
        if current_primary and current_primary.entity_type != EntityType.INTERNAL_SYSTEM:
            internal_system = next(
                (n for n in nodes if n.entity_type == EntityType.INTERNAL_SYSTEM),
                None,
            )
            if internal_system:
                current_primary.is_primary = False
                internal_system.is_primary = True
        # If no primary at all, pick the first internal_system
        if not any(n.is_primary for n in nodes):
            internal_system = next(
                (n for n in nodes if n.entity_type == EntityType.INTERNAL_SYSTEM),
                None,
            )
            if internal_system:
                internal_system.is_primary = True
            elif nodes:
                nodes[0].is_primary = True
        return nodes

    @staticmethod
    def _format_relationships(knowledge_model: KnowledgeModel, layer_names: set[str]) -> str:
        lines: list[str] = []
        for rel in knowledge_model.relationships:
            if rel.source in layer_names or rel.target in layer_names:
                continue
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
    def _top_relationships(knowledge_model: KnowledgeModel, layer_names: set[str]) -> list[str]:
        rels: list[str] = []
        for rel in knowledge_model.relationships[:10]:
            if rel.source in layer_names or rel.target in layer_names:
                continue
            direction = "↔" if rel.is_bidirectional else "→"
            rels.append(f"{rel.source} {direction} {rel.target}: {rel.label}")
        return rels
