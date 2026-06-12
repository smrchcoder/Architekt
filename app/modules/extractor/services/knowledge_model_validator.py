from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import ValidationError

from app.modules.extractor.models.knowledge_model import (
    EntityType,
    KnowledgeModel,
)


class KnowledgeModelValidationError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


@dataclass(frozen=True)
class KnowledgeModelValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)


class KnowledgeModelValidator:
    def validate_raw(self, raw_json: dict) -> KnowledgeModel:
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
        errors: list[str] = []
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
                errors,
            )
            self._validate_reference(
                f"relationships[{index}].target",
                relationship.target,
                entity_name_set,
                errors,
            )

        flow_orders = [step.step_order for step in knowledge_model.flow_sequences]
        self._validate_unique_values("flow_sequences.step_order", flow_orders, errors)
        for index, step in enumerate(knowledge_model.flow_sequences):
            self._validate_reference(
                f"flow_sequences[{index}].actor",
                step.actor,
                entity_name_set,
                errors,
            )
            if step.target:
                self._validate_reference(
                    f"flow_sequences[{index}].target",
                    step.target,
                    entity_name_set,
                    errors,
                )

        for index, layer in enumerate(knowledge_model.layer_signals):
            self._validate_unique_values(
                f"layer_signals[{index}].entities_in_layer",
                layer.entities_in_layer,
                errors,
            )
            for entity_name in layer.entities_in_layer:
                self._validate_reference(
                    f"layer_signals[{index}].entities_in_layer",
                    entity_name,
                    entity_name_set,
                    errors,
                )

        for index, signal in enumerate(knowledge_model.temporal_signals):
            if signal.before_entity:
                self._validate_reference(
                    f"temporal_signals[{index}].before_entity",
                    signal.before_entity,
                    entity_name_set,
                    errors,
                )
            if signal.after_entity:
                self._validate_reference(
                    f"temporal_signals[{index}].after_entity",
                    signal.after_entity,
                    entity_name_set,
                    errors,
                )

        if errors:
            raise KnowledgeModelValidationError(errors)

        return KnowledgeModelValidationResult(valid=True)

    @staticmethod
    def _validate_reference(
        field_name: str,
        value: str,
        valid_values: set[str],
        errors: list[str],
    ) -> None:
        if value not in valid_values:
            errors.append(f"{field_name} references unknown entity '{value}'")

    @staticmethod
    def _validate_unique_values(
        field_name: str,
        values: list[str] | list[int],
        errors: list[str],
    ) -> None:
        seen: set[str | int] = set()
        duplicates: set[str | int] = set()
        for value in values:
            if value in seen:
                duplicates.add(value)
            seen.add(value)
        for duplicate in sorted(duplicates, key=str):
            errors.append(f"{field_name} contains duplicate value '{duplicate}'")
