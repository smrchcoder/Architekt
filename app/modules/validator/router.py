from __future__ import annotations

from fastapi import APIRouter

from app.modules.validator.schemas import ValidateRequest, ValidationResultRead
from app.modules.validator.service import ValidatorService


router = APIRouter(prefix="/validator", tags=["validator"])


@router.get("/health", response_model=ValidationResultRead)
def health():
    return ValidationResultRead(valid=True)


@router.post("/validate", response_model=ValidationResultRead)
def validate(payload: ValidateRequest):
    service = ValidatorService()
    result = service.validate(payload.raw_json)
    return ValidationResultRead(**result)
