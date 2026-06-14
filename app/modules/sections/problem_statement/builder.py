from __future__ import annotations

from app.modules.extractor.models.knowledge_model import (
    KnowledgeModel,
    TemporalSignalType,
)
from app.modules.sections.problem_statement.schemas import ProblemSection
from app.storage.models import Article


class ProblemStatementBuilder:
    def build(
        self, knowledge_model: KnowledgeModel, article: Article
    ) -> ProblemSection:
        if not knowledge_model.problem_signals:
            raise ValueError(
                "problem statement requires at least one problem_signal in the KnowledgeModel"
            )

        headline = self._build_headline(knowledge_model)
        context = self._build_context(knowledge_model)
        pain_points = self._build_pain_points(knowledge_model)
        constraints = self._build_constraints(knowledge_model)
        scale_context = self._build_scale_context(knowledge_model)
        prior_approach = self._build_prior_approach(knowledge_model)

        return ProblemSection(
            headline=headline,
            context=context,
            pain_points=pain_points,
            constraints=constraints,
            scale_context=scale_context,
            prior_approach=prior_approach,
        )

    # ── field builders ──────────────────────────────────────────────────

    def _build_headline(self, knowledge_model: KnowledgeModel) -> str:
        strongest = knowledge_model.problem_signals[0]
        return self._sentence(strongest)

    def _build_context(self, knowledge_model: KnowledgeModel) -> str:
        parts: list[str] = []

        previous_signals = [
            signal.description
            for signal in knowledge_model.temporal_signals
            if signal.signal_type == TemporalSignalType.PREVIOUS_SYSTEM
        ]
        if previous_signals:
            parts.append(self._sentence(previous_signals[0]))

        scale_signals = knowledge_model.scale_context_signals
        if scale_signals:
            parts.append(self._sentence(scale_signals[0]))

        if not parts:
            parts.append(
                self._sentence(
                    f"The system faced significant engineering challenges: {knowledge_model.problem_signals[0]}"
                )
            )

        return " ".join(parts)

    def _build_pain_points(self, knowledge_model: KnowledgeModel) -> list[str]:
        return [self._sentence(signal) for signal in knowledge_model.problem_signals]

    def _build_constraints(self, knowledge_model: KnowledgeModel) -> list[str]:
        constraints: list[str] = []
        for signal in knowledge_model.constraint_signals:
            constraint = self._sentence(signal)
            if not constraint.lower().startswith("the solution had to"):
                body = self._strip_leading_modals(constraint)
                constraint = f"The solution had to {body[0].lower()}{body[1:]}"
            constraints.append(constraint)
        return constraints

    @staticmethod
    def _strip_leading_modals(text: str) -> str:
        lower = text.lower()
        for prefix in ("must ", "should ", "had to ", "needed to ", "required to "):
            if lower.startswith(prefix):
                return text[len(prefix) :]
        return text

    def _build_scale_context(self, knowledge_model: KnowledgeModel) -> str | None:
        scale_signals = knowledge_model.scale_context_signals
        if not scale_signals:
            return None

        scored: list[tuple[int, str]] = []
        for signal in scale_signals:
            score = self._quantitative_score(signal)
            scored.append((score, signal))
        scored.sort(key=lambda x: x[0], reverse=True)
        return self._sentence(scored[0][1])

    def _build_prior_approach(self, knowledge_model: KnowledgeModel) -> str | None:
        for signal in knowledge_model.temporal_signals:
            if (
                signal.signal_type == TemporalSignalType.PREVIOUS_SYSTEM
                and signal.before_entity
            ):
                return signal.before_entity

        for signal in knowledge_model.temporal_signals:
            if signal.before_entity:
                return signal.before_entity

        return "No prior approach stated"

    # ── helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _quantitative_score(text: str) -> int:
        score = 0
        for ch in text:
            if ch.isdigit():
                score += 1
        return score

    @staticmethod
    def _sentence(text: str) -> str:
        cleaned = " ".join(text.strip().split())
        if not cleaned:
            return cleaned
        return cleaned if cleaned.endswith((".", "!", "?")) else f"{cleaned}."
