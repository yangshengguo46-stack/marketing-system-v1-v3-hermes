"""Marketing projection adapter over the source-agnostic Human Observation Core.

These structures remain account-planning compatibility projections.  They are
not the canonical human model and cannot revise the core.  Maslow-like needs,
Jungian cognition, and existence strategies stay bounded and falsifiable.
"""

from __future__ import annotations

from typing import Any


HUMAN_PROJECTION_MODEL_VERSION = "marketing-human-projection-adapter-v0.4"
EXISTENCE_STRATEGIES = {"preserve", "confirm", "expand", "continue", "unknown"}
JUNGIAN_FUNCTIONS = {"Se", "Si", "Ne", "Ni", "Te", "Ti", "Fe", "Fi", "unknown"}
COLLECTIVE_MECHANISMS = {
    "identity_convergence",
    "emotional_contagion",
    "normative_pressure",
    "suggestibility",
    "deindividuation",
    "polarization",
    "imitation",
    "authority_transfer",
    "rumor_cascade",
    "collective_effervescence",
    "unknown",
}
COLLECTIVE_LENSES = {
    "crowd_psychology_synthesis",
    "le_bon_historical_lens",
    "social_identity",
    "deindividuation",
    "emergent_norm",
    "information_cascade",
    "unknown",
}
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
        "premise": "revisable_existence_strategy_research_seed",
        "role": "marketing_projection_adapter_not_core_truth",
        "canonical_owner": "human_observer.human_model_revisions",
        "directly_observable": False,
        "directly_scoreable": False,
        "fixed_axiom": False,
        "projection_chain": [
            "environment_and_embodied_constraints",
            "need_projection",
            "cognitive_projection",
            "existence_strategy",
            "observable_behavior",
            "collective_mechanism_projection",
            "platform_allocation",
            "delayed_outcome_and_retro_calibration",
        ],
        "guardrail": (
            "This Marketing projection cannot establish human truth.  The core seed and every "
            "theory weight remain revisable against sealed predictions and counterevidence."
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
        framework = _text(raw.get("framework"), limit=120).lower()
        dimension = _text(raw.get("dimension"), limit=120)
        hypothesis = _text(raw.get("hypothesis"), limit=800)
        if not framework or not dimension or not hypothesis:
            raise ValueError(
                "cognitive hypothesis requires framework, dimension, and hypothesis"
            )
        if framework not in {"jungian_eight_functions", "jungian_functions"}:
            raise ValueError(
                f"unsupported cognitive framework at index {index}; "
                "use jungian_eight_functions"
            )
        canonical_dimension = {
            item.lower(): item for item in JUNGIAN_FUNCTIONS
        }.get(dimension.lower())
        if canonical_dimension is None:
            raise ValueError(f"unsupported Jungian function at index {index}")
        result.append(
            {
                "framework": "jungian_eight_functions",
                "dimension": canonical_dimension,
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


def normalize_collective_projection_hypotheses(value: Any) -> list[dict[str, Any]]:
    """Normalize falsifiable group-field hypotheses, never individual psychology."""

    rows = _rows(value, field="collective_projection_hypotheses", limit=16)
    result: list[dict[str, Any]] = []
    for index, raw in enumerate(rows):
        leaked = sorted(
            {
                "user_id",
                "platform_user_id",
                "handle",
                "profile_url",
                "diagnosis",
                "permanent_type",
                "medical_claim",
            }
            & set(raw)
        )
        if leaked:
            raise ValueError(
                f"collective hypothesis cannot identify or diagnose a person at index {index}: "
                + ", ".join(leaked)
            )
        lens = str(raw.get("lens") or raw.get("framework") or "unknown").strip().lower()
        mechanism = str(raw.get("mechanism") or "unknown").strip().lower()
        if lens not in COLLECTIVE_LENSES:
            raise ValueError(f"unsupported collective psychology lens at index {index}")
        if mechanism not in COLLECTIVE_MECHANISMS:
            raise ValueError(f"unsupported collective mechanism at index {index}")
        hypothesis = _text(raw.get("hypothesis"), limit=800)
        observable_signals = _strings(
            raw.get("observable_signals"), field="observable_signals", limit=12
        )
        disconfirming_signals = _strings(
            raw.get("disconfirming_signals"),
            field="disconfirming_signals",
            limit=12,
        )
        if not hypothesis or not observable_signals or not disconfirming_signals:
            raise ValueError(
                "collective hypothesis requires hypothesis, observable_signals, and "
                f"disconfirming_signals at index {index}"
            )
        result.append(
            {
                "lens": lens,
                "mechanism": mechanism,
                "cohort": _text(raw.get("cohort"), limit=240),
                "context": _text(raw.get("context"), limit=600),
                "hypothesis": hypothesis,
                "observable_signals": observable_signals,
                "evidence_basis": _strings(
                    raw.get("evidence_basis"), field="evidence_basis", limit=12
                ),
                "disconfirming_signals": disconfirming_signals,
                "confidence": _soft_confidence(raw.get("confidence")),
                "data_gaps": _strings(raw.get("data_gaps"), field="data_gaps", limit=12),
                "guardrail": "anonymous_group_mechanism_not_individual_motive_or_universal_law",
            }
        )
    return result


def build_human_projection_model(
    *,
    need_projections: Any = None,
    cognitive_projections: Any = None,
    existence_strategies: Any = None,
    collective_projections: Any = None,
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
        "collective_projection_hypotheses": normalize_collective_projection_hypotheses(
            collective_projections
        ),
        "epistemic_status": "revisable_projection_hypotheses",
        "observer_contract": {
            "mode": "read_only_marketing_projection_adapter",
            "source_of_human_truth": False,
            "core_writeback_allowed": False,
            "user_mutable": False,
            "conversation_mutable": False,
            "single_sample_generalization_allowed": False,
        },
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
