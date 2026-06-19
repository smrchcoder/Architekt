from __future__ import annotations

import re

from app.modules.extractor.models.extraction_result import ExtractionResult
from app.modules.extractor.models.knowledge_model import (
    ArchitectureRole,
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

    Entity canonicalization: Duplicate entities (same thing referred to by
    different names) are consolidated into a single canonical entity with
    all alternative names stored as aliases. This prevents duplicate nodes
    in architecture graphs.

    Entity backfill: When Pass 2 (structure) references entities not found
    in Pass 1's inventory (common in dense articles where Pass 1 misses
    infrastructure/tool entities), the merger promotes them into the entity
    list as vendor_tool or external_tool entities. This reduces cross-pass
    validation failures without requiring a re-run of Pass 1.

    Deterministic IDs: All extracted objects receive stable machine-readable
    IDs derived from their content for use in visual systems (graph rendering,
    animations, viewport navigation, deep links, state persistence).

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
        Entity canonicalization deduplicates entities by merging aliases
        and consolidating duplicate references.

        Args:
            pass_1: The recognition extraction result (entities, concepts, etc.)
            pass_2: The structure extraction result (relationships, flows, etc.)
            pass_3: The reasoning extraction result (tradeoffs, constraints, etc.)
            cross_pass_warnings: Optional list of referential-integrity errors
                from the cross-pass validator that should be surfaced to
                downstream components.

        Returns:
            A fully composed KnowledgeModel with schema_version=3, ready for
            validation and section generation.
        """
        p1 = pass_1.data
        p2 = pass_2.data
        p3 = pass_3.data

        merged_warnings: list[str] = []
        merged_warnings.extend(p3.extraction_warnings)
        if cross_pass_warnings:
            merged_warnings.extend(cross_pass_warnings)

        # Step 1: Backfill entities from Pass 2 references
        named_entities = MergeService._backfill_entities(p1.named_entities, p2)

        # Step 2: Canonicalize entities — deduplicate and merge aliases
        canonicalization_warnings = []
        named_entities, name_map = MergeService._canonicalize_entities(
            named_entities, canonicalization_warnings
        )
        merged_warnings.extend(canonicalization_warnings)

        # Step 3: Ensure deterministic IDs on all objects
        named_entities = [MergeService._ensure_entity_id(e) for e in named_entities]
        concepts = [MergeService._ensure_concept_id(c) for c in p1.concept_definitions]
        relationships = [
            MergeService._ensure_relationship_id(r) for r in p2.relationships
        ]
        flow_sequences = [
            MergeService._ensure_flow_id(f) for f in p2.flow_sequences
        ]
        tradeoffs = [
            MergeService._ensure_tradeoff_id(t) for t in p3.tradeoff_signals
        ]

        # Step 4: Update structure references to use canonical entity names
        relationships = MergeService._remap_entity_refs_in_relationships(
            relationships, name_map
        )
        flow_sequences = MergeService._remap_entity_refs_in_flows(
            flow_sequences, name_map
        )

        return KnowledgeModel(
            schema_version=3,
            # Pass 1 — Recognition
            article_summary=p1.article_summary,
            core_problem=p1.core_problem,
            named_entities=named_entities,
            concept_definitions=concepts,
            key_quotes=p1.key_quotes,
            problem_signals=p1.problem_signals,
            scale_context_signals=p1.scale_context_signals,
            # Pass 2 — Structure
            relationships=relationships,
            flow_sequences=flow_sequences,
            layer_signals=p2.layer_signals,
            temporal_signals=p2.temporal_signals,
            # Pass 3 — Reasoning
            tradeoff_signals=tradeoffs,
            constraint_signals=p3.constraint_signals,
            # Computed
            confidence_score=min(
                pass_1.combined_score,
                pass_2.combined_score,
                pass_3.combined_score,
            ),
            extraction_warnings=merged_warnings,
        )

    # ── Entity Canonicalization ────────────────────────────────────────

    @staticmethod
    def _canonicalize_entities(
        entities: list[NamedEntity],
        warnings: list[str],
    ) -> tuple[list[NamedEntity], dict[str, str]]:
        """Deduplicate entities and build a name → canonical name mapping.

        Two entities are considered duplicates when:
        1. One name appears in the other's aliases list
        2. One name is a case-insensitive substring of the other
           (e.g. "Cassandra" and "Apache Cassandra")
        3. They share a common alias

        When duplicates are found, the entity with the longer, more precise
        name is kept as canonical. All alternative names (the discarded name
        plus both aliases lists) are merged into the canonical entity's
        aliases. The other entity's attributes are merged (higher importance,
        more specific role, combined evidence).

        Returns:
            A tuple of (deduplicated_entities, name_map) where name_map
            maps every known name (including aliases) to the canonical name.
        """
        if not entities:
            return [], {}

        # Sort by name length descending — longer names are more precise
        sorted_entities = sorted(entities, key=lambda e: len(e.name), reverse=True)
        canonical: dict[str, NamedEntity] = {}  # canonical name → entity
        name_map: dict[str, str] = {}  # any name/alias → canonical name

        for entity in sorted_entities:
            # Check if this entity matches any existing canonical
            matched_canonical_name = None
            for canon_name, canon_entity in canonical.items():
                if MergeService._is_duplicate_of(entity, canon_entity):
                    matched_canonical_name = canon_name
                    break

            if matched_canonical_name:
                # Merge into existing canonical entity
                canon = canonical[matched_canonical_name]
                MergeService._merge_entities(canon, entity, warnings)
                # Map this entity's name (and all aliases) to canonical
                name_map[entity.name] = matched_canonical_name
                for alias in entity.aliases:
                    name_map[alias] = matched_canonical_name
            else:
                # This is a new canonical entity
                canonical[entity.name] = entity
                name_map[entity.name] = entity.name
                for alias in entity.aliases:
                    name_map[alias] = entity.name

        return list(canonical.values()), name_map

    @staticmethod
    def _is_duplicate_of(a: NamedEntity, b: NamedEntity) -> bool:
        """Check if entity ``a`` refers to the same thing as entity ``b``."""
        # Exact name match
        if a.name.lower() == b.name.lower():
            return True
        # One name is in the other's aliases
        if a.name.lower() in (alias.lower() for alias in b.aliases):
            return True
        if b.name.lower() in (alias.lower() for alias in a.aliases):
            return True
        # Shared alias
        a_aliases_lower = {alias.lower() for alias in a.aliases}
        b_aliases_lower = {alias.lower() for alias in b.aliases}
        if a_aliases_lower & b_aliases_lower:
            return True
        # Substring match: one name contains the other
        a_lower = a.name.lower()
        b_lower = b.name.lower()
        if len(a_lower) >= 4 and len(b_lower) >= 4:
            if a_lower in b_lower or b_lower in a_lower:
                return True
        return False

    @staticmethod
    def _merge_entities(
        canonical: NamedEntity, duplicate: NamedEntity, warnings: list[str],
    ) -> None:
        """Merge a duplicate entity into the canonical entity in-place."""
        # Collect all aliases: canonical's + duplicate's name + duplicate's aliases
        all_aliases: list[str] = list(canonical.aliases)
        if duplicate.name.lower() != canonical.name.lower():
            all_aliases.append(duplicate.name)
        for alias in duplicate.aliases:
            if alias.lower() != canonical.name.lower():
                all_aliases.append(alias)

        # Deduplicate aliases (case-insensitive, keep first occurrence)
        seen_aliases: set[str] = set()
        deduped_aliases: list[str] = []
        for alias in all_aliases:
            alias_lower = alias.lower()
            if alias_lower != canonical.name.lower() and alias_lower not in seen_aliases:
                seen_aliases.add(alias_lower)
                deduped_aliases.append(alias)
        canonical.aliases = deduped_aliases

        # Merge importance — keep the higher score
        if duplicate.importance > canonical.importance:
            canonical.importance = duplicate.importance

        # Merge architecture_role — prefer the more specific (non-None) one
        if canonical.architecture_role is None and duplicate.architecture_role is not None:
            canonical.architecture_role = duplicate.architecture_role

        # Merge evidence — prefer the longer/more detailed excerpt
        if duplicate.evidence and (
            canonical.evidence is None
            or len(duplicate.evidence) > len(canonical.evidence)
        ):
            canonical.evidence = duplicate.evidence

        # Merge is_primary
        if duplicate.is_primary:
            canonical.is_primary = True

        # Merge description — prefer the longer one
        if len(duplicate.description) > len(canonical.description):
            canonical.description = duplicate.description

        # Merge first_mention_context — prefer the longer one
        if len(duplicate.first_mention_context) > len(canonical.first_mention_context):
            canonical.first_mention_context = duplicate.first_mention_context

        warnings.append(
            f"Canonicalized entity '{duplicate.name}' into '{canonical.name}' "
            f"(merged aliases: {[a for a in deduped_aliases if a != duplicate.name]})"
        )

    @staticmethod
    def _remap_entity_refs_in_relationships(
        relationships: list, name_map: dict[str, str]
    ) -> list:
        """Update relationship source/target names to use canonical names."""
        for rel in relationships:
            if rel.source in name_map and name_map[rel.source] != rel.source:
                rel.source = name_map[rel.source]
            if rel.target in name_map and name_map[rel.target] != rel.target:
                rel.target = name_map[rel.target]
            # Regenerate ID if names changed
            if rel.id:
                expected = MergeService._slugify(f"rel_{rel.source}_{rel.target}")
                if rel.id != expected:
                    rel.id = expected
        return relationships

    @staticmethod
    def _remap_entity_refs_in_flows(
        flow_sequences: list, name_map: dict[str, str]
    ) -> list:
        """Update flow step actor/target names to use canonical names."""
        for seq in flow_sequences:
            for step in seq.steps:
                if step.actor in name_map and name_map[step.actor] != step.actor:
                    step.actor = name_map[step.actor]
                if step.target and step.target in name_map and name_map[step.target] != step.target:
                    step.target = name_map[step.target]
        return flow_sequences

    # ── Entity Backfill ────────────────────────────────────────────────

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
                        id=MergeService._slugify(f"ent_{name}"),
                        name=name,
                        entity_type=MergeService._infer_entity_type(name),
                        architecture_role=MergeService._infer_architecture_role(name),
                        importance=3,  # Default moderate-low for backfilled
                        description=f"Referenced in the article's architecture as {name}",
                        is_primary=False,
                        first_mention_context=f"Referenced as {name}",
                        aliases=[],
                        evidence=None,
                    )
                )

        return new_entities

    # ── Deterministic ID Generation ────────────────────────────────────

    @staticmethod
    def _slugify(text: str) -> str:
        """Convert arbitrary text to a deterministic slug.

        Lowercases, replaces non-alphanumeric characters with underscores,
        and collapses multiple underscores. Produces stable IDs that can
        be reproduced across re-extractions of the same content.
        """
        slug = text.lower()
        slug = re.sub(r"[^a-z0-9_]", "_", slug)
        slug = re.sub(r"_+", "_", slug)
        slug = slug.strip("_")
        return slug

    @staticmethod
    def _ensure_entity_id(entity: NamedEntity) -> NamedEntity:
        """Ensure the entity has a deterministic ID."""
        if not entity.id or entity.id == "ent_":
            entity.id = MergeService._slugify(f"ent_{entity.name}")
        return entity

    @staticmethod
    def _ensure_concept_id(concept) -> object:
        """Ensure the concept has a deterministic ID."""
        if not concept.id or concept.id == "con_":
            concept.id = MergeService._slugify(f"con_{concept.term}")
        return concept

    @staticmethod
    def _ensure_relationship_id(rel) -> object:
        """Ensure the relationship has a deterministic ID."""
        if not rel.id or rel.id == "rel_":
            rel.id = MergeService._slugify(f"rel_{rel.source}_{rel.target}")
        return rel

    @staticmethod
    def _ensure_flow_id(flow) -> object:
        """Ensure the flow sequence has a deterministic ID."""
        if not flow.id or flow.id == "flow_":
            flow.id = MergeService._slugify(f"flow_{flow.flow_name}")
        return flow

    @staticmethod
    def _ensure_tradeoff_id(tradeoff) -> object:
        """Ensure the tradeoff has a deterministic ID."""
        if not tradeoff.id or tradeoff.id == "trade_":
            # Use first ~60 chars of description as the unique basis
            short = tradeoff.description[:60]
            tradeoff.id = MergeService._slugify(f"trade_{short}")
        return tradeoff

    # ── Type Inference ─────────────────────────────────────────────────

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

    @staticmethod
    def _infer_architecture_role(name: str) -> ArchitectureRole | None:
        """Infer architecture role from name patterns for backfilled entities."""
        name_lower = name.lower()

        if any(kw in name_lower for kw in ["db", "database", "store", "sql", "postgres", "mysql", "redis", "cassandra", "mongodb"]):
            return ArchitectureRole.DATASTORE
        if any(kw in name_lower for kw in ["cache", "memcached"]):
            return ArchitectureRole.CACHE
        if any(kw in name_lower for kw in ["queue", "kafka", "rabbit", "pubsub", "bus", "topic"]):
            return ArchitectureRole.QUEUE
        if any(kw in name_lower for kw in ["worker", "consumer"]):
            return ArchitectureRole.WORKER
        if any(kw in name_lower for kw in ["scheduler", "cron", "periodic"]):
            return ArchitectureRole.SCHEDULER
        if any(kw in name_lower for kw in ["api", "gateway", "ingress", "endpoint"]):
            return ArchitectureRole.API
        if any(kw in name_lower for kw in ["proxy", "lb", "load balancer"]):
            return ArchitectureRole.PROXY
        if any(kw in name_lower for kw in ["orchestrator", "coordinator", "controller"]):
            return ArchitectureRole.ORCHESTRATOR
        if any(kw in name_lower for kw in ["agent"]):
            return ArchitectureRole.AGENT
        if any(kw in name_lower for kw in ["stream", "flink", "spark streaming"]):
            return ArchitectureRole.STREAM_PROCESSOR
        if any(kw in name_lower for kw in ["client", "sdk", "frontend", "ui"]):
            return ArchitectureRole.CLIENT
        if any(kw in name_lower for kw in ["batch", "etl", "job"]):
            return ArchitectureRole.BATCH_JOB
        if any(kw in name_lower for kw in ["service", "server", "backend"]):
            return ArchitectureRole.SERVICE
        if any(kw in name_lower for kw in ["dns", "cdn", "monitor", "deploy", "infra"]):
            return ArchitectureRole.INFRASTRUCTURE_COMPONENT

        return None
