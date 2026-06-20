from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.logging_config import get_logger
from app.modules.extractor.services.extractor_service import KnowledgeExtractor
from app.modules.extractor.services.knowledge_model_validator import (
    KnowledgeModelValidator,
)
from app.modules.extractor.services.overview_section_builder import (
    OverviewSectionBuilder,
)
from app.modules.ingestion.schema.article_schema import ArticleCreate
from app.modules.ingestion.services.ingestion_service import IngestionService
from app.modules.orchestrator.schemas import (
    PipelineRunCreate,
    ProcessingRunRead,
)
from app.modules.sections.architecture.builder import ArchitectureBuilder
from app.modules.sections.flow.builder import FlowBuilder
from app.modules.sections.key_concepts.builder import KeyConceptsBuilder
from app.modules.sections.problem_statement.builder import ProblemStatementBuilder
from app.modules.sections.tradeoffs.builder import TradeoffsBuilder
from app.storage.db import SessionLocal
from app.storage.models import ProcessingRun


_log = get_logger(__name__)

STEP_INGESTION = "ingestion"
STEP_MULTI_PASS_EXTRACTION = "multi_pass_extraction"
STEP_MERGE_VALIDATION = "merge_validation"

STEP_OVERVIEW = "overview"
STEP_KEY_CONCEPTS = "key_concepts"
STEP_PROBLEM = "problem_statement"
STEP_ARCHITECTURE = "architecture"
STEP_FLOW = "flow"
STEP_TRADEOFFS = "tradeoffs"

PIPELINE_STEPS = [
    STEP_INGESTION,
    STEP_MULTI_PASS_EXTRACTION,
    STEP_MERGE_VALIDATION,
    STEP_OVERVIEW,
    STEP_KEY_CONCEPTS,
    STEP_PROBLEM,
    STEP_ARCHITECTURE,
    STEP_FLOW,
    STEP_TRADEOFFS,
]

SECTION_SLOT_TO_COLUMN: dict[str, str] = {
    "overview": "section_1_json",
    "key_concepts": "section_2_json",
    "problem_statement": "section_3_json",
    "architecture": "section_4_json",
    "flow": "section_5_json",
    "tradeoffs": "section_6_json",
}

_STEP_PROGRESS: dict[str, int] = {
    STEP_INGESTION: 5,
    STEP_MULTI_PASS_EXTRACTION: 15,
    STEP_MERGE_VALIDATION: 25,
    STEP_OVERVIEW: 35,
    STEP_KEY_CONCEPTS: 45,
    STEP_PROBLEM: 53,
    STEP_ARCHITECTURE: 61,
    STEP_FLOW: 69,
    STEP_TRADEOFFS: 77,
}


