from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor

from sqlalchemy.orm import Session

from app.core.config import settings
from app.llm import LLMClient
from app.logging_config import get_logger
from app.modules.extractor.models.extraction_result import ExtractionResult
from app.modules.extractor.models.knowledge_model import KnowledgeModel
from app.modules.extractor.models.recognition_output import RecognitionOutput
from app.modules.extractor.models.structure_output import StructureOutput
from app.modules.extractor.models.reasoning_output import ReasoningOutput
from app.modules.extractor.repository import KnowledgeModelRepository
from app.modules.extractor.prompts.recognition_prompt import (
    PASS_1_RECOGNITION_SYSTEM_PROMPT,
    build_recognition_user_prompt,
)
from app.modules.extractor.prompts.structure_prompt import (
    PASS_2_STRUCTURE_SYSTEM_PROMPT,
    build_structure_user_prompt,
)
from app.modules.extractor.prompts.reasoning_prompt import (
    PASS_3_REASONING_SYSTEM_PROMPT,
    build_reasoning_user_prompt,
)
from app.modules.extractor.services.knowledge_model_validator import (
    KnowledgeModelValidator,
)
from app.modules.extractor.services.merge_service import MergeService
from app.modules.extractor.services.pass_extractor import PassExtractor
from app.storage.repository import ArticleRepository
from app.storage.models import KnowledgeModelRecord

_log = get_logger(__name__)


