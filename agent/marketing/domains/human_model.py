"""Bounded, falsifiable projections from an ontological existence premise.

Existence is the model's philosophical root, not an observable label. Maslow-like
needs, Jungian cognition, and existence strategies are revisable projections
used to explain behavior without turning inference into diagnosis or identity.
"""

from __future__ import annotations

from typing import Any


HUMAN_PROJECTION_MODEL_VERSION = "human-projection-model-v0.2"
EXISTENCE_STRATEGIES = {"preserve", "confirm", "expand", "continue", "unknown"}
MASLOW_NEEDS = {
    "physiological",
    "safety",
    "belonging",
    "esteem",
    "self_actualization",
    "transcendence",
    "unknown",
}
FORBIDDEN_COGNITIVE_KEYS = {
    "diagnosis", "disorder", "clinical_label", "permanent_type", "medical_claim"
}


def existence_ontology_contract() -> dict[str, Any]:
    return {
        "premise": "existence_precedes_observable_behavior",
        "role": "ontological_root_not_measured_variable",
        "directly_observable": False,
        "directly_scoreable": False,
        "projection_chain": [
            "environment_and_embodied_constraints",
            "need_projection",
            "cognitive_projection",
            "existence_strategy",
            "observable_behavior",
            "social_and_platform_feedback",
        ],
        "guardrail": (
            "Only projections and behavior are falsifiable here; the ontological premise must "
            "never be presented as a measured psychological fact."
        ),
    }


def normalize_need_projection_hypotheses(value: Any) -> list[dict[str, Any]]:
    rows = _rows(value, field="need_projection_hypotheses", limit=12)
    result: list[dict[str, Any]] = []
    for index, raw in enumerate(rows):
        need = str(raw.get("need") or "unknown").strip().lower()
        if need not in MASLOW_NEEDS:
            raise ValueError(f"unsupported Maslow need projection at index {index}")
        result.append(
            {
                "framework": "maslow_hierarchy",
                "need": need,
                "subject": _text(raw.get("subject"), limit=240),
                "context": _text(raw.get("context"), limit=600),
                "observable_signals": _strings(
                    raw.get("observable_signals"), field="observable_signals", limit=12
                ),
                "evidence_basis": _strings(
                    raw.get("evidence_basis"), field="evidence_basis", limit=12
                ),
                "disconfirming_signals": _strings(
                    raw.get("disconfirming_signals"),
                    field="disconfirming_signals",
                    limit=12,
                ),
                "confidence": _soft_confidence(raw.get("confidence")),
                "data_gaps": _strings(raw.get("data_gaps"), field="data_gaps", limit=12),
                "guardrail": "need_projection_not_direct_observation",
            }
        )
    return result


def normalize_existence_strategy_hypotheses(value: Any) -> list[dict[str, Any]]:
    rows = _rows(value, field="existence_strategy_hypotheses", limit=12)
    result: list[dict[str, Any]] = []
    for index, raw in enumerate(rows):
        strategy = str(raw.get("strategy") or raw.get("direction") or "unknown").strip().lower()
        if strategy not in EXISTENCE_STRATEGIES:
            raise ValueError(f"unsupported existence strategy at index {index}")
        result.append(
            {
                "subject": _text(raw.get("subject"), limit=240),
                "strategy": strategy,
                "context": _text(raw.get("context"), limit=600),
                "observable_signals": _strings(
                    raw.get("observable_signals"), field="observable_signals", limit=12
                ),
                "evidence_basis": _strings(
                    raw.get("evidence_basis"), field="evidence_basis", limit=12
                ),
                "disconfirming_signals": _strings(
                    raw.get("disconfirming_signals"),
                    field="disconfirming_signals",
                    limit=12,
                ),
                "confidence": _soft_confidence(raw.get("confidence")),
                "data_gaps": _strings(raw.get("data_gaps"), field="data_gaps", limit=12),
                "guardrail": "behavioral_strategy_not_existence_itself",
            }
        )
    return result


def normalize_cognitive_projection_hypotheses(value: Any) -> list[dict[str, Any]]:
    rows = _rows(value, field="cognitive_projection_hypotheses", limit=16)
    result: list[dict[str, Any]] = []
    for index, raw in enumerate(rows):
        leaked = sorted(FORBIDDEN_COGNITIVE_KEYS & set(raw))
        if leaked:
            raise ValueError(
                f"cognitive hypothesis cannot contain diagnostic keys at index {index}: "
                + ", ".join(leaked)
            )
        framework = _text(raw.get("framework"), limit=120)
        dimension = _text(raw.get("dimension"), limit=120)
        hypothesis = _text(raw.get("hypothesis"), limit=800)
        if not framework or not dimension or not hypothesis:
            raise ValueError(
                "cognitive hypothesis requires framework, dimension, and hypothesis"
            )
        result.append(
            {
                "framework": framework,
                "dimension": dimension,
                "hypothesis": hypothesis,
                "confidence": _soft_confidence(raw.get("confidence")),
                "evidence_basis": _strings(
                    raw.get("evidence_basis"), field="evidence_basis", limit=12
                ),
                "disconfirming_signals": _strings(
                    raw.get("disconfirming_signals"),
                    field="disconfirming_signals",
                    limit=12,
                ),
                "review_after": _text(raw.get("review_after"), limit=80),
                "data_gaps": _strings(raw.get("data_gaps"), field="data_gaps", limit=12),
                "guardrail": "cognitive_projection_not_diagnosis_or_permanent_type",
            }
        )
    return result


def build_human_projection_model(
    *,
    need_projections: Any = None,
    cognitive_projections: Any = None,
    existence_strategies: Any = None,
) -> dict[str, Any]:
    return {
        "version": HUMAN_PROJECTION_MODEL_VERSION,
        "existence_ontology": existence_ontology_contract(),
        "need_projection_hypotheses": normalize_need_projection_hypotheses(
            need_projections
        ),
        "cognitive_projection_hypotheses": normalize_cognitive_projection_hypotheses(
            cognitive_projections
        ),
        "existence_strategy_hypotheses": normalize_existence_strategy_hypotheses(
            existence_strategies
        ),
        "epistemic_status": "revisable_projection_hypotheses",
    }


def normalize_existence_hypotheses(value: Any) -> list[dict[str, Any]]:
    """Read compatibility for v0.1 callers; new output uses strategy semantics."""

    return normalize_existence_strategy_hypotheses(value)


def normalize_cognitive_style_hypotheses(value: Any) -> list[dict[str, Any]]:
    """Read compatibility for v0.1 callers; new output uses projection semantics."""

    return normalize_cognitive_projection_hypotheses(value)


def _rows(value: Any, *, field: str, limit: int) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    if len(value) > limit:
        raise ValueError(f"{field} exceeds {limit} items")
    if any(not isinstance(item, dict) for item in value):
        raise ValueError(f"{field} entries must be objects")
    return value


def _strings(value: Any, *, field: str, limit: int) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    if len(value) > limit:
        raise ValueError(f"{field} exceeds {limit} items")
    return [_text(item, limit=400) for item in value if _text(item, limit=400)]


def _soft_confidence(value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError("hypothesis confidence must be numeric")
    try:
        result = float(value if value is not None else 0.3)
    except (TypeError, ValueError) as exc:
        raise ValueError("hypothesis confidence must be numeric") from exc
    if not 0 <= result <= 0.7:
        raise ValueError("human-model hypothesis confidence must be between 0 and 0.7")
    return round(result, 4)


def _text(value: Any, *, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]
