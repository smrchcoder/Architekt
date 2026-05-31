from __future__ import annotations

from pydantic import BaseModel


class ValidationResultRead(BaseModel):
    valid: bool

