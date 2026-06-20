from __future__ import annotations

from app.core.config import settings
from app.llm import LLMClient
from app.logging_config import get_logger
from app.modules.extractor.models.knowledge_model import KnowledgeModel, SectionRelevance
from app.modules.sections._shared.entity_resolver import (
    build_name_to_slug_map,
    resolve_entity_refs_in_text,
)
from app.modules.sections._shared.enums import Severity
from app.modules.sections.problem_statement.prompts import (
    PROBLEM_STATEMENT_SYSTEM_PROMPT,
    build_problem_statement_user_prompt,
)
from app.modules.sections.problem_statement.schemas import (
    ProblemSignal,
    ProblemStatementEnrichment,
    ProblemStatementSection,
)
from app.storage.models import Article

_log = get_logger(__name__)


class ProblemStatementBuilder:
    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self._llm = llm_client or LLMClient()

    def build(
        self, knowledge_model: KnowledgeModel, article: Article
    ) -> ProblemStatementSection:
        log = _log.bind(
            article_id=article.article_id,
            title=(article.source_title or "")[:60],
        )

        if len(knowledge_model.problem_signals) < 1:
            raise ValueError("problem statement requires at least 1 problem signal")

        # ── Phase 1: deterministic signal extraction ───────────────────
        core_problem = knowledge_model.core_problem or knowledge_model.problem_signals[0]
        article_summary = getattr(knowledge_model, "article_summary", "")
        scale_context = self._format_scale(knowledge_model)
        problem_signals_text = self._format_problem_signals(knowledge_model)
        key_quotes_text = self._format_problem_quotes(knowledge_model)

        # ── Phase 2: LLM enrichment ────────────────────────────────────
        try:
            enrichment = self._llm.extract_structured(
                system_prompt=PROBLEM_STATEMENT_SYSTEM_PROMPT,
                user_prompt=build_problem_statement_user_prompt(
                    problem_signals=problem_signals_text,
                    key_quotes=key_quotes_text,
                    core_problem=core_problem,
                    article_summary=article_summary,
                    scale_context=scale_context,
                    article_title=article.source_title or "Untitled",
                    article_domain=article.source_domain or "Unknown",
                ),
                response_model=ProblemStatementEnrichment,
                temperature=0.4,
                validation_retries=2,
                model=settings.section_model,
            )
        except Exception:
            enrichment = None
            log.opt.warning("problem_statement:phase_2_failed | falling_back_to_deterministic")

        # ── Phase 3: assemble ──────────────────────────────────────────
        if enrichment:
            narrative = enrichment.problem_narrative
            signals = enrichment.signals
        else:
            narrative = self._build_deterministic_narrative(
                core_problem, knowledge_model, scale_context
            )
            signals = self._build_deterministic_signals(knowledge_model)

        why_it_hurt = self._build_why_it_hurt(knowledge_model, scale_context)

        # Resolve affected entity IDs for cross-section linking
        signals = self._resolve_entity_refs(signals, knowledge_model)

        result = ProblemStatementSection(
            problem_narrative=narrative,
            signals=signals,
            core_problem=core_problem,
            why_it_hurt=why_it_hurt,
        )
        return result

    # ── Phase 1 helpers ─────────────────────────────────────────────────

    @staticmethod
    def _format_scale(knowledge_model: KnowledgeModel) -> str:
        if not knowledge_model.scale_context_signals:
            return ""
        return "\n".join(f"- {s}" for s in knowledge_model.scale_context_signals)

    @staticmethod
    def _format_problem_signals(knowledge_model: KnowledgeModel) -> str:
        lines: list[str] = []
        for i, signal in enumerate(knowledge_model.problem_signals, 1):
            lines.append(f"{i}. {signal}")
        return "\n".join(lines)

    @staticmethod
    def _format_problem_quotes(knowledge_model: KnowledgeModel) -> str:
        problem_quotes = [
            q for q in knowledge_model.key_quotes
            if SectionRelevance.PROBLEM in q.section_relevance
        ]
        if not problem_quotes:
            return ""
        return "\n".join(f'"{q.text}"' for q in problem_quotes[:4])

    # ── Phase 3 deterministic fallback helpers ──────────────────────────

    def _build_deterministic_narrative(
        self,
        core_problem: str,
        knowledge_model: KnowledgeModel,
        scale_context: str,
    ) -> str:
        parts: list[str] = []
        parts.append(f"The central technical challenge addressed in this article is: {core_problem}.")

        if knowledge_model.problem_signals:
            parts.append("")
            parts.append("Key problem signals extracted from the article include:")
            for signal in knowledge_model.problem_signals[:4]:
                parts.append(f"• {signal}")

        if scale_context:
            parts.append("")
            parts.append(f"Scale context: {knowledge_model.scale_context_signals[0] if knowledge_model.scale_context_signals else ''}")

        if len(knowledge_model.problem_signals) > 1:
            parts.append("")
            parts.append("These challenges were compounded by the operating scale and engineering requirements described in the article.")

        return "\n".join(parts)

    def _build_deterministic_signals(
        self, knowledge_model: KnowledgeModel
    ) -> list[ProblemSignal]:
        signals: list[ProblemSignal] = []
        for i, raw_signal in enumerate(knowledge_model.problem_signals[:6]):
            severity = Severity.CRITICAL if i == 0 else Severity.MAJOR if i < 3 else Severity.MINOR
            scale_dim = self._infer_scale_dimension(raw_signal)
            signals.append(
                ProblemSignal(
                    description=raw_signal,
                    severity=severity,
                    scale_dimension=scale_dim,
                    evidence=raw_signal,
                )
            )
        return signals

    @staticmethod
    def _resolve_entity_refs(
        signals: list[ProblemSignal], knowledge_model: KnowledgeModel
    ) -> list[ProblemSignal]:
        """Resolve architecture node IDs for each problem signal.

        Finds entity names mentioned in each signal's description and maps
        them to architecture node slugs for cross-section visual linking.
        """
        name_to_slug = build_name_to_slug_map(knowledge_model)
        for signal in signals:
            signal.affected_entity_ids = resolve_entity_refs_in_text(
                signal.description, name_to_slug
            )
        return signals

    @staticmethod
    def _infer_scale_dimension(text: str) -> str | None:
        text_lower = text.lower()
        if any(kw in text_lower for kw in ["latency", "delay", "ms", "seconds", "slow"]):
            return "latency"
        if any(kw in text_lower for kw in ["throughput", "rps", "qps", "requests", "volume"]):
            return "throughput"
        if any(kw in text_lower for kw in ["cost", "cheap", "expensive", "dollar"]):
            return "cost"
        if any(kw in text_lower for kw in ["reliab", "outage", "failure", "crash", "downtime"]):
            return "reliability"
        if any(kw in text_lower for kw in ["complex", "hard to", "difficult", "brittle"]):
            return "complexity"
        return None

    @staticmethod
    def _build_why_it_hurt(
        knowledge_model: KnowledgeModel, scale_context: str
    ) -> str:
        parts: list[str] = []

        if knowledge_model.scale_context_signals:
            parts.append(
                f"At the operating scale described ({knowledge_model.scale_context_signals[0]}), "
                f"these problems had compounding effects on the engineering organization."
            )

        problem_quotes = [
            q for q in knowledge_model.key_quotes
            if SectionRelevance.PROBLEM in q.section_relevance
        ]
        if problem_quotes:
            parts.append(f'As the article states: "{problem_quotes[0].text}"')

        if not parts:
            parts.append(
                "The problem was urgent because existing approaches or tools "
                "could not meet the requirements at the necessary scale."
            )

        return " ".join(parts)
