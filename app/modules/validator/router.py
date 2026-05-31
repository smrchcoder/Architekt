from __future__ import annotations

from fastapi import APIRouter

from app.modules.validator.schemas import ValidationResultRead


router = APIRouter(prefix="/validator", tags=["validator"])


@router.get("/health", response_model=ValidationResultRead)
def health():
    return ValidationResultRead(valid=True)
