from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import ValidationError

from app.modules.extractor.models.knowledge_model import (
    EntityType,
    KnowledgeModel,
)


class KnowledgeModelValidationError(ValueError):
    """Raised when a KnowledgeModel fails schema or semantic validation.

    Errors are aggregated as a list for structured error reporting in API
    responses and logs.
    """

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


@dataclass(frozen=True)
class KnowledgeModelValidationResult:
    """Result of a single validation run.

    Attributes:
        valid: True if no hard errors were found.
        errors: Human-readable error messages, keyed by field path.
        warnings: Quality checklist warnings (non-failing).
        failing_pass: If cross-pass validation identifies a specific pass
            as the source of errors (e.g. 'structure'), the pass name;
            None otherwise.
    """

    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    failing_pass: str | None = None


class KnowledgeModelValidator:
    """Validates KnowledgeModel instances for schema and semantic correctness.

    Runs three levels of validation:

    1. **Schema validation** (Pydantic-level): Ensures the raw JSON matches
       the KnowledgeModel type definition. Catches missing required fields,
       type mismatches, and constraint violations (min_length, max_length).

    2. **Semantic validation** (``validate()``): Checks business rules that
       Pydantic cannot express — unique entity/concept names, at most one
       primary internal system, and that all relationship/flow/layer/temporal
       references point to valid entity names.

    3. **Quality checklist** (``validate()``): Checks items from the
       Extraction Quality Checklist: no duplicate entities, stable IDs,
       importance scores, architecture roles, evidence preservation,
       flow-to-architecture linking, and meaningful layer names.

    4. **Cross-pass validation** (``validate_cross_pass()``): Checks
       referential integrity after merge — all structure-pass references
       (relationships, flow steps, layers, temporal signals) must match
       entities extracted in the recognition pass. Returns ``failing_pass``
       metadata so the orchestrator can retry the offending pass.

    Usage::

        validator = KnowledgeModelValidator()
        km = validator.validate_raw(raw_json_dict)    # raises if invalid
        result = validator.validate(km)               # semantic checks + quality
        cross = validator.validate_cross_pass(km)     # cross-pass integrity
    """

    # Generic layer names that should raise warnings
    _GENERIC_LAYER_NAMES = {
        "system layer", "other layer", "general layer", "misc layer",
        "default layer", "unnamed layer", "layer",
    }

    def validate_raw(self, raw_json: dict) -> KnowledgeModel:
        """Parse and validate raw JSON into a KnowledgeModel.

        Runs Pydantic model_validate first, then semantic validate().
        Catches ValidationError and converts it to a
        KnowledgeModelValidationError with field-path-prefixed messages.

        Args:
            raw_json: The raw JSON dictionary to parse.

        Returns:
            A fully parsed and validated KnowledgeModel instance.

        Raises:
            KnowledgeModelValidationError: If schema or semantic validation fails.
        """
        try:
            knowledge_model = KnowledgeModel.model_validate(raw_json)
        except ValidationError as exc:
            errors = [
                f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
                for error in exc.errors()
            ]
            raise KnowledgeModelValidationError(errors) from exc

        self.validate(knowledge_model)
        return knowledge_model

    def validate(self, knowledge_model: KnowledgeModel) -> KnowledgeModelValidationResult:
        """Run semantic validation and quality checklist checks.

        Semantic checks:
            - Unique entity names and concept terms (no duplicates)
            - At most one internal_system marked is_primary
            - All relationship source/target references exist in named_entities
            - All flow step actor/target references exist in named_entities
            - Flow step orders are unique within each FlowSequence
            - Layer entity references are validated (fuzzy match for layers)
            - Temporal signal before/after entity references are validated
              (fuzzy match with parenthetical qualifier stripping)

        Quality checklist checks (warnings, not errors):
            - No duplicate entities remain after canonicalization
            - Every entity has a stable ID
            - Every relationship has a stable ID
            - Every flow has a stable ID
            - Every tradeoff has a stable ID
            - Every concept has a stable ID
            - High-importance entities (>=7) have evidence
            - Every flow actor/target resolves to a known entity
            - Layer names are meaningful (not generic)
            - Architecture roles are assigned when possible

        Args:
            knowledge_model: The KnowledgeModel to validate.

        Returns:
            A KnowledgeModelValidationResult with semantic errors as
            ``errors`` and quality warnings as ``warnings``.

        Raises:
            KnowledgeModelValidationError: If hard validation errors are found.
        """
        errors: list[str] = []
        warnings: list[str] = []
        entity_names = [entity.name for entity in knowledge_model.named_entities]
        entity_name_set = set(entity_names)

        self._validate_unique_values("named_entities.name", entity_names, errors)
        self._validate_unique_values(
            "concept_definitions.term",
            [concept.term for concept in knowledge_model.concept_definitions],
            errors,
        )

        primary_internal_systems = [
            entity
            for entity in knowledge_model.named_entities
            if entity.entity_type == EntityType.INTERNAL_SYSTEM and entity.is_primary
        ]
        if len(primary_internal_systems) > 1:
            errors.append("Only one internal_system may be marked is_primary")

        for index, relationship in enumerate(knowledge_model.relationships):
            self._validate_reference(
                f"relationships[{index}].source",
                relationship.source,
                entity_name_set,
                warnings,
            )
            self._validate_reference(
                f"relationships[{index}].target",
                relationship.target,
                entity_name_set,
                warnings,
            )

        for seq_index, sequence in enumerate(knowledge_model.flow_sequences):
            seq_label = f"flow_sequences[{seq_index}]"
            flow_orders = [step.step_order for step in sequence.steps]
            self._validate_unique_values(
                f"{seq_label}.steps.step_order", flow_orders, errors,
            )
            for step_index, step in enumerate(sequence.steps):
                step_label = f"{seq_label}.steps[{step_index}]"
                self._validate_reference(
                    f"{step_label}.actor",
                    step.actor,
                    entity_name_set,
                    warnings,
                )
                if step.target:
                    self._validate_reference(
                        f"{step_label}.target",
                        step.target,
                        entity_name_set,
                        warnings,
                    )

        for index, layer in enumerate(knowledge_model.layer_signals):
            self._validate_unique_values(
                f"layer_signals[{index}].entities_in_layer",
                layer.entities_in_layer,
                warnings,
            )
            for entity_name in layer.entities_in_layer:
                self._validate_reference(
                    f"layer_signals[{index}].entities_in_layer",
                    entity_name,
                    entity_name_set,
                    warnings,
                    fuzzy=True,
                )

        for index, signal in enumerate(knowledge_model.temporal_signals):
            if signal.before_entity:
                before = self._normalize_temporal_entity(
                    signal.before_entity, entity_name_set
                )
                self._validate_reference(
                    f"temporal_signals[{index}].before_entity",
                    before,
                    entity_name_set,
                    warnings,
                    fuzzy=True,
                )
            if signal.after_entity:
                after = self._normalize_temporal_entity(
                    signal.after_entity, entity_name_set
                )
                self._validate_reference(
                    f"temporal_signals[{index}].after_entity",
                    after,
                    entity_name_set,
                    warnings,
                    fuzzy=True,
                )

        # ── Extraction Quality Checklist ────────────────────────────────
        quality_warnings = self._validate_quality_checklist(knowledge_model)
        warnings.extend(quality_warnings)

        if warnings:
            knowledge_model.extraction_warnings.extend(warnings)

        if errors:
            raise KnowledgeModelValidationError(errors)

        return KnowledgeModelValidationResult(
            valid=True,
            warnings=quality_warnings,
        )

    def _validate_quality_checklist(
        self, knowledge_model: KnowledgeModel
    ) -> list[str]:
        """Run the Extraction Quality Checklist and return warnings.

        Checks:
          1. No duplicate entities (via alias or fuzzy match)
          2. Stable IDs on all objects
          3. Importance scores on all entities
          4. Evidence on high-importance entities (>=7)
          5. Architecture roles on major entities
          6. Flow-to-architecture linking (flow actors to entities)
          7. Layer names are meaningful
          8. Concepts have evidence
        """
        warnings: list[str] = []
        entity_name_set = {e.name.lower(): e for e in knowledge_model.named_entities}

        # ── 1. Duplicate entity detection ───────────────────────────────
        for i, e1 in enumerate(knowledge_model.named_entities):
            for e2 in knowledge_model.named_entities[i + 1 :]:
                # Check if names overlap via alias or substring
                e1_aliases_lower = {a.lower() for a in e1.aliases}
                e2_aliases_lower = {a.lower() for a in e2.aliases}
                shared_aliases = e1_aliases_lower & e2_aliases_lower

                name_in_alias = e1.name.lower() in e2_aliases_lower or e2.name.lower() in e1_aliases_lower
                substring_match = (
                    len(e1.name) >= 4
                    and len(e2.name) >= 4
                    and (e1.name.lower() in e2.name.lower() or e2.name.lower() in e1.name.lower())
                )

                if name_in_alias or shared_aliases or substring_match:
                    warnings.append(
                        f"Potential duplicate entities remain after canonicalization: "
                        f"'{e1.name}' and '{e2.name}' (shared aliases or fuzzy match). "
                        f"Consider merging them."
                    )

        # ── 2. Stable IDs ───────────────────────────────────────────────
        for i, entity in enumerate(knowledge_model.named_entities):
            if not entity.id or entity.id == "ent_":
                warnings.append(f"named_entities[{i}] missing stable ID")
        for i, concept in enumerate(knowledge_model.concept_definitions):
            if not concept.id or concept.id == "con_":
                warnings.append(f"concept_definitions[{i}] missing stable ID")
        for i, rel in enumerate(knowledge_model.relationships):
            if not rel.id or rel.id == "rel_":
                warnings.append(f"relationships[{i}] missing stable ID")
        for i, flow in enumerate(knowledge_model.flow_sequences):
            if not flow.id or flow.id == "flow_":
                warnings.append(f"flow_sequences[{i}] missing stable ID")
        for i, tradeoff in enumerate(knowledge_model.tradeoff_signals):
            if not tradeoff.id or tradeoff.id == "trade_":
                warnings.append(f"tradeoff_signals[{i}] missing stable ID")

        # ── 3. Importance scores ────────────────────────────────────────
        for i, entity in enumerate(knowledge_model.named_entities):
            if entity.importance < 1 or entity.importance > 10:
                warnings.append(
                    f"named_entities[{i}] '{entity.name}' has invalid importance "
                    f"({entity.importance}), expected 1-10"
                )

        # ── 4. Evidence on high-importance entities ─────────────────────
        for i, entity in enumerate(knowledge_model.named_entities):
            if entity.importance >= 7 and not entity.evidence:
                warnings.append(
                    f"named_entities[{i}] '{entity.name}' has importance={entity.importance} "
                    f"but no evidence excerpt. Add evidence for UI traceability."
                )

        # ── 5. Architecture roles ───────────────────────────────────────
        null_role_entities = [
            e for e in knowledge_model.named_entities
            if e.architecture_role is None and e.entity_type != EntityType.CONCEPT
        ]
        if null_role_entities and len(null_role_entities) > len(knowledge_model.named_entities) * 0.5:
            warnings.append(
                f"{len(null_role_entities)}/{len(knowledge_model.named_entities)} entities "
                f"have no architecture_role. Consider assigning roles for better "
                f"visual classification."
            )

        # ── 6. Flow-to-architecture linking ─────────────────────────────
        entity_names_exact = {e.name for e in knowledge_model.named_entities}
        for seq_idx, seq in enumerate(knowledge_model.flow_sequences):
            for step_idx, step in enumerate(seq.steps):
                if step.actor not in entity_names_exact:
                    # Try fuzzy match
                    fuzzy_match = any(
                        step.actor.lower() in name.lower() or name.lower() in step.actor.lower()
                        for name in entity_names_exact
                    )
                    if not fuzzy_match:
                        warnings.append(
                            f"flow_sequences[{seq_idx}].steps[{step_idx}].actor "
                            f"'{step.actor}' does not resolve to any named entity. "
                            f"This breaks flow-to-architecture linking in the UI."
                        )
                if step.target and step.target not in entity_names_exact:
                    fuzzy_match = any(
                        step.target.lower() in name.lower() or name.lower() in step.target.lower()
                        for name in entity_names_exact
                    )
                    if not fuzzy_match:
                        warnings.append(
                            f"flow_sequences[{seq_idx}].steps[{step_idx}].target "
                            f"'{step.target}' does not resolve to any named entity. "
                            f"This breaks flow-to-architecture linking in the UI."
                        )

        # ── 7. Layer name quality ───────────────────────────────────────
        for i, layer in enumerate(knowledge_model.layer_signals):
            if layer.layer_name.lower() in self._GENERIC_LAYER_NAMES:
                warnings.append(
                    f"layer_signals[{i}] has generic layer name '{layer.layer_name}'. "
                    f"Use a more meaningful architectural boundary name."
                )

        # ── 8. Concept evidence ─────────────────────────────────────────
        for i, concept in enumerate(knowledge_model.concept_definitions):
            if not concept.evidence:
                warnings.append(
                    f"concept_definitions[{i}] '{concept.term}' has no evidence excerpt. "
                    f"Add evidence for UI traceability."
                )

        return warnings

    def validate_cross_pass(
        self, knowledge_model: KnowledgeModel
    ) -> KnowledgeModelValidationResult:
        """Validate referential integrity between recognition and structure passes.

        Checks that every entity reference in the structure pass (relationships,
        flow steps, layer entities, temporal before/after) resolves to a known
        entity name from the recognition pass. Layer and temporal references use
        substring fuzzy matching since LLMs often add qualifiers or omit exact
        component names.

        Returns ``failing_pass='structure'`` when errors are detected — this
        signals the orchestrator that Pass 2 should be retried (with the
        recognition entities as implicit context for entity names).

        Args:
            knowledge_model: The merged KnowledgeModel with entities from Pass 1
                and structure references from Pass 2.

        Returns:
            A KnowledgeModelValidationResult with errors if cross-pass references
            fail, and ``failing_pass='structure'`` when applicable.
        """
        errors: list[str] = []
        warnings: list[str] = []
        entity_name_set = {
            entity.name for entity in knowledge_model.named_entities
        }

        has_structure_error = False

        for index, relationship in enumerate(knowledge_model.relationships):
            if relationship.source not in entity_name_set:
                errors.append(
                    f"relationships[{index}].source references unknown entity '{relationship.source}'"
                )
                has_structure_error = True
            if relationship.target not in entity_name_set:
                errors.append(
                    f"relationships[{index}].target references unknown entity '{relationship.target}'"
                )
                has_structure_error = True

        for seq_index, sequence in enumerate(knowledge_model.flow_sequences):
            for step_index, step in enumerate(sequence.steps):
                label = f"flow_sequences[{seq_index}].steps[{step_index}]"
                if step.actor not in entity_name_set:
                    errors.append(
                        f"{label}.actor references unknown entity '{step.actor}'"
                    )
                    has_structure_error = True
                if step.target and step.target not in entity_name_set:
                    errors.append(
                        f"{label}.target references unknown entity '{step.target}'"
                    )
                    has_structure_error = True

        for index, layer in enumerate(knowledge_model.layer_signals):
            for entity_name in layer.entities_in_layer:
                matched = any(
                    name in entity_name or entity_name in name
                    for name in entity_name_set
                )
                if not matched:
                    errors.append(
                        f"layer_signals[{index}].entities_in_layer references unknown entity '{entity_name}'"
                    )
                    has_structure_error = True

        for index, signal in enumerate(knowledge_model.temporal_signals):
            if signal.before_entity:
                before = self._normalize_temporal_entity(
                    signal.before_entity, entity_name_set
                )
                if before not in entity_name_set:
                    matched = any(
                        name in before or before in name
                        for name in entity_name_set
                    )
                    if not matched:
                        errors.append(
                            f"temporal_signals[{index}].before_entity references unknown entity '{before}'"
                        )
                        has_structure_error = True
            if signal.after_entity:
                after = self._normalize_temporal_entity(
                    signal.after_entity, entity_name_set
                )
                if after not in entity_name_set:
                    matched = any(
                        name in after or after in name
                        for name in entity_name_set
                    )
                    if not matched:
                        errors.append(
                            f"temporal_signals[{index}].after_entity references unknown entity '{after}'"
                        )
                        has_structure_error = True

        if warnings:
            knowledge_model.extraction_warnings.extend(warnings)

        return KnowledgeModelValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            failing_pass="structure" if has_structure_error else None,
        )

    @staticmethod
    def _validate_reference(
        field_name: str,
        value: str,
        valid_values: set[str],
        errors: list[str],
        fuzzy: bool = False,
    ) -> None:
        """Check that a reference value exists in the set of known entities.

        In fuzzy mode, uses substring matching (useful for layer and temporal
        references where LLMs add qualifiers like "Durable Objects (previous
        runtime)"). In exact mode, requires an exact match.

        Args:
            field_name: Human-readable field path for error messages.
            value: The reference value to validate.
            valid_values: The set of known entity names.
            errors: List to append error messages to.
            fuzzy: If True, use substring matching instead of exact match.
        """
        if fuzzy:
            matched = any(
                valid in value or value in valid
                for valid in valid_values
            )
            if not matched:
                errors.append(f"{field_name} references unknown or unmatched entity '{value}'")
        elif value not in valid_values:
            errors.append(f"{field_name} references unknown entity '{value}'")

    @staticmethod
    def _validate_unique_values(
        field_name: str,
        values: list[str] | list[int],
        errors: list[str],
    ) -> None:
        """Check for duplicate values in a list, appending errors for each duplicate.

        Args:
            field_name: Human-readable field path for error messages.
            values: The list of values to check for duplicates.
            errors: List to append error messages to.
        """
        seen: set[str | int] = set()
        duplicates: set[str | int] = set()
        for value in values:
            if value in seen:
                duplicates.add(value)
            seen.add(value)
        for duplicate in sorted(duplicates, key=str):
            errors.append(f"{field_name} contains duplicate value '{duplicate}'")

    @staticmethod
    def _normalize_temporal_entity(
        value: str,
        entity_name_set: set[str],
    ) -> str:
        """Strip parenthetical qualifiers from temporal signal entity references.

        The LLM often writes values like '"Durable Objects (previous runtime)"'
        where the actual entity name is 'Durable Objects'. This method searches
        the known entity name set for a substring match and returns the matched
        canonical name.

        Args:
            value: The raw temporal signal entity reference.
            entity_name_set: The set of known entity names from the recognition pass.

        Returns:
            The matched canonical entity name if found, otherwise the original value.
        """
        for name in entity_name_set:
            if name in value:
                return name
        return value
