from __future__ import annotations

from fastapi import APIRouter

from app.modules.orchestrator.schemas import ProcessingRunRead


router = APIRouter(prefix="/orchestrator", tags=["orchestrator"])


@router.get("/health", response_model=ProcessingRunRead)
def health():
    return ProcessingRunRead(run_id="noop", status="ok")

