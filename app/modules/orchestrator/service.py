from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

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

STEP_SECTION_1_OVERVIEW = "section_1_overview"
STEP_SECTION_2_KEY_CONCEPTS = "section_2_key_concepts"
STEP_SECTION_3_PROBLEM = "section_3_problem_statement"
STEP_SECTION_4_ARCHITECTURE = "section_4_architecture_overview"
STEP_SECTION_5_FLOW = "section_5_end_to_end_flow"
STEP_SECTION_6_TRADEOFFS = "section_6_tradeoffs_key_learnings"

PIPELINE_STEPS = [
    STEP_INGESTION,
    STEP_MULTI_PASS_EXTRACTION,
    STEP_MERGE_VALIDATION,
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
        section_2_builder: KeyConceptsBuilder | None = None,
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
            "section_2": section_2_builder or KeyConceptsBuilder(),
            "section_3": section_3_builder or ProblemStatementBuilder(),
            "section_4": section_4_builder or ArchitectureBuilder(),
            "section_5": section_5_builder or FlowBuilder(),
            "section_6": section_6_builder or TradeoffsBuilder(),
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
        """Execute the full pipeline: ingestion → extraction → validation → sections 1-6."""
        log = _log.bind(run_id=run_id)
        log.info("pipeline_started | steps_total=%d", len(PIPELINE_STEPS))

        db = SessionLocal()
        try:
            run = self._require_run(db, run_id)
            payload = PipelineRunCreate.model_validate(run.request_payload or {})

            # ── Step 1: Ingestion ───────────────────────────────────────
            log.info("step_start | step=%s | progress=%d%%", STEP_INGESTION, 5)
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
            log.info(
                "step_complete | step=%s | article_id=%s | word_count=%d | title=%s",
                STEP_INGESTION,
                article.article_id,
                article.word_count or 0,
                (article.source_title or "")[:80],
            )

            # ── Step 2: Multi-Pass Knowledge Extraction ──────────────────
            log.info(
                "step_start | step=%s | progress=%d%% | article_id=%s",
                STEP_MULTI_PASS_EXTRACTION, 15, article.article_id,
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
            log.info(
                "step_complete | step=%s | record_id=%s | raw_json_bytes=%d",
                STEP_MULTI_PASS_EXTRACTION,
                knowledge_record.article_id,
                len(str(knowledge_record.raw_json)),
            )

            # ── Step 3: Merge & Cross-Pass Validation ───────────────────
            log.info("step_start | step=%s | progress=%d%%", STEP_MERGE_VALIDATION, 25)
            self._update_run(
                db, run_id,
                current_step=STEP_MERGE_VALIDATION, progress_percent=25,
            )

            knowledge_model = self.knowledge_validator.validate_raw(
                knowledge_record.raw_json
            )
            log.info(
                "step_complete | step=%s | confidence=%.2f | entities=%d | "
                "concepts=%d | relationships=%d | flows=%d | "
                "tradeoffs=%d | warnings=%d",
                STEP_MERGE_VALIDATION,
                knowledge_model.confidence_score,
                len(knowledge_model.named_entities),
                len(knowledge_model.concept_definitions),
                len(knowledge_model.relationships),
                len(knowledge_model.flow_sequences),
                len(knowledge_model.tradeoff_signals),
                len(knowledge_model.extraction_warnings),
            )

            run = self._require_run(db, run_id)
            run.knowledge_model_json = knowledge_model.model_dump(mode="json")
            db.commit()

            # ── Steps 4-9: Section Builders ─────────────────────────────
            section_pipeline = [
                (STEP_SECTION_1_OVERVIEW, "section_1", 35, 2),
                (STEP_SECTION_2_KEY_CONCEPTS, "section_2", 45, 2),
                (STEP_SECTION_3_PROBLEM, "section_3", 53, 2),
                (STEP_SECTION_4_ARCHITECTURE, "section_4", 61, 2),
                (STEP_SECTION_5_FLOW, "section_5", 69, 2),
                (STEP_SECTION_6_TRADEOFFS, "section_6", 77, 2),
            ]

            for step_name, slot, progress, max_attempts in section_pipeline:
                builder = self.section_builders.get(slot)
                if builder is None:
                    log.info(
                        "step_skipped | step=%s | reason=no_builder_registered",
                        step_name,
                    )
                    continue

                log.info(
                    "step_start | step=%s | progress=%d%% | builder=%s",
                    step_name, progress, type(builder).__name__,
                )
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
            log.opt.error(
                "pipeline_failed | error=%s",
                str(exc),
            )
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
            knowledge_model=run.knowledge_model_json,
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
        log = _log.bind(run_id=run_id)
        result = self._with_retry(
            func=builder.build,
            step_name=step_name,
            knowledge_model=knowledge_model,
            article=article,
            max_attempts=max_attempts,
            run_id=run_id,
        )
        self._save_section(db, run_id, section_slot, result)
        log.info(
            "step_complete | step=%s | section=%s | result_type=%s",
            step_name, section_slot,
            type(result).__name__ if result else "None",
        )

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
        _log.bind(run_id=run_id).info(
            "section_saved | slot=%s | bytes=%d",
            slot, len(str(data)) if data else 0,
        )

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
        base = {
            STEP_INGESTION: 5,
            STEP_MULTI_PASS_EXTRACTION: 15,
            STEP_MERGE_VALIDATION: 25,
            STEP_SECTION_1_OVERVIEW: 35,
            STEP_SECTION_2_KEY_CONCEPTS: 45,
            STEP_SECTION_3_PROBLEM: 53,
            STEP_SECTION_4_ARCHITECTURE: 61,
            STEP_SECTION_5_FLOW: 69,
            STEP_SECTION_6_TRADEOFFS: 77,
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
