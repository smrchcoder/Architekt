from __future__ import annotations

from pydantic import BaseModel


class ProcessingRunRead(BaseModel):
    run_id: str
    status: str
