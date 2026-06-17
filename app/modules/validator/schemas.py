from __future__ import annotations

from pydantic import BaseModel


class ValidationResultRead(BaseModel):
    valid: bool
    errors: list[str] | None = None


class ValidateRequest(BaseModel):
    raw_json: dict
