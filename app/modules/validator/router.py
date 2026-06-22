from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.security import require_admin_api_key
from app.modules.validator.schemas import ValidateRequest, ValidationResultRead
from app.modules.validator.service import ValidatorService


router = APIRouter(prefix="/validator", tags=["validator"])


@router.get("/health", response_model=ValidationResultRead)
def health():
    return ValidationResultRead(valid=True)


@router.post("/validate", response_model=ValidationResultRead)
def validate(
    payload: ValidateRequest,
    _: None = Depends(require_admin_api_key),
):
    service = ValidatorService()
    result = service.validate(payload.raw_json)
    return ValidationResultRead(**result)