class OrchestratorService:
    def __init__(
        self,
        ingestion_service: IngestionService | None = None,
        knowledge_extractor: KnowledgeExtractor | None = None,
        knowledge_validator: KnowledgeModelValidator | None = None,
        overview_builder: OverviewSectionBuilder | None = None,
        key_concepts_builder: KeyConceptsBuilder | None = None,
        problem_builder: ProblemStatementBuilder | None = None,
        architecture_builder: ArchitectureBuilder | None = None,
        flow_builder: FlowBuilder | None = None,
        tradeoffs_builder: TradeoffsBuilder | None = None,
    ) -> None:
        self.ingestion_service = ingestion_service or IngestionService()
        self.knowledge_extractor = knowledge_extractor or KnowledgeExtractor()
        self.knowledge_validator = knowledge_validator or KnowledgeModelValidator()
        self.section_builders = {
            "overview": overview_builder or OverviewSectionBuilder(),
            "key_concepts": key_concepts_builder or KeyConceptsBuilder(),
            "problem_statement": problem_builder or ProblemStatementBuilder(),
            "architecture": architecture_builder or ArchitectureBuilder(),
            "flow": flow_builder or FlowBuilder(),
            "tradeoffs": tradeoffs_builder or TradeoffsBuilder(),
        }

    def create_pipeline_run(
        self, db: Session, payload: PipelineRunCreate
    ) -> ProcessingRun:
        run = ProcessingRun(
            status="queued",
            current_step="queued",
            progress_percent=0,
            request_payload=payload.model_dump(mode="json"),
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        _log.bind(run_id=str(run.run_id)).info(
            "pipeline_run_created | source_url=%s | has_raw_text=%s",
            payload.source_url or "none",
            payload.raw_text is not None,
        )
        return run

    def run_pipeline(self, run_id: str) -> None:
        """Execute the full pipeline: ingestion → extraction → validation → sections."""
        log = _log.bind(run_id=run_id)
        log.info("pipeline_started | steps_total=%d", len(PIPELINE_STEPS))

        db = SessionLocal()
        try:
            run = self._require_run(db, run_id)
            payload = PipelineRunCreate.model_validate(run.request_payload or {})

            self._mark_running(db, run_id, STEP_INGESTION, 5)
            article = self._with_retry(
                func=self.ingestion_service.ingest_article,
                step_name=STEP_INGESTION,
                db=db,
                payload=ArticleCreate(
                    source_url=payload.source_url,
                    raw_text=payload.raw_text,
                    source_title=payload.source_title,
                    source_domain=payload.source_domain,
                ),
                max_attempts=3,
                run_id=run_id,
            )

            self._update_run(
                db, run_id,
                current_step=STEP_MULTI_PASS_EXTRACTION, progress_percent=15,
                article_id=article.article_id,
            )

            knowledge_record = self._with_retry(
                func=self.knowledge_extractor.extract_knowledge_model,
                step_name=STEP_MULTI_PASS_EXTRACTION,
                db=db,
                article_id=article.article_id,
                max_attempts=2,
                run_id=run_id,
            )

            self._update_run(
                db, run_id,
                current_step=STEP_MERGE_VALIDATION, progress_percent=25,
            )

            knowledge_model = self.knowledge_validator.validate_raw(
                knowledge_record.raw_json
            )

            run = self._require_run(db, run_id)
            db.commit()

            # ── Section Builders ──────────────────────────────────────────
            section_pipeline = [
                (STEP_OVERVIEW, "overview", 35, 2),
                (STEP_KEY_CONCEPTS, "key_concepts", 45, 2),
                (STEP_PROBLEM, "problem_statement", 53, 2),
                (STEP_ARCHITECTURE, "architecture", 61, 2),
                (STEP_FLOW, "flow", 69, 2),
                (STEP_TRADEOFFS, "tradeoffs", 77, 2),
            ]

            for step_name, slot, progress, max_attempts in section_pipeline:
                builder = self.section_builders.get(slot)
                if builder is None:
                    continue
                self._update_run(db, run_id, step_name, progress)
                self._run_section(
                    db=db,
                    run_id=run_id,
                    step_name=step_name,
                    builder=builder,
                    section_slot=slot,
                    knowledge_model=knowledge_model,
                    article=article,
                    max_attempts=max_attempts,
                )

            self._complete_run(db, run_id)
            log.info("pipeline_complete")

        except Exception as exc:
            db.rollback()
            log.opt.error("pipeline_failed | error=%s", str(exc))
            self._fail_run(db, run_id, str(exc))
        finally:
            db.close()

    def get_run(self, db: Session, run_id: str) -> ProcessingRun | None:
        return db.get(ProcessingRun, run_id)

    def recover_interrupted_runs(self, db: Session) -> int:
        """Mark runs left in queued/running as failed after a process restart.

        The current pipeline is executed via FastAPI BackgroundTasks, which are
        process-local. If the server restarts while work is in flight, those
        tasks are not resumed automatically. Without recovery, clients can poll
        forever against runs that will never complete.
        """
        active_runs = db.execute(
            select(ProcessingRun).where(
                ProcessingRun.status.in_(("queued", "running"))
            )
        ).scalars().all()

        if not active_runs:
            return 0

        recovered_at = datetime.now(timezone.utc)
        for run in active_runs:
            run.status = "failed"
            run.current_step = "failed"
            run.error_message = (
                "Run was interrupted by an application restart before completion. "
                "Please create a new run."
            )
            run.updated_at = recovered_at

        db.commit()
        return len(active_runs)

    def to_read_model(self, run: ProcessingRun) -> ProcessingRunRead:
        return ProcessingRunRead(
            run_id=run.run_id,
            status=run.status,
            current_step=run.current_step,
            progress_percent=run.progress_percent,
            article_id=run.article_id,
            overview=run.section_1_json,
            key_concepts=run.section_2_json,
            problem_statement=run.section_3_json,
            architecture=run.section_4_json,
            flow=run.section_5_json,
            tradeoffs=run.section_6_json,
            error_message=run.error_message,
            created_at=run.created_at,
            updated_at=run.updated_at,
        )

    # ── internal helpers ─────────────────────────────────────────────────

    def _run_section(
        self,
        db: Session,
        run_id: str,
        step_name: str,
        builder,
        section_slot: str,
        knowledge_model,
        article,
        max_attempts: int = 2,
    ) -> None:
        result = self._with_retry(
            func=builder.build,
            step_name=step_name,
            knowledge_model=knowledge_model,
            article=article,
            max_attempts=max_attempts,
            run_id=run_id,
        )
        self._save_section(db, run_id, section_slot, result)

    def _save_section(
        self, db: Session, run_id: str, slot: str, result
    ) -> None:
        run = self._require_run(db, run_id)
        col = SECTION_SLOT_TO_COLUMN.get(slot)
        if col is None:
            raise ValueError(f"Unknown section slot: {slot}")
        if not hasattr(run, col):
            raise ValueError(f"Unknown section column: {col}")
        data = result.model_dump(mode="json") if result is not None else None
        setattr(run, col, data)
        db.commit()

    def _with_retry(
        self,
        func,
        step_name: str,
        run_id: str,
        max_attempts: int = 2,
        **kwargs: Any,
    ) -> Any:
        log = _log.bind(run_id=run_id, step=step_name)
        for attempt in range(1, max_attempts + 1):
            try:
                return func(**kwargs)
            except Exception:
                if attempt == max_attempts:
                    log.opt.error(
                        "step_retry_exhausted | attempts=%d/%d",
                        attempt, max_attempts,
                    )
                    raise
                log.warning(
                    "step_retry | attempt=%d/%d",
                    attempt, max_attempts,
                )
                if "db" in kwargs:
                    kwargs["db"].rollback()
                db = SessionLocal()
                try:
                    self._update_run(
                        db,
                        run_id,
                        current_step=f"{step_name}_retry_{attempt}",
                        progress_percent=self._progress_for(
                            step_name, attempt, max_attempts
                        ),
                    )
                finally:
                    db.close()
                time.sleep(min(2 ** attempt, 10))

    @staticmethod
    def _progress_for(step_name: str, attempt: int, _max_attempts: int) -> int:
        base = _STEP_PROGRESS.get(step_name, 50)
        return base + (attempt * 2)

    def _mark_running(
        self, db: Session, run_id: str, current_step: str, progress_percent: int
    ) -> None:
        run = self._require_run(db, run_id)
        run.status = "running"
        run.current_step = current_step
        run.progress_percent = progress_percent
        run.updated_at = datetime.now(timezone.utc)
        db.commit()

    def _update_run(
        self,
        db: Session,
        run_id: str,
        current_step: str,
        progress_percent: int,
        article_id: str | None = None,
    ) -> None:
        run = self._require_run(db, run_id)
        run.current_step = current_step
        run.progress_percent = progress_percent
        if article_id is not None:
            run.article_id = article_id
        run.updated_at = datetime.now(timezone.utc)
        db.commit()

    def _complete_run(self, db: Session, run_id: str) -> None:
        run = self._require_run(db, run_id)
        run.status = "completed"
        run.current_step = "completed"
        run.progress_percent = 100
        run.error_message = None
        run.updated_at = datetime.now(timezone.utc)
        db.commit()

    def _fail_run(self, db: Session, run_id: str, error_message: str) -> None:
        run = self._require_run(db, run_id)
        run.status = "failed"
        run.current_step = "failed"
        run.error_message = error_message
        run.updated_at = datetime.now(timezone.utc)
        db.commit()

    @staticmethod
    def _require_run(db: Session, run_id: str) -> ProcessingRun:
        run = db.get(ProcessingRun, run_id)
        if run is None:
            raise LookupError("processing run not found")
        return run