class KnowledgeExtractor:
    """Top-level orchestrator for the multi-pass Knowledge Model extraction pipeline.

    Coordinates three independent, parallel extraction passes (recognition,
    structure, reasoning), merges their outputs deterministically, validates
    cross-pass referential integrity, and stores the results.

    The extraction flow:
        1. Build per-pass prompts from the article's cleaned text and metadata.
        2. Run all three passes in parallel via ThreadPoolExecutor (max 3 workers).
        3. Merge the three ExtractionResults into a single KnowledgeModel.
        4. Run cross-pass validation — if structure references don't match
           recognition entities, retry the structure pass once.
        5. Store the KnowledgeModel and per-pass raw JSON to the database.

    All dependencies (LLM client, repositories, validator, pass extractor,
    merge service) are injectable for testability. If omitted, sensible
    defaults are created from global settings.

    Usage::

        extractor = KnowledgeExtractor()
        record = extractor.extract_knowledge_model(db, article_id)
        # record.raw_json is the merged KnowledgeModel
        # record.pass_1_json, pass_2_json, pass_3_json are per-pass outputs
    """

    def __init__(
        self,
        repo: KnowledgeModelRepository | None = None,
        article_repo: ArticleRepository | None = None,
        llm_client: LLMClient | None = None,
        validator: KnowledgeModelValidator | None = None,
        pass_extractor: PassExtractor | None = None,
        merge_service: MergeService | None = None,
    ) -> None:
        """Create a KnowledgeExtractor with optional dependency injection.

        Args:
            repo: Repository for knowledge model persistence. Defaults to
                KnowledgeModelRepository().
            article_repo: Repository for article lookup. Defaults to
                ArticleRepository().
            llm_client: LLM client for structured extraction. Defaults to
                LLMClient() using global settings.
            validator: Schema and cross-pass validator. Defaults to
                KnowledgeModelValidator().
            pass_extractor: Per-pass extraction engine. Defaults to
                PassExtractor() configured with the LLM client.
            merge_service: Deterministic merge of pass outputs. Defaults to
                MergeService().
        """
        self.repo = repo or KnowledgeModelRepository()
        self.article_repo = article_repo or ArticleRepository()
        self.llm_client = llm_client or LLMClient()
        self.validator = validator or KnowledgeModelValidator()
        self.pass_extractor = pass_extractor or PassExtractor(llm_client=self.llm_client)
        self.merge_service = merge_service or MergeService()

    def extract_knowledge_model(
        self, db: Session, article_id: str
    ) -> KnowledgeModelRecord:
        """Run the full multi-pass extraction for an article.

        This is the main entry point. It checks for an existing knowledge model
        (idempotent), loads the article, and delegates to the multi-pass
        pipeline. If the article has no cleaned_text, raises ValueError.

        Args:
            db: Active SQLAlchemy session.
            article_id: UUID of the article to extract from.

        Returns:
            The created or existing KnowledgeModelRecord with the merged
            KnowledgeModel in raw_json and per-pass outputs in pass_*_json.

        Raises:
            ValueError: If article_id is empty or the article has no cleaned_text.
            LookupError: If no article exists with the given article_id.
        """
        if not article_id:
            raise ValueError("article_id is required for extraction")

        existing = self.repo.get(db, article_id=article_id)
        if existing is not None:
            return existing

        article = self.article_repo.get(db, article_id=article_id)
        if article is None:
            raise LookupError("article not found")
        if not article.cleaned_text:
            raise ValueError("article has no cleaned_text to extract from")

        return self._extract_multi_pass(db, article)

    def _extract_multi_pass(
        self, db: Session, article
    ) -> KnowledgeModelRecord:
        """Execute the 3-pass extraction pipeline and return the stored record.

        Builds user prompts from the article's cleaned text and metadata,
        runs all three passes in parallel, merges the results, validates
        cross-pass referential integrity (retrying pass 2 if needed), and
        persists everything to the database.

        Args:
            db: Active SQLAlchemy session.
            article: The Article ORM object with cleaned_text, source_title, etc.

        Returns:
            The stored KnowledgeModelRecord with the merged model and per-pass
            raw JSON.

        Raises:
            RuntimeError: If any pass fails with an unhandled exception.
        """
        log = _log.bind(
            article_id=article.article_id,
            title=(article.source_title or "")[:80],
        )
        log.info("multi_pass_extraction_start | passes=3")

        cleaned_text = article.cleaned_text
        source_title = article.source_title
        source_domain = article.source_domain
        word_count = article.word_count

        user_prompts = {
            "recognition": build_recognition_user_prompt(
                cleaned_text=cleaned_text,
                source_title=source_title,
                source_domain=source_domain,
                word_count=word_count,
            ),
            "structure": build_structure_user_prompt(
                cleaned_text=cleaned_text,
                source_title=source_title,
                source_domain=source_domain,
                word_count=word_count,
            ),
            "reasoning": build_reasoning_user_prompt(
                cleaned_text=cleaned_text,
                source_title=source_title,
                source_domain=source_domain,
                word_count=word_count,
            ),
        }

        system_prompts = {
            "recognition": PASS_1_RECOGNITION_SYSTEM_PROMPT,
            "structure": PASS_2_STRUCTURE_SYSTEM_PROMPT,
            "reasoning": PASS_3_REASONING_SYSTEM_PROMPT,
        }

        models = {
            "recognition": settings.extraction_model_pass_1 or settings.extraction_model,
            "structure": settings.extraction_model_pass_2 or settings.extraction_model,
            "reasoning": settings.extraction_model_pass_3 or settings.extraction_model,
        }

        # ── Parallel execution ──────────────────────────────────────────
        futures: dict[str, Future] = {}
        with ThreadPoolExecutor(max_workers=3) as executor:
            for pass_name in ("recognition", "structure", "reasoning"):
                futures[pass_name] = executor.submit(
                    self.pass_extractor.extract_pass,
                    pass_name=pass_name,
                    system_prompt=system_prompts[pass_name],
                    user_prompt=user_prompts[pass_name],
                    model=models[pass_name],
                )

            results: dict[str, ExtractionResult] = {}
            for pass_name, future in futures.items():
                try:
                    results[pass_name] = future.result()
                except Exception as exc:
                    log.opt.error("pass_failed | pass=%s | error=%s", pass_name, str(exc))
                    raise RuntimeError(
                        f"Pass '{pass_name}' failed: {exc}"
                    ) from exc

        p1: ExtractionResult[RecognitionOutput] = results["recognition"]
        p2: ExtractionResult[StructureOutput] = results["structure"]
        p3: ExtractionResult[ReasoningOutput] = results["reasoning"]

        log.info(
            "multi_pass_extraction_complete"
            " | recogn_self=%.2f struct=%.2f comb=%.2f retries=%d"
            " | struct_self=%.2f struct=%.2f comb=%.2f retries=%d"
            " | reason_self=%.2f struct=%.2f comb=%.2f retries=%d",
            p1.self_reported_score, p1.structural_score, p1.combined_score, p1.retry_count,
            p2.self_reported_score, p2.structural_score, p2.combined_score, p2.retry_count,
            p3.self_reported_score, p3.structural_score, p3.combined_score, p3.retry_count,
        )

        # ── Merge ───────────────────────────────────────────────────────
        log.info("merge_start")
        cross_pass_warnings: list[str] = []
        knowledge_model = self.merge_service.merge(p1, p2, p3)

        # ── Cross-pass validation ───────────────────────────────────────
        log.info("cross_pass_validation_start")
        cross_val = self.validator.validate_cross_pass(knowledge_model)
        if not cross_val.valid:
            log.warning(
                "cross_pass_validation_failed | errors=%d | failing_pass=%s",
                len(cross_val.errors), cross_val.failing_pass,
            )
            if cross_val.failing_pass == "structure":
                log.info("retrying_pass_2_due_to_cross_reference_failure")
                try:
                    p2_retry = self.pass_extractor.extract_pass(
                        pass_name="structure",
                        system_prompt=system_prompts["structure"],
                        user_prompt=user_prompts["structure"],
                        model=models["structure"],
                    )
                    knowledge_model = self.merge_service.merge(p1, p2_retry, p3)
                    cross_val_2 = self.validator.validate_cross_pass(knowledge_model)
                    if not cross_val_2.valid:
                        cross_pass_warnings.extend(cross_val_2.errors)
                        log.warning(
                            "cross_pass_validation_still_failed_after_retry | errors=%d",
                            len(cross_val_2.errors),
                        )
                    else:
                        log.info("cross_pass_validation_passed_after_retry")
                except Exception as exc:
                    cross_pass_warnings.extend(cross_val.errors)
                    log.opt.warning(
                        "pass_2_retry_failed | error=%s | proceeding_with_warnings",
                        str(exc),
                    )
            else:
                cross_pass_warnings.extend(cross_val.errors)

        if cross_pass_warnings:
            knowledge_model = self.merge_service.merge(
                p1, p2, p3, cross_pass_warnings=cross_pass_warnings,
            )

        log.info(
            "merge_complete | entities=%d | concepts=%d | relationships=%d | "
            "flows=%d | tradeoffs=%d | combined_confidence=%.2f | warnings=%d",
            len(knowledge_model.named_entities),
            len(knowledge_model.concept_definitions),
            len(knowledge_model.relationships),
            len(knowledge_model.flow_sequences),
            len(knowledge_model.tradeoff_signals),
            knowledge_model.confidence_score,
            len(knowledge_model.extraction_warnings),
        )

        # ── Store ───────────────────────────────────────────────────────
        record = KnowledgeModelRecord(
            article_id=article.article_id,
            source_url=article.source_url,
            raw_json=knowledge_model.model_dump(mode="json"),
            pass_1_json=p1.data.model_dump(mode="json"),
            pass_2_json=p2.data.model_dump(mode="json"),
            pass_3_json=p3.data.model_dump(mode="json"),
        )
        return self.repo.create(db, record)
