from __future__ import annotations

from math import ceil

from app.modules.extractor.models.knowledge_model import (
    CategoryHint,
    EntityType,
    KnowledgeModel,
    NamedEntity,
    TemporalSignalType,
)
from app.modules.extractor.schemas import OverviewSection
from app.storage.models import Article


class OverviewSectionBuilder:
    def build(self, knowledge_model: KnowledgeModel, article: Article) -> OverviewSection:
        if not knowledge_model.problem_signals:
            raise ValueError("overview requires at least one problem signal")

        primary_system = self._select_primary_system(knowledge_model)
        if primary_system is None:
            raise ValueError("overview requires at least one named entity for system_name")

        company = self._select_company(knowledge_model)
        domain = self._build_domain_tags(knowledge_model)
        reading_time_min = max(1, ceil((article.word_count or 0) / 230))
        strongest_problem = knowledge_model.problem_signals[0]
        motivation = self._motivation_text(knowledge_model)

        return OverviewSection(
            one_line_summary=self._one_line_summary(
                company=company,
                system_name=primary_system.name,
                problem=strongest_problem,
            ),
            system_name=primary_system.name,
            company=company,
            domain=domain,
            full_summary=self._full_summary(
                company=company,
                system_name=primary_system.name,
                problem=strongest_problem,
                knowledge_model=knowledge_model,
            ),
            why_it_exists=motivation or self._sentence(strongest_problem),
            reading_time_min=reading_time_min,
        )

    @staticmethod
    def _select_primary_system(knowledge_model: KnowledgeModel) -> NamedEntity | None:
        internal_systems = [
            entity
            for entity in knowledge_model.named_entities
            if entity.entity_type == EntityType.INTERNAL_SYSTEM
        ]
        for entity in internal_systems:
            if entity.is_primary:
                return entity
        if internal_systems:
            return internal_systems[0]
        for entity in knowledge_model.named_entities:
            if entity.is_primary:
                return entity
        return knowledge_model.named_entities[0] if knowledge_model.named_entities else None

    @staticmethod
    def _select_company(knowledge_model: KnowledgeModel) -> str:
        for entity in knowledge_model.named_entities:
            if entity.entity_type == EntityType.COMPANY:
                return entity.name
        return "Not stated in the article"

    def _build_domain_tags(self, knowledge_model: KnowledgeModel) -> list[str]:
        tags: list[str] = []
        category_tags = {
            CategoryHint.INFRASTRUCTURE: "Infrastructure",
            CategoryHint.PATTERN: "Architecture Patterns",
            CategoryHint.DATA_MODEL: "Data Models",
            CategoryHint.PROTOCOL: "Protocols",
            CategoryHint.TOOL: "Developer Tools",
            CategoryHint.ALGORITHM: "Algorithms",
        }
        for concept in knowledge_model.concept_definitions:
            self._append_unique(tags, category_tags[concept.category_hint])

        layer_text = " ".join(layer.layer_name.lower() for layer in knowledge_model.layer_signals)
        layer_tags = [
            ("ml", "ML Infrastructure"),
            ("model", "ML Infrastructure"),
            ("data", "Data Systems"),
            ("routing", "Distributed Systems"),
            ("serving", "Serving Systems"),
            ("control", "Control Plane"),
            ("client", "Client Systems"),
        ]
        for keyword, tag in layer_tags:
            if keyword in layer_text:
                self._append_unique(tags, tag)

        if len(tags) < 2:
            self._append_unique(tags, "Distributed Systems")
        if len(tags) < 2:
            self._append_unique(tags, "Software Architecture")
        return tags[:3]

    def _motivation_text(self, knowledge_model: KnowledgeModel) -> str | None:
        motivations = [
            signal.description
            for signal in knowledge_model.temporal_signals
            if signal.signal_type == TemporalSignalType.MOTIVATION
        ]
        if motivations:
            return self._sentence(" ".join(motivations[:2]))
        if knowledge_model.problem_signals:
            return self._sentence(
                "The system exists to address "
                + "; ".join(knowledge_model.problem_signals[:2])
            )
        return None

    def _full_summary(
        self,
        company: str,
        system_name: str,
        problem: str,
        knowledge_model: KnowledgeModel,
    ) -> str:
        sentences = [
            self._sentence(f"{company} discusses {system_name} in this engineering article"),
            self._sentence(f"The core problem was {problem}"),
        ]
        if knowledge_model.scale_context_signals:
            sentences.append(
                self._sentence(
                    f"The scale context includes {knowledge_model.scale_context_signals[0]}"
                )
            )
        previous_or_motivation = next(
            (
                signal.description
                for signal in knowledge_model.temporal_signals
                if signal.signal_type
                in {
                    TemporalSignalType.PREVIOUS_SYSTEM,
                    TemporalSignalType.MOTIVATION,
                    TemporalSignalType.EVOLUTION,
                }
            ),
            None,
        )
        if previous_or_motivation:
            sentences.append(self._sentence(previous_or_motivation))
        return " ".join(sentences[:4])

    def _one_line_summary(self, company: str, system_name: str, problem: str) -> str:
        if company == "Not stated in the article":
            summary = f"{system_name} addresses {problem}."
        else:
            summary = f"{company} uses {system_name} to address {problem}."
        return self._truncate_sentence(summary, limit=160)

    @staticmethod
    def _append_unique(values: list[str], value: str) -> None:
        if value not in values:
            values.append(value)

    @staticmethod
    def _sentence(text: str) -> str:
        cleaned = " ".join(text.strip().split())
        if not cleaned:
            return cleaned
        return cleaned if cleaned.endswith((".", "!", "?")) else f"{cleaned}."

    @staticmethod
    def _truncate_sentence(text: str, limit: int) -> str:
        cleaned = " ".join(text.strip().split())
        if len(cleaned) <= limit:
            return cleaned
        truncated = cleaned[: limit - 1].rsplit(" ", maxsplit=1)[0].rstrip(".,;:")
        return f"{truncated}."
