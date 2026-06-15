from __future__ import annotations

from app.modules.extractor.services.knowledge_model_validator import (
    KnowledgeModelValidator,
    KnowledgeModelValidationError,
)


class ValidatorService:
    def __init__(self) -> None:
        self._validator = KnowledgeModelValidator()

    def validate(self, raw_json: dict) -> dict:
        try:
            self._validator.validate_raw(raw_json)
        except KnowledgeModelValidationError as exc:
            return {"valid": False, "errors": exc.errors}
        return {"valid": True, "errors": None}
