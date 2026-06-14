from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.modules.extractor.services.extractor_service import KnowledgeExtractor
from app.modules.extractor.services.knowledge_model_validator import (
    KnowledgeModelValidator,
)
from app.modules.extractor.services.overview_section_builder import (
    OverviewSectionBuilder,
)
from app.modules.sections.problem_statement.builder import (
    ProblemStatementBuilder,
)
from app.modules.ingestion.schema.article_schema import ArticleCreate
from app.modules.ingestion.services.ingestion_service import IngestionService
from app.modules.orchestrator.schemas import (
    PipelineRunCreate,
    ProcessingRunRead,
)
from app.storage.db import SessionLocal
from app.storage.models import ProcessingRun


STEP_INGESTION = "ingestion"
STEP_EXTRACTION = "knowledge_extraction"
STEP_VALIDATION = "knowledge_validation"

STEP_SECTION_1_OVERVIEW = "section_1_overview"
STEP_SECTION_2_KEY_CONCEPTS = "section_2_key_concepts"
STEP_SECTION_3_PROBLEM = "section_3_problem_statement"
STEP_SECTION_4_ARCHITECTURE = "section_4_architecture_overview"
STEP_SECTION_5_FLOW = "section_5_end_to_end_flow"
STEP_SECTION_6_TRADEOFFS = "section_6_tradeoffs_key_learnings"

PIPELINE_STEPS = [
    STEP_INGESTION,
    STEP_EXTRACTION,
    STEP_VALIDATION,
    STEP_SECTION_1_OVERVIEW,
    STEP_SECTION_2_KEY_CONCEPTS,
    STEP_SECTION_3_PROBLEM,
    STEP_SECTION_4_ARCHITECTURE,
    STEP_SECTION_5_FLOW,
    STEP_SECTION_6_TRADEOFFS,
]


class OrchestratorService:
    def __init__(
        self,
        ingestion_service: IngestionService | None = None,
        knowledge_extractor: KnowledgeExtractor | None = None,
        knowledge_validator: KnowledgeModelValidator | None = None,
        section_1_builder: OverviewSectionBuilder | None = None,
        section_2_builder: Any | None = None,
        section_3_builder: Any | None = None,
        section_4_builder: Any | None = None,
        section_5_builder: Any | None = None,
        section_6_builder: Any | None = None,
    ) -> None:
        self.ingestion_service = ingestion_service or IngestionService()
        self.knowledge_extractor = knowledge_extractor or KnowledgeExtractor()
        self.knowledge_validator = knowledge_validator or KnowledgeModelValidator()
        self.section_builders = {
            "section_1": section_1_builder or OverviewSectionBuilder(),
            "section_2": section_2_builder,
            "section_3": section_3_builder or ProblemStatementBuilder(),
            "section_4": section_4_builder,
            "section_5": section_5_builder,
            "section_6": section_6_builder,
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
        return run

    def run_pipeline(self, run_id: str) -> None:
        """Execute the full pipeline: ingestion → extraction → validation → sections 1-6."""
        db = SessionLocal()
        try:
            run = self._require_run(db, run_id)
            payload = PipelineRunCreate.model_validate(run.request_payload or {})

            # ── Ingestion ────────────────────────────────────────────────
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

            # ── Knowledge Extraction ─────────────────────────────────────
            self._update_run(
                db, run_id,
                current_step=STEP_EXTRACTION, progress_percent=20,
                article_id=article.article_id,
            )
            knowledge_record = self._with_retry(
                func=self.knowledge_extractor.extract_knowledge_model,
                step_name=STEP_EXTRACTION,
                db=db,
                article_id=article.article_id,
                max_attempts=2,
                run_id=run_id,
            )

            # ── Validation ───────────────────────────────────────────────
            self._update_run(
                db, run_id,
                current_step=STEP_VALIDATION, progress_percent=35,
            )
            knowledge_model = self.knowledge_validator.validate_raw(
                knowledge_record.raw_json
            )

            # ── Section Builders ─────────────────────────────────────────
            section_pipeline = [
                (STEP_SECTION_1_OVERVIEW, "section_1", 45, 2),
                (STEP_SECTION_2_KEY_CONCEPTS, "section_2", 55, 2),
                (STEP_SECTION_3_PROBLEM, "section_3", 63, 2),
                (STEP_SECTION_4_ARCHITECTURE, "section_4", 71, 2),
                (STEP_SECTION_5_FLOW, "section_5", 79, 2),
                (STEP_SECTION_6_TRADEOFFS, "section_6", 87, 2),
            ]
            # ── Running All the sections ─────────────────────────────────────────
            for step_name, slot, progress, max_attempts in section_pipeline:
                self._update_run(db, run_id, step_name, progress)
                builder = self.section_builders.get(slot)
                if builder is None:
                    continue
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
        except Exception as exc:
            db.rollback()
            self._fail_run(db, run_id, str(exc))
        finally:
            db.close()

    def get_run(self, db: Session, run_id: str) -> ProcessingRun | None:
        return db.get(ProcessingRun, run_id)

    def to_read_model(self, run: ProcessingRun) -> ProcessingRunRead:
        return ProcessingRunRead(
            run_id=run.run_id,
            status=run.status,
            current_step=run.current_step,
            progress_percent=run.progress_percent,
            article_id=run.article_id,
            section_1=run.section_1_json,
            section_2=run.section_2_json,
            section_3=run.section_3_json,
            section_4=run.section_4_json,
            section_5=run.section_5_json,
            section_6=run.section_6_json,
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
        col = f"{slot}_json"
        if not hasattr(run, col):
            raise ValueError(f"Unknown section slot: {slot}")
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
        for attempt in range(1, max_attempts + 1):
            try:
                return func(**kwargs)
            except Exception:
                if attempt == max_attempts:
                    raise
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
    def _progress_for(step_name: str, attempt: int, max_attempts: int) -> int:
        base = {
            STEP_INGESTION: 5,
            STEP_EXTRACTION: 20,
            STEP_VALIDATION: 35,
            STEP_SECTION_1_OVERVIEW: 45,
            STEP_SECTION_2_KEY_CONCEPTS: 55,
            STEP_SECTION_3_PROBLEM: 63,
            STEP_SECTION_4_ARCHITECTURE: 71,
            STEP_SECTION_5_FLOW: 79,
            STEP_SECTION_6_TRADEOFFS: 87,
        }
        return base.get(step_name, 50) + (attempt * 2)

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
