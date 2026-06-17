from __future__ import annotations

import time
from typing import Type, TypeVar

from pydantic import BaseModel

from app.core.config import settings
from app.llm import LLMClient
from app.logging_config import get_logger
from app.modules.extractor.models.extraction_result import ExtractionResult
from app.modules.extractor.services.confidence_scorer import ConfidenceScorer
from app.modules.extractor.models.recognition_output import RecognitionOutput
from app.modules.extractor.models.structure_output import StructureOutput
from app.modules.extractor.models.reasoning_output import ReasoningOutput

T = TypeVar("T", bound=BaseModel)

_log = get_logger(__name__)

_SCORERS = {
    "recognition": ConfidenceScorer.compute_pass_1,
    "structure": ConfidenceScorer.compute_pass_2,
    "reasoning": ConfidenceScorer.compute_pass_3,
}

_OUTPUT_MODELS: dict[str, Type[BaseModel]] = {
    "recognition": RecognitionOutput,
    "structure": StructureOutput,
    "reasoning": ReasoningOutput,
}


class PassExtractor:
    """Runs a single Knowledge Model pass with confidence-gated retry.

    Each pass receives the full article text, a focused system prompt, and a
    dedicated Pydantic response model. The LLM self-reports confidence, which
    is combined with a deterministic structural quality score. If the combined
    score falls below the configured threshold, the pass is retried with
    exponential backoff.

    On retry exhaustion, the best result (highest combined confidence) is
    returned with a warning instead of raising — this allows the pipeline to
    degrade gracefully when articles are inherently sparse or vague.

    Usage::

        extractor = PassExtractor(llm_client=client)
        result = extractor.extract_pass(
            pass_name="recognition",
            system_prompt=RECOGNITION_SYSTEM_PROMPT,
            user_prompt=recognition_user_prompt,
        )
        # result.data is RecognitionOutput
        # result.combined_score is min(self_reported, structural)
    """

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        """Create a PassExtractor.

        Args:
            llm_client: An optional pre-configured LLMClient. If omitted, a
                default client is created using global settings.
        """
        self._llm = llm_client or LLMClient()
        self._scorer = ConfidenceScorer()

    def extract_pass(
        self,
        pass_name: str,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
    ) -> ExtractionResult:
        """Execute a single extraction pass with confidence-gated retry.

        Calls the LLM with a temperature of 0.0 for deterministic output.
        The returned Pydantic model is scored using the pass-specific
        structural heuristics. If the combined confidence (min of
        self-reported and structural) is below the threshold, the pass
        retries with exponential backoff (base 2s, capped at 10s).

        Args:
            pass_name: One of 'recognition', 'structure', or 'reasoning'.
                Determines which output model and scoring function to use.
            system_prompt: The system-level instructions for this pass.
                Should be the pass-specific constant from the prompts module.
            user_prompt: The user-level prompt containing article metadata,
                text, and the task description for this pass.
            model: Optional model override. Falls back to
                settings.extraction_model if not provided.

        Returns:
            An ExtractionResult wrapping the extracted Pydantic model
            (accessible via ``result.data``) along with confidence scores,
            retry count, and any warnings generated.

        Raises:
            RuntimeError: If every attempt (including all retries) fails
                with an exception — not just low confidence, but actual
                LLM or parsing errors on every try.
        """
        log = _log.bind(pass_name=pass_name)
        output_model = _OUTPUT_MODELS[pass_name]
        score_fn = _SCORERS[pass_name]
        threshold = settings.extraction_confidence_threshold
        max_retries = settings.extraction_max_retries_per_pass
        resolved_model = model or settings.extraction_model

        best_result: ExtractionResult | None = None
        all_warnings: list[str] = []

        for attempt in range(max_retries + 1):
            try:
                data = self._llm.extract_structured(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    response_model=output_model,
                    temperature=0.0,
                    validation_retries=2,
                    model=resolved_model,
                )
            except Exception as exc:
                log.warning(
                    "pass_extraction_attempt_failed | attempt=%d/%d | error=%s",
                    attempt + 1, max_retries + 1, str(exc),
                )
                if attempt < max_retries:
                    time.sleep(min(2 ** attempt, 10))
                continue

            self_reported = getattr(data, "confidence_score", 1.0)
            structural = score_fn(data)
            combined = ConfidenceScorer.combined_confidence(self_reported, structural)

            warnings: list[str] = []
            if structural < 0.5:
                warnings.append(
                    f"Low structural score ({structural:.2f}) — fields sparsely populated"
                )
            if self_reported < 0.5:
                warnings.append(
                    f"LLM self-reported low confidence ({self_reported:.2f})"
                )
            pass_warnings = getattr(data, "extraction_warnings", None)
            if pass_warnings:
                warnings.extend(pass_warnings)
            all_warnings.extend(warnings)

            result = ExtractionResult(
                pass_name=pass_name,
                self_reported_score=self_reported,
                structural_score=structural,
                combined_score=combined,
                data=data,
                retry_count=attempt,
                warnings=warnings,
            )

            if combined >= threshold:
                log.info(
                    "pass_extraction_success | attempt=%d | self=%.2f | struct=%.2f | combined=%.2f",
                    attempt + 1, self_reported, structural, combined,
                )
                return result

            if best_result is None or combined > best_result.combined_score:
                best_result = result

            if attempt < max_retries:
                backoff = min(2 ** attempt, 10)
                log.warning(
                    "pass_confidence_below_threshold | attempt=%d/%d | combined=%.2f | threshold=%.2f | retry_in=%ds",
                    attempt + 1, max_retries + 1, combined, threshold, backoff,
                )
                time.sleep(backoff)

        if best_result is None:
            raise RuntimeError(
                f"Pass '{pass_name}' failed all {max_retries + 1} extraction attempts"
            )

        _log.bind(pass_name=pass_name).warning(
            "pass_retries_exhausted | best_combined=%.2f | retries=%d | returning_best",
            best_result.combined_score, max_retries,
        )
        best_result.warnings.append(
            f"All {max_retries} retries exhausted. Best combined confidence: {best_result.combined_score:.2f}."
        )
        return best_result
