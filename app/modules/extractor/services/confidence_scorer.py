from __future__ import annotations

from pydantic import BaseModel


class ConfidenceScorer:
    """Computes deterministic structural quality scores for per-pass outputs.

    Each pass has its own scoring profile with weighted sub-signals tuned to
    what matters most for that pass:

    - **Pass 1 (Recognition)**: entity density, concept completeness, field
      population, problem signals, scale signals, key quotes.
    - **Pass 2 (Structure)**: field population, relationship count, flow
      step density, flow sequence count, layer count, temporal count.
    - **Pass 3 (Reasoning)**: tradeoff completeness (benefit+cost presence),
      field population, tradeoff count, constraint count.

    The structural score complements the LLM's self-reported confidence. The
    final combined score used downstream is ``min(self_reported, structural)``.
    """

    @staticmethod
    def compute_pass_1(data: BaseModel) -> float:
        """Compute the structural score for a RecognitionOutput.

        Weights entity density (0.25) and concept completeness (0.20) most
        heavily because empty entities or shallow concept definitions are the
        strongest signals of a poor recognition pass.
        """
        weights = {
            "entity_density": 0.25,
            "concept_completeness": 0.20,
            "field_population": 0.20,
            "problem_signals": 0.15,
            "scale_signals": 0.10,
            "key_quotes": 0.10,
        }

        signals = [
            (weights["entity_density"], ConfidenceScorer._entity_density(data)),
            (weights["concept_completeness"], ConfidenceScorer._concept_completeness(data)),
            (weights["field_population"], ConfidenceScorer._field_population_rate(data)),
            (weights["problem_signals"], ConfidenceScorer._count_score(data, "problem_signals", 1)),
            (weights["scale_signals"], ConfidenceScorer._count_score(data, "scale_context_signals", 1)),
            (weights["key_quotes"], ConfidenceScorer._count_score(data, "key_quotes", 1)),
        ]

        return sum(weight * score for weight, score in signals)

    @staticmethod
    def compute_pass_2(data: BaseModel) -> float:
        """Compute the structural score for a StructureOutput.

        Weights field population (0.30) and relationship count (0.25) most
        heavily. Flow step density (0.20) captures whether the extracted
        steps are substantive or just single-token placeholders.
        """
        weights = {
            "field_population": 0.30,
            "relationship_count": 0.25,
            "flow_step_count": 0.20,
            "flow_sequence_count": 0.10,
            "layer_count": 0.10,
            "temporal_count": 0.05,
        }

        signals = [
            (weights["field_population"], ConfidenceScorer._field_population_rate(data)),
            (weights["relationship_count"], ConfidenceScorer._count_score(data, "relationships", 1)),
            (weights["flow_step_count"], ConfidenceScorer._flow_step_density(data)),
            (weights["flow_sequence_count"], ConfidenceScorer._count_score(data, "flow_sequences", 1)),
            (weights["layer_count"], ConfidenceScorer._count_score(data, "layer_signals", 1)),
            (weights["temporal_count"], ConfidenceScorer._count_score(data, "temporal_signals", 1)),
        ]

        return sum(weight * score for weight, score in signals)

    @staticmethod
    def compute_pass_3(data: BaseModel) -> float:
        """Compute the structural score for a ReasoningOutput.

        Tradeoff completeness (0.45) dominates — a ReasoningOutput with
        trades that have only a benefit or only a cost is penalized heavily.
        Field population (0.30) checks that the output model is broadly filled.
        """
        weights = {
            "tradeoff_completeness": 0.45,
            "field_population": 0.30,
            "tradeoff_count": 0.15,
            "constraint_count": 0.10,
        }

        signals = [
            (weights["tradeoff_completeness"], ConfidenceScorer._tradeoff_completeness(data)),
            (weights["field_population"], ConfidenceScorer._field_population_rate(data)),
            (weights["tradeoff_count"], ConfidenceScorer._count_score(data, "tradeoff_signals", 1)),
            (weights["constraint_count"], ConfidenceScorer._count_score(data, "constraint_signals", 1)),
        ]

        return sum(weight * score for weight, score in signals)

    # ── Individual signal functions ────────────────────────────────────

    @staticmethod
    def _entity_density(data: BaseModel) -> float:
        """Score entity count against a baseline of 4 (saturates at 1.0)."""
        entities = getattr(data, "named_entities", [])
        return min(1.0, len(entities) / 4.0)

    @staticmethod
    def _concept_completeness(data: BaseModel) -> float:
        """Score concepts by definition substance (≥3 words) and count.

        A concept with an inline_definition of fewer than 3 words is likely
        a filler. Multiplied by count density (≥2 concepts needed for full
        score). Both dimensions saturate at 1.0.
        """
        concepts = getattr(data, "concept_definitions", [])
        if not concepts:
            return 0.0
        substantive = sum(
            1 for c in concepts
            if len(getattr(c, "inline_definition", "").split()) >= 3
        )
        return (substantive / len(concepts)) * min(1.0, len(concepts) / 2.0)

    @staticmethod
    def _field_population_rate(data: BaseModel) -> float:
        """Return fraction of top-level model fields that are non-empty.

        Skips the ``confidence_score`` field (it's always populated by the LLM
        and not meaningful for structural quality). String fields count as
        populated only if non-whitespace. List fields count only if they have
        at least one item. Booleans, ints, and floats always count as populated
        since they have meaningful defaults.
        """
        fields = data.model_fields
        total = 0
        populated = 0
        for name, field_info in fields.items():
            if name == "confidence_score":
                continue
            total += 1
            value = getattr(data, name, None)
            if value is None:
                continue
            if isinstance(value, list):
                if len(value) > 0:
                    populated += 1
            elif isinstance(value, str):
                if value.strip():
                    populated += 1
            elif isinstance(value, bool):
                populated += 1
            elif isinstance(value, (int, float)):
                populated += 1
            else:
                populated += 1
        return populated / max(total, 1)

    @staticmethod
    def _count_score(data: BaseModel, field_name: str, threshold: int) -> float:
        """Score a list field by how many items it has, saturating at 1.0.

        The threshold is the count needed to reach a full score. For example,
        ``threshold=1`` means any non-empty list scores 1.0; ``threshold=3``
        means a list needs 3 items to score 1.0.
        """
        value = getattr(data, field_name, [])
        if not isinstance(value, list):
            return 0.0
        return min(1.0, len(value) / threshold)

    @staticmethod
    def _flow_step_density(data: BaseModel) -> float:
        """Score total flow steps across all FlowSequences against baseline of 3.

        Iterates the nested ``flow_sequences[].steps`` lists and sums their
        lengths. An article with one flow of 3 steps scores 1.0. Less than 3
        total steps produces a partial score.
        """
        flow_sequences = getattr(data, "flow_sequences", [])
        if not flow_sequences:
            return 0.0
        total_steps = sum(len(getattr(seq, "steps", [])) for seq in flow_sequences)
        return min(1.0, total_steps / 3.0)

    @staticmethod
    def _tradeoff_completeness(data: BaseModel) -> float:
        """Score tradeoffs by the fraction that have both a benefit and a cost.

        Pass 3 is required to extract only complete tradeoffs (benefit AND
        cost). A score of 1.0 means every tradeoff in the output has both
        fields populated; 0.5 means half do. An empty list returns 0.0
        (the LLM found no extractable tradeoffs).
        """
        tradeoffs = getattr(data, "tradeoff_signals", [])
        if not tradeoffs:
            return 0.0
        complete = sum(
            1
            for t in tradeoffs
            if getattr(t, "benefit", None) and getattr(t, "cost", None)
        )
        return complete / len(tradeoffs)

    @staticmethod
    def combined_confidence(self_reported: float, structural: float) -> float:
        """Combine self-reported and structural scores by taking the minimum.

        This is a conservative gate: if either signal says the output is weak,
        the combined score reflects it. The structural score acts as a floor
        so naive self-reporting cannot inflate confidence.
        """
        return min(self_reported, structural)
