from __future__ import annotations

import json
from typing import Any

from app.core.config import settings
from app.llm import LLMClient
from app.logging_config import get_logger
from app.modules.extractor.models.knowledge_model import KnowledgeModel
from app.modules.sections.flow.prompts import (
    FLOW_SYSTEM_PROMPT,
    build_flow_user_prompt,
)
from app.modules.sections.flow.schemas import (
    FlowEnrichment,
    FlowSection,
    FlowStep,
    FlowWalkthrough,
)
from app.storage.models import Article

_log = get_logger(__name__)


class FlowBuilder:
    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self._llm = llm_client or LLMClient()

    def build(
        self, knowledge_model: KnowledgeModel, article: Article
    ) -> FlowSection:
        log = _log.bind(
            article_id=article.article_id,
            title=(article.source_title or "")[:60],
        )

        if len(knowledge_model.flow_sequences) < 1:
            raise ValueError("flow section requires at least 1 flow sequence")

        # ── Phase 1: deterministic flow extraction ─────────────────────
        flows_json = self._build_flows_json(knowledge_model)

        # ── Phase 2: LLM enrichment ────────────────────────────────────
        try:
            enrichment = self._llm.extract_structured(
                system_prompt=FLOW_SYSTEM_PROMPT,
                user_prompt=build_flow_user_prompt(
                    flows_json=flows_json,
                    article_title=article.source_title or "Untitled",
                    article_domain=article.source_domain or "Unknown",
                ),
                response_model=FlowEnrichment,
                temperature=0.4,
                validation_retries=2,
                model=settings.section_model,
            )
        except Exception:
            enrichment = None
            log.opt.warning("section_5:phase_2_failed | falling_back_to_deterministic")

        # ── Phase 3: assemble ──────────────────────────────────────────
        if enrichment:
            flows = enrichment.flows
        else:
            flows = self._build_deterministic_flows(knowledge_model)

        result = FlowSection(flows=flows)
        return result

    # ── Phase 1 helpers ─────────────────────────────────────────────────

    @staticmethod
    def _build_flows_json(knowledge_model: KnowledgeModel) -> str:
        payload: list[dict[str, Any]] = []
        for seq in knowledge_model.flow_sequences:
            payload.append({
                "flow_name": seq.flow_name,
                "entry_point": seq.entry_point,
                "exit_point": seq.exit_point,
                "steps": [
                    {
                        "order": step.step_order,
                        "actor": step.actor,
                        "action": step.action,
                        "target": step.target,
                        "data": step.data_involved,
                    }
                    for step in seq.steps
                ],
            })
        return json.dumps(payload, indent=2, ensure_ascii=False)

    # ── Phase 3 fallback helpers ────────────────────────────────────────

    def _build_deterministic_flows(
        self, knowledge_model: KnowledgeModel
    ) -> list[FlowWalkthrough]:
        flows: list[FlowWalkthrough] = []
        for seq in knowledge_model.flow_sequences:
            steps = [
                FlowStep(
                    order=step.step_order,
                    actor=step.actor,
                    action=step.action,
                    target=step.target,
                    data=step.data_involved,
                    description=self._describe_step(step),
                )
                for step in seq.steps
            ]
            flows.append(
                FlowWalkthrough(
                    flow_name=seq.flow_name,
                    overview=self._build_flow_overview(seq),
                    steps=steps,
                )
            )
        return flows

    @staticmethod
    def _describe_step(step) -> str:
        parts = [f"{step.actor} {step.action}"]
        if step.target:
            parts.append(f"to {step.target}")
        if step.data_involved:
            parts.append(f"({step.data_involved})")
        return " ".join(parts)

    @staticmethod
    def _build_flow_overview(seq) -> str:
        return (
            f"The {seq.flow_name} flow is triggered by {seq.entry_point} "
            f"and results in {seq.exit_point}. "
            f"It involves {len(seq.steps)} steps."
        )
