from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.modules.orchestrator.service import OrchestratorService
from app.modules.orchestrator.schemas import (
    PipelineRunCreate,
    ProcessingRunRead,
)
from app.storage.db import get_db


router = APIRouter(prefix="/orchestrator", tags=["orchestrator"])


@router.get("/health", response_model=ProcessingRunRead)
def health():
    return ProcessingRunRead(
        run_id="noop",
        status="completed",
        current_step="health",
        progress_percent=100,
    )


@router.post("/runs", response_model=ProcessingRunRead, status_code=202)
def create_pipeline_run(
    payload: PipelineRunCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Create a new processing run and kick off the pipeline asynchronously."""
    service = OrchestratorService()
    run = service.create_pipeline_run(db, payload)
    background_tasks.add_task(
        service.run_pipeline,
        str(run.run_id),
    )
    db.refresh(run)
    return service.to_read_model(run)


@router.get("/runs/{run_id}", response_model=ProcessingRunRead)
def get_run(run_id: str, db: Session = Depends(get_db)):
    """Poll a processing run to check progress and retrieve the result when completed."""
    service = OrchestratorService()
    run = service.get_run(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="processing run not found")
    return service.to_read_model(run)
