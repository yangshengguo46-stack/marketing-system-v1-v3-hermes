"""Governed calibration over repeated publishing retrospectives.

One successful or failed post should not rewrite a creator's strategy.  This
module looks for repeated, evidence-backed patterns and turns them into
``weight`` learning candidates.  Candidates remain pending until an explicit
review path accepts/rejects them.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from typing import Any

from .influence_score import BUCKET_VALUES, INFLUENCE_SCORE_VERSION, RISK_BUCKET_VALUES


GOVERNANCE_VERSION = "learning-governance-v0.1"
WEIGHT_REPLAY_VERSION = "weight-candidate-replay-v0.2"

HIGH_BUCKETS = {"high", "spike"}
LOW_BUCKETS = {"zero", "low"}
POSITIVE_REPLAY_DIMENSIONS = ("attention", "retention", "trust", "action", "fit")
COMPONENT_DIMENSIONS = {
    "PlatformReachPotential": "attention",
    "HumanAttentionKernel": "attention",
    "RetentionDesign": "retention",
    "PersuasionScore": "trust",
    "AccountFit": "fit",
    "BusinessValue": "action",
    "RiskPenalty": "risk",
}
CONFLICTING_RULES: dict[str, set[str]] = {
    "retention_gap_after_attention": {"retention_strength_after_attention"},
    "action_gap_after_attention": {"action_strength_after_attention"},
    "trust_signal_strength": {"trust_signal_absent"},
    "risk_pressure": {"risk_absent"},
    "prediction_over_optimistic": {"prediction_under_optimistic"},
    "prediction_under_optimistic": {"prediction_over_optimistic"},
}


def _proposal(candidate: dict[str, Any]) -> dict[str, Any]:
    proposal = candidate.get("proposal")
    return proposal if isinstance(proposal, dict) else {}


def _label(candidate: dict[str, Any], dimension: str) -> dict[str, Any] | None:
    labels = (_proposal(candidate).get("metric_labels") or {}).get("labels") or {}
    label = labels.get(dimension)
    return label if isinstance(label, dict) else None


def _bucket(candidate: dict[str, Any], dimension: str) -> str:
    label = _label(candidate, dimension)
    return str((label or {}).get("bucket") or "")


def _retro(candidate: dict[str, Any]) -> dict[str, Any]:
    retro = _proposal(candidate).get("retro")
    return retro if isinstance(retro, dict) else {}


def _candidate_score(candidate: dict[str, Any]) -> float:
    score = (_proposal(candidate).get("influence_score") or {}).get("score")
    if isinstance(score, (int, float)):
        return float(score)
    return 0.0


def _score_components(candidate: dict[str, Any]) -> dict[str, Any]:
    components = (_proposal(candidate).get("influence_score") or {}).get("components")
    return components if isinstance(components, dict) else {}


def _component_value(candidate: dict[str, Any], component: str) -> float | None:
    raw = _score_components(candidate).get(component)
    value = raw.get("value") if isinstance(raw, dict) else None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return max(0.0, min(1.0, float(value)))
    dimension = COMPONENT_DIMENSIONS.get(component)
    if not dimension:
        return None
    bucket = _bucket(candidate, dimension)
    if dimension == "risk":
        return RISK_BUCKET_VALUES.get(bucket)
    return BUCKET_VALUES.get(bucket)


def _actual_success_score(candidate: dict[str, Any]) -> float | None:
    """Approximate realised result quality from published metric labels.

    This is deliberately simple and explainable.  It is used only for replay
    safety checks, not as a secret strategy score.
    """

    values = [
        BUCKET_VALUES[bucket]
        for dimension in POSITIVE_REPLAY_DIMENSIONS
        if (bucket := _bucket(candidate, dimension)) in BUCKET_VALUES
    ]
    if not values:
        score = _candidate_score(candidate)
        return max(0.0, min(1.0, score / 100)) if score else None
    realised = sum(values) / len(values)
    risk = RISK_BUCKET_VALUES.get(_bucket(candidate, "risk"))
    if risk is not None:
        realised -= risk * 0.2
    return round(max(0.0, min(1.0, realised)), 3)


def _rule_hits(candidate: dict[str, Any]) -> list[str]:
    hits: list[str] = []
    attention = _bucket(candidate, "attention")
    retention = _bucket(candidate, "retention")
    action = _bucket(candidate, "action")
    trust = _bucket(candidate, "trust")
    risk = _bucket(candidate, "risk")
    bias = str(_retro(candidate).get("bias_direction") or "")

    if attention in HIGH_BUCKETS and retention in LOW_BUCKETS:
        hits.append("retention_gap_after_attention")
    if attention in HIGH_BUCKETS and action in LOW_BUCKETS:
        hits.append("action_gap_after_attention")
    if trust in HIGH_BUCKETS:
        hits.append("trust_signal_strength")
    if risk in {"mid", "high", "spike"}:
        hits.append("risk_pressure")
    if bias == "over":
        hits.append("prediction_over_optimistic")
    if bias == "under":
        hits.append("prediction_under_optimistic")
    return hits


def _rule_conflicts(candidate: dict[str, Any], rule_key: str) -> list[str]:
    attention = _bucket(candidate, "attention")
    retention = _bucket(candidate, "retention")
    action = _bucket(candidate, "action")
    trust = _bucket(candidate, "trust")
    risk = _bucket(candidate, "risk")
    conflicts: list[str] = []

    if rule_key == "retention_gap_after_attention" and attention in HIGH_BUCKETS and retention in HIGH_BUCKETS:
        conflicts.append("retention_strength_after_attention")
    if rule_key == "action_gap_after_attention" and attention in HIGH_BUCKETS and action in HIGH_BUCKETS:
        conflicts.append("action_strength_after_attention")
    if rule_key == "trust_signal_strength" and trust in LOW_BUCKETS:
        conflicts.append("trust_signal_absent")
    if rule_key == "risk_pressure" and risk in {"zero", "low"}:
        conflicts.append("risk_absent")

    hits = set(_rule_hits(candidate))
    conflicts.extend(sorted(CONFLICTING_RULES.get(rule_key, set()) & hits))
    return conflicts


def _label_buckets(candidate: dict[str, Any]) -> dict[str, str]:
    buckets: dict[str, str] = {}
    for dimension in ("attention", "retention", "trust", "action", "fit", "risk"):
        bucket = _bucket(candidate, dimension)
        if bucket:
            buckets[dimension] = bucket
    return buckets


def _safe_get(store: Any, getter: str, identifier: Any) -> dict[str, Any] | None:
    value = str(identifier or "").strip()
    if not value:
        return None
    try:
        result = getattr(store, getter)(value)
    except (AttributeError, KeyError, ValueError, TypeError):
        return None
    return result if isinstance(result, dict) else None


def _feature_snapshot_summary(asset: dict[str, Any] | None) -> dict[str, Any] | None:
    if not asset:
        return None
    content = asset.get("content") if isinstance(asset.get("content"), dict) else {}
    snapshot = content.get("feature_snapshot")
    if not isinstance(snapshot, dict):
        return None
    evidence = snapshot.get("evidence") if isinstance(snapshot.get("evidence"), dict) else {}
    structure = snapshot.get("structure") if isinstance(snapshot.get("structure"), dict) else {}
    identity = snapshot.get("identity") if isinstance(snapshot.get("identity"), dict) else {}
    return {
        "id": snapshot.get("id"),
        "version": snapshot.get("version"),
        "kind": snapshot.get("kind"),
        "platforms": list(identity.get("platforms") or []),
        "evidence_ready": evidence.get("ready"),
        "evidence_with_url": evidence.get("with_url"),
        "structure_keys": sorted(str(key) for key in structure.keys()),
    }


def _replay_case_audit(store: Any, candidate: dict[str, Any]) -> dict[str, Any]:
    """Return compact audit context for one historical retro candidate."""

    asset = _safe_get(store, "get_content_asset", candidate.get("asset_id"))
    preflight = _safe_get(store, "get_preflight_record", candidate.get("preflight_id"))
    prediction = _safe_get(store, "get_prediction", candidate.get("prediction_id"))
    snapshot = _feature_snapshot_summary(asset)
    preflight_decision = (
        (preflight.get("decision") or {}).get("preflight_decision")
        if isinstance((preflight or {}).get("decision"), dict)
        else None
    )
    if not isinstance(preflight_decision, dict):
        preflight_decision = preflight.get("decision") if isinstance((preflight or {}).get("decision"), dict) else {}
    return {
        "asset_id": candidate.get("asset_id"),
        "preflight_id": candidate.get("preflight_id"),
        "prediction_id": candidate.get("prediction_id"),
        "has_asset": asset is not None,
        "has_feature_snapshot": snapshot is not None,
        "has_preflight": preflight is not None,
        "has_prediction": prediction is not None,
        "feature_snapshot": snapshot,
        "asset_kind": snapshot.get("kind") if snapshot else ((asset or {}).get("content") or {}).get("production_kind"),
        "preflight_status": preflight_decision.get("status"),
        "prediction_status": (prediction or {}).get("status"),
        "metric_label_buckets": _label_buckets(candidate),
    }


def _coverage_ratio(count: int, total: int) -> float:
    return round(count / total, 3) if total else 0.0


def _estimated_adjustment_delta(candidate: dict[str, Any], adjustment: dict[str, Any]) -> float | None:
    component = str(adjustment.get("component") or "")
    direction = str(adjustment.get("direction") or "")
    amount = adjustment.get("amount")
    if not isinstance(amount, (int, float)) or isinstance(amount, bool):
        return None
    value = _component_value(candidate, component)
    if value is None:
        return None

    # Positive delta means the proposed adjustment would have treated this
    # historical case as more promising; negative delta means more conservative.
    if component == "RiskPenalty" or direction == "increase_penalty":
        delta = -value * float(amount) * 100
    elif direction in {"increase_weight", "increase_prior"}:
        delta = (value - 0.5) * float(amount) * 100
    elif direction == "decrease_prior":
        delta = (0.5 - value) * float(amount) * 100
    else:
        delta = 0.0
    return round(delta, 3)


RULE_RECOMMENDATIONS: dict[str, dict[str, Any]] = {
    "retention_gap_after_attention": {
        "component": "RetentionDesign",
        "direction": "increase_weight",
        "amount": 0.04,
        "recommendation": "连续内容能拿到注意力但留存偏弱，后续预演应更重视中段结构、节奏和信息密度。",
    },
    "action_gap_after_attention": {
        "component": "BusinessValue",
        "direction": "increase_weight",
        "amount": 0.04,
        "recommendation": "连续内容有曝光但缺少关注/点击/转化，后续预演应更重视行动路径和商业目标。",
    },
    "trust_signal_strength": {
        "component": "PersuasionScore",
        "direction": "increase_prior",
        "amount": 0.03,
        "recommendation": "连续内容出现较强信任/互动信号，相关表达方式可以作为账号优势候选。",
    },
    "risk_pressure": {
        "component": "RiskPenalty",
        "direction": "increase_penalty",
        "amount": 0.05,
        "recommendation": "连续内容出现风险或负反馈，后续预演应更严格扣风险分。",
    },
    "prediction_over_optimistic": {
        "component": "PlatformReachPotential",
        "direction": "decrease_prior",
        "amount": 0.04,
        "recommendation": "连续预测过度乐观，后续预演应下调冷启动分发预期。",
    },
    "prediction_under_optimistic": {
        "component": "PlatformReachPotential",
        "direction": "increase_prior",
        "amount": 0.03,
        "recommendation": "连续预测偏保守，后续预演可适度上调该账号/题材的分发潜力。",
    },
}


def summarize_learning_patterns(
    candidates: list[dict[str, Any]],
    *,
    min_support: int = 3,
) -> dict[str, Any]:
    """Summarise repeated retrospective signals without writing state."""

    usable = [
        candidate for candidate in candidates
        if candidate.get("status") in {"pending", "accepted"}
        and _proposal(candidate).get("kind") == "published_metric_retro"
    ]
    counter: Counter[str] = Counter()
    evidence_by_rule: dict[str, list[dict[str, Any]]] = {}
    for candidate in usable:
        for rule_key in _rule_hits(candidate):
            counter[rule_key] += 1
            evidence_by_rule.setdefault(rule_key, []).append(candidate)

    if not counter:
        return {
            "version": GOVERNANCE_VERSION,
            "status": "no_pattern",
            "sample_size": len(usable),
            "min_support": min_support,
            "patterns": [],
        }

    patterns = [
        {
            "rule_key": rule_key,
            "support_count": count,
            "ready": count >= min_support,
            "recommendation": RULE_RECOMMENDATIONS[rule_key]["recommendation"],
        }
        for rule_key, count in counter.most_common()
    ]
    ready = [pattern for pattern in patterns if pattern["ready"]]
    return {
        "version": GOVERNANCE_VERSION,
        "status": "ready" if ready else "insufficient_evidence",
        "sample_size": len(usable),
        "min_support": min_support,
        "patterns": patterns,
        "top_rule_key": ready[0]["rule_key"] if ready else patterns[0]["rule_key"],
        "top_support_count": ready[0]["support_count"] if ready else patterns[0]["support_count"],
        "_evidence": evidence_by_rule,
    }


def propose_weight_candidate_from_recent_retros(
    store: Any,
    *,
    user_id: str = "default",
    account_id: str | None = None,
    platform: str | None = None,
    window: int = 12,
    min_support: int = 3,
) -> dict[str, Any]:
    """Create a pending weight candidate if repeated signals cross threshold."""

    candidates = store.list_learning_candidates(
        candidate_type="memory",
        user_id=user_id,
        account_id=account_id,
        platform=platform,
        limit=window,
    )
    summary = summarize_learning_patterns(candidates, min_support=min_support)
    if summary["status"] != "ready":
        public_summary = {key: value for key, value in summary.items() if key != "_evidence"}
        return {
            **public_summary,
            "weight_candidate_id": None,
            "candidate_status": None,
        }

    rule_key = str(summary["top_rule_key"])
    existing = [
        candidate for candidate in store.list_learning_candidates(
            candidate_type="weight",
            status="pending",
            user_id=user_id,
            account_id=account_id,
            platform=platform,
            limit=50,
        )
        if _proposal(candidate).get("rule_key") == rule_key
    ]
    if existing:
        public_summary = {key: value for key, value in summary.items() if key != "_evidence"}
        return {
            **public_summary,
            "status": "candidate_exists",
            "weight_candidate_id": existing[0]["id"],
            "candidate_status": existing[0]["status"],
        }

    support = summary["_evidence"][rule_key][:summary["top_support_count"]]
    rule = RULE_RECOMMENDATIONS[rule_key]
    receipt_refs: list[str] = []
    evidence_refs: list[str] = []
    prediction_ids: list[str] = []
    scores: list[float] = []
    for candidate in support:
        evidence_refs.append(f"learning_candidate:{candidate['id']}")
        evidence_refs.extend(str(ref) for ref in candidate.get("evidence_refs") or [])
        receipt_refs.extend(str(ref) for ref in candidate.get("receipt_refs") or [])
        if candidate.get("prediction_id"):
            prediction_ids.append(str(candidate["prediction_id"]))
        score = _candidate_score(candidate)
        if score:
            scores.append(score)

    # Preserve order while removing duplicates.
    receipt_refs = list(dict.fromkeys(receipt_refs))
    evidence_refs = list(dict.fromkeys(evidence_refs))
    prediction_ids = list(dict.fromkeys(prediction_ids))
    avg_score = round(sum(scores) / len(scores), 1) if scores else None
    candidate = store.create_learning_candidate(
        candidate_type="weight",
        user_id=user_id,
        account_id=account_id,
        platform=platform,
        receipt_refs=receipt_refs,
        evidence_refs=evidence_refs,
        prediction_id=prediction_ids[0] if len(prediction_ids) == 1 else None,
        proposal={
            "kind": "influence_weight_adjustment",
            "version": GOVERNANCE_VERSION,
            "score_version": INFLUENCE_SCORE_VERSION,
            "rule_key": rule_key,
            "support_count": summary["top_support_count"],
            "sample_size": summary["sample_size"],
            "observed_patterns": [
                {key: pattern[key] for key in ("rule_key", "support_count", "recommendation")}
                for pattern in summary["patterns"]
            ],
            "proposed_adjustment": {
                "component": rule["component"],
                "direction": rule["direction"],
                "amount": rule["amount"],
            },
            "recommendation": rule["recommendation"],
            "average_influence_score": avg_score,
            "guardrail": "pending weight candidate only; do not change durable strategy weights without review and replay",
        },
        confidence=min(0.86, 0.42 + 0.08 * summary["top_support_count"] + (0.08 if avg_score else 0.0)),
    )
    public_summary = {key: value for key, value in summary.items() if key != "_evidence"}
    return {
        **public_summary,
        "status": "candidate_created",
        "weight_candidate_id": candidate["id"],
        "candidate_status": candidate["status"],
    }


def propose_publish_recovery_skill_candidate(
    publishing: Any,
    store: Any,
    *,
    user_id: str,
    account_id: str,
    platform: str,
    provider: str,
    content_kind: str | None = None,
    min_support: int = 3,
) -> dict[str, Any]:
    """Propose a procedural Skill only from repeated verified recoveries."""

    required = max(3, min(int(min_support), 20))
    recoveries = publishing.list_verified_recoveries(
        user_id=user_id,
        account_id=account_id,
        platform=platform,
        provider=provider,
        content_kind=content_kind,
        limit=100,
    )
    if len(recoveries) < required:
        return {
            "status": "insufficient_recovery_evidence",
            "support_count": len(recoveries),
            "required_support": required,
            "skill_candidate_id": None,
            "guardrail": "final success rows alone cannot become procedural memory",
        }
    selected = recoveries[:required]
    resolved_kind = str(content_kind or selected[0].get("content_kind") or "content")
    identity = f"{user_id}:{platform}:{provider}:{resolved_kind}:publish-unknown-recovery-v1"
    slug_source = f"marketing-{platform}-{provider}-{resolved_kind}-publish-recovery".lower()
    slug = re.sub(r"[^a-z0-9._-]+", "-", slug_source).strip("-._")
    if len(slug) > 64:
        slug = f"{slug[:51].rstrip('-._')}-{hashlib.sha256(identity.encode()).hexdigest()[:10]}"
    steps = [
        "Reuse the original pre-logged publish action and idempotency key.",
        "Treat a disconnected or timed-out provider result as unknown, never as failed or successful.",
        "Query the platform creator-center works list before considering any retry.",
        "Match the intended asset using the target platform, content fingerprint, title and time window.",
        "Settle the original action only with a verified platform post id or stable work URL.",
        "If no matching work is found, keep the action unknown and ask for inspection instead of publishing again.",
        "After verified recovery, resume metric checkpoints on the original action.",
    ]
    receipt_refs = list(dict.fromkeys(
        str(item[key])
        for item in selected
        for key in ("unknown_receipt_id", "published_receipt_id")
    ))
    candidate = store.create_learning_candidate(
        candidate_type="skill",
        user_id=user_id,
        account_id=account_id,
        platform=platform,
        receipt_refs=receipt_refs,
        evidence_refs=[f"publish_action:{item['action_id']}" for item in selected],
        proposal={
            "kind": "publish_unknown_recovery_workflow",
            "version": GOVERNANCE_VERSION,
            "skill_name": slug,
            "description": (
                f"Recover uncertain {platform} publishing through {provider} without duplicate posts."
            ),
            "trigger": (
                "Use when a publish provider disconnects, times out, or returns unknown after the "
                "external action may already have happened."
            ),
            "steps": steps,
            "platform": platform,
            "provider": provider,
            "content_kind": resolved_kind,
            "support_count": len(selected),
            "required_support": required,
            "recovery_pairs": [
                {
                    "action_id": item["action_id"],
                    "unknown_receipt_id": item["unknown_receipt_id"],
                    "published_receipt_id": item["published_receipt_id"],
                    "failure_code": item.get("failure_code"),
                    "verification_source": item.get("verification_source"),
                }
                for item in selected
            ],
            "guardrail": (
                "pending Skill candidate only; user must review the exact deterministic workflow "
                "before Hermes creates procedural memory"
            ),
        },
        confidence=min(0.92, 0.62 + len(selected) * 0.08),
        source_key=f"publish-recovery-skill:{hashlib.sha256(identity.encode()).hexdigest()}",
    )
    return {
        "status": "candidate_ready",
        "support_count": len(selected),
        "required_support": required,
        "skill_candidate_id": candidate["id"],
        "candidate_status": candidate["status"],
        "guardrail": "no Skill was written; explicit candidate review is required",
    }


def replay_weight_candidate(
    store: Any,
    candidate_id: str,
    *,
    window: int = 500,
    min_support: int | None = None,
    max_conflict_ratio: float = 0.25,
    max_harm_count: int = 0,
) -> dict[str, Any]:
    """Replay a pending weight candidate against historical retrospectives.

    The replay is an internal safety gate.  It explains whether the proposed
    calibration is consistent with past published-result evidence, but it does
    not mutate durable strategy weights.
    """

    if not candidate_id:
        raise ValueError("candidate_id is required")
    candidate = store.get_learning_candidate(candidate_id)
    proposal = _proposal(candidate)
    if candidate.get("candidate_type") != "weight" or proposal.get("kind") != "influence_weight_adjustment":
        return {
            "version": WEIGHT_REPLAY_VERSION,
            "candidate_id": candidate_id,
            "candidate_status": candidate.get("status"),
            "status": "invalid_candidate",
            "can_accept": False,
            "required_next_steps": ["选择 influence_weight_adjustment 类型的 weight 候选"],
            "guardrail": "replay only; no durable weights changed",
        }

    rule_key = str(proposal.get("rule_key") or "")
    adjustment = proposal.get("proposed_adjustment")
    if not rule_key or not isinstance(adjustment, dict):
        return {
            "version": WEIGHT_REPLAY_VERSION,
            "candidate_id": candidate_id,
            "candidate_status": candidate.get("status"),
            "status": "invalid_candidate",
            "can_accept": False,
            "required_next_steps": ["候选缺少 rule_key 或 proposed_adjustment"],
            "guardrail": "replay only; no durable weights changed",
        }

    required_support = max(1, int(min_support or proposal.get("support_count") or 3))
    replay_window = max(1, min(int(window), 500))
    retros = [
        item for item in store.list_learning_candidates(
            candidate_type="memory",
            user_id=candidate.get("user_id") or "default",
            account_id=candidate.get("account_id"),
            platform=candidate.get("platform"),
            limit=replay_window,
        )
        if item.get("status") in {"pending", "accepted"}
        and _proposal(item).get("kind") == "published_metric_retro"
    ]

    support_examples: list[str] = []
    conflict_examples: list[dict[str, Any]] = []
    harm_examples: list[dict[str, Any]] = []
    replayed: list[dict[str, Any]] = []
    coverage_counter: Counter[str] = Counter()
    support_count = 0
    conflict_count = 0
    harm_count = 0
    for retro_candidate in retros:
        hits = _rule_hits(retro_candidate)
        support = rule_key in hits
        conflicts = _rule_conflicts(retro_candidate, rule_key)
        actual_success = _actual_success_score(retro_candidate)
        estimated_delta = _estimated_adjustment_delta(retro_candidate, adjustment)
        harmful = (
            actual_success is not None
            and estimated_delta is not None
            and (
                (actual_success >= 0.68 and estimated_delta < -1.0)
                or (actual_success <= 0.32 and estimated_delta > 1.0)
            )
        )
        if support:
            support_count += 1
            support_examples.append(str(retro_candidate["id"]))
        if conflicts:
            conflict_count += 1
            conflict_examples.append({
                "candidate_id": retro_candidate["id"],
                "conflicts": conflicts,
            })
        if harmful:
            harm_count += 1
            harm_examples.append({
                "candidate_id": retro_candidate["id"],
                "actual_success": actual_success,
                "estimated_delta": estimated_delta,
            })
        case = _replay_case_audit(store, retro_candidate)
        for key in ("has_asset", "has_feature_snapshot", "has_preflight", "has_prediction"):
            if case.get(key):
                coverage_counter[key] += 1
        if case.get("metric_label_buckets"):
            coverage_counter["has_metric_labels"] += 1
        replayed.append({
            "candidate_id": retro_candidate["id"],
            "support": support,
            "conflicts": conflicts,
            "actual_success": actual_success,
            "estimated_delta": estimated_delta,
            "case": case,
        })

    sample_size = len(retros)
    coverage = {
        "asset_cases": coverage_counter["has_asset"],
        "with_feature_snapshot": coverage_counter["has_feature_snapshot"],
        "with_preflight": coverage_counter["has_preflight"],
        "with_prediction": coverage_counter["has_prediction"],
        "with_metric_labels": coverage_counter["has_metric_labels"],
        "feature_snapshot_ratio": _coverage_ratio(coverage_counter["has_feature_snapshot"], sample_size),
        "preflight_ratio": _coverage_ratio(coverage_counter["has_preflight"], sample_size),
        "prediction_ratio": _coverage_ratio(coverage_counter["has_prediction"], sample_size),
        "metric_label_ratio": _coverage_ratio(coverage_counter["has_metric_labels"], sample_size),
    }
    conflict_ratio = round(conflict_count / sample_size, 3) if sample_size else 0.0
    if sample_size < required_support:
        status = "insufficient_replay_samples"
        next_steps = ["至少需要更多发布复盘样本后再接受权重候选"]
    elif support_count < required_support:
        status = "failed_support"
        next_steps = ["历史样本没有稳定复现该规律，保持候选 pending 或拒绝"]
    elif conflict_ratio > max_conflict_ratio:
        status = "failed_conflict"
        next_steps = ["历史样本存在较高反例比例，先拆分账号/题材/平台上下文再判断"]
    elif harm_count > max_harm_count:
        status = "failed_historical_harm"
        next_steps = ["回放显示可能误伤成功内容，先降低调整幅度或补充分组规则"]
    else:
        status = "passed"
        next_steps = ["可以接受该候选，但仍只进入候选状态；永久权重需由后续策略模块单独生效"]

    can_accept = status == "passed" and candidate.get("status") == "pending"
    return {
        "version": WEIGHT_REPLAY_VERSION,
        "candidate_id": candidate_id,
        "candidate_status": candidate.get("status"),
        "status": status,
        "can_accept": can_accept,
        "rule_key": rule_key,
        "proposed_adjustment": adjustment,
        "audit_scope": {
            "mode": "full_history_up_to_500" if replay_window >= 500 else "bounded_window",
            "window": replay_window,
            "note": "replays historical published-result learning candidates in the candidate account/platform scope",
        },
        "sample_size": sample_size,
        "required_support": required_support,
        "support_count": support_count,
        "conflict_count": conflict_count,
        "conflict_ratio": conflict_ratio,
        "harm_count": harm_count,
        "coverage": coverage,
        "support_examples": support_examples[:8],
        "conflict_examples": conflict_examples[:8],
        "harm_examples": harm_examples[:8],
        "replayed_candidates": replayed[:20],
        "required_next_steps": next_steps,
        "guardrail": "replay only; no durable weights changed",
    }


def _confidence(value: Any) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return max(0.0, min(1.0, float(value)))
    return 0.5


def _strategy_candidate_from_weight(
    store: Any,
    candidate: dict[str, Any],
    replay: dict[str, Any],
) -> dict[str, Any]:
    """Create the second-review strategy candidate after replay acceptance.

    A replay-approved ``weight`` candidate is still not durable account truth.
    It becomes a separate ``strategy`` candidate so the operator can inspect
    the actual account-level change before the versioned strategy owner applies
    it.  ``source_key`` makes repeated decisions/restarts idempotent.
    """

    if candidate.get("status") != "accepted" or replay.get("status") != "passed":
        return {
            "status": "skipped",
            "reason": "weight_not_accepted_or_replay_not_passed",
            "strategy_candidate_id": None,
            "source_weight_candidate_id": candidate.get("id"),
            "replay_status": replay.get("status"),
        }
    proposal = _proposal(candidate)
    source_id = str(candidate.get("id") or "")
    strategy = store.create_learning_candidate(
        candidate_type="strategy",
        user_id=str(candidate.get("user_id") or "default"),
        account_id=str(candidate.get("account_id") or ""),
        platform=candidate.get("platform"),
        receipt_refs=list(candidate.get("receipt_refs") or []),
        evidence_refs=list(dict.fromkeys([
            f"learning_candidate:{source_id}",
            *(str(ref) for ref in (candidate.get("evidence_refs") or [])),
        ])),
        proposal={
            "kind": "account_influence_calibration",
            "version": GOVERNANCE_VERSION,
            "score_version": proposal.get("score_version") or INFLUENCE_SCORE_VERSION,
            "source_weight_candidate_id": source_id,
            "rule_key": proposal.get("rule_key"),
            "proposed_adjustment": proposal.get("proposed_adjustment"),
            "recommendation": proposal.get("recommendation"),
            "support_count": proposal.get("support_count"),
            "sample_size": replay.get("sample_size"),
            "replay": {
                "version": replay.get("version"),
                "status": replay.get("status"),
                "support_count": replay.get("support_count"),
                "conflict_count": replay.get("conflict_count"),
                "conflict_ratio": replay.get("conflict_ratio"),
                "harm_count": replay.get("harm_count"),
                "coverage": replay.get("coverage"),
            },
            "guardrail": (
                "pending strategy candidate only; explicit second review is required "
                "before versioned account calibration"
            ),
        },
        confidence=min(float(candidate.get("confidence") or 0.5), 0.9),
        source_key=f"strategy-calibration:{source_id}:{WEIGHT_REPLAY_VERSION}",
    )
    return {
        "status": "candidate_created" if strategy.get("status") == "pending" else "candidate_exists",
        "reason": "awaiting_explicit_strategy_review",
        "strategy_candidate_id": strategy["id"],
        "source_weight_candidate_id": source_id,
        "replay_status": replay.get("status"),
        "guardrail": "no durable strategy weights changed",
    }


def decide_weight_candidate_with_replay(
    store: Any,
    candidate_id: str,
    *,
    decision: str,
    reason: str | None = None,
    window: int = 500,
    min_support: int | None = None,
) -> dict[str, Any]:
    """Accept/reject a weight candidate through replay governance.

    Accepting here only marks the candidate as accepted.  It does not mutate
    durable strategy weights; a later strategy module must consume accepted
    candidates with its own versioned migration.
    """

    decision = str(decision or "").strip()
    if decision not in {"accepted", "rejected"}:
        raise ValueError("weight candidate decision must be accepted or rejected")
    current = store.get_learning_candidate(candidate_id)
    if current.get("candidate_type") != "weight":
        raise ValueError("candidate_id must reference a weight learning candidate")
    replay = replay_weight_candidate(
        store,
        candidate_id,
        window=window,
        min_support=min_support,
    )
    if current.get("status") == decision:
        strategy_candidate = (
            _strategy_candidate_from_weight(store, current, replay)
            if decision == "accepted" and replay.get("status") == "passed"
            else {"status": "skipped", "reason": "not_accepted", "strategy_candidate_id": None}
        )
        return {
            "status": decision,
            "already_decided": True,
            "candidate": current,
            "replay": replay,
            "strategy_candidate": strategy_candidate,
            "strategy_candidate_id": strategy_candidate.get("strategy_candidate_id"),
            "guardrail": "candidate already decided; no durable weights changed",
        }
    if decision == "accepted" and not replay.get("can_accept"):
        return {
            "status": "blocked",
            "reason": "replay_not_passed",
            "candidate": current,
            "replay": replay,
            "guardrail": "candidate not changed; no durable weights changed",
        }
    decided = store.decide_learning_candidate(
        candidate_id,
        status=decision,
        reason=reason or (
            "weight replay passed; accepted as governed candidate"
            if decision == "accepted"
            else "rejected by reviewer"
        ),
    )
    strategy_candidate = (
        _strategy_candidate_from_weight(store, decided, replay)
        if decision == "accepted"
        else {"status": "skipped", "reason": "rejected", "strategy_candidate_id": None}
    )
    return {
        "status": decision,
        "candidate": decided,
        "replay": replay,
        "strategy_candidate": strategy_candidate,
        "strategy_candidate_id": strategy_candidate.get("strategy_candidate_id"),
        "guardrail": "weight accepted after replay; durable weights await separate strategy review",
    }
