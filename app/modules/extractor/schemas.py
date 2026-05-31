from __future__ import annotations

from pydantic import BaseModel


class KnowledgeModelRead(BaseModel):
    id: str
    status: str
