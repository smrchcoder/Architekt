"""Shared slug and entity-resolution utilities for section builders.

Centralizes the slug logic that was previously duplicated (with bugs) across
multiple builders. The key bug this fixes: ArchitectureBuilder de-duplicated
slug collisions by appending ``-{count}``, but FlowBuilder and TradeoffsBuilder
did not — producing dangling node IDs that didn't match any architecture node.

All builders MUST use these functions so that the same entity produces the
same slug everywhere.
"""

from __future__ import annotations

import re

from app.modules.extractor.models.knowledge_model import KnowledgeModel


def slugify(text: str) -> str:
    """Convert arbitrary text to a deterministic URL-safe slug.

    This is the single source of truth for slug generation. Every builder
    that produces node IDs or resolves entity references must use this.
    """
    slug = text.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


def build_name_to_slug_map(
    knowledge_model: KnowledgeModel,
    skip_layer_names: bool = False,
    layer_names: set[str] | None = None,
) -> dict[str, str]:
    """Build a name → slug map from the KnowledgeModel's named entities.

    Includes aliases so references using alternative names still resolve.

    Parameters
    ----------
    skip_layer_names
        If True, entities whose name matches a layer name are skipped
        (matching ArchitectureBuilder's behavior — layer-name entities are
        backfill artifacts, not real components).
    layer_names
        The set of layer names to skip. Required if ``skip_layer_names``
        is True.

    The collision de-duplication logic matches ArchitectureBuilder._build_nodes
    exactly: if two entities slugify to the same string, the second one gets
    ``-{count}`` appended. This ensures flow/tradeoff/problem builders produce
    slugs that match architecture node IDs.
    """
    if skip_layer_names and layer_names is None:
        layer_names = set()

    slug_map: dict[str, str] = {}
    seen_slugs: set[str] = set()

    for entity in knowledge_model.named_entities:
        if skip_layer_names and entity.name in (layer_names or set()):
            continue

        slug = slugify(entity.name)
        if slug in seen_slugs:
            slug = f"{slug}-{len(seen_slugs)}"
        seen_slugs.add(slug)

        slug_map[entity.name] = slug
        for alias in entity.aliases:
            # Only register alias if not already mapped to a different slug
            if alias not in slug_map:
                slug_map[alias] = slug

    return slug_map


def resolve_entity_refs_in_text(
    text: str, name_to_slug: dict[str, str]
) -> list[str]:
    """Find entity names mentioned in ``text`` and return their slugs.

    Performs case-insensitive substring matching. Returns slugs in the order
    they appear in ``name_to_slug`` (which preserves entity insertion order).

    Used by tradeoffs and problem_statement builders to resolve which
    architecture nodes are affected by a tradeoff or problem signal.
    """
    if not text:
        return []

    text_lower = text.lower()
    refs: list[str] = []
    seen: set[str] = set()

    for name, slug in name_to_slug.items():
        if name.lower() in text_lower and slug not in seen:
            refs.append(slug)
            seen.add(slug)

    return refs
