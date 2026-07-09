"""Product-owned orchestration for the marketing learning flywheel.

The individual scoring, prediction and retrospective modules are deliberately
pure.  This layer connects them to durable content assets and memory candidates
without allowing an LLM to silently change strategy weights.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, TYPE_CHECKING

from .content_retro import reconcile, retro_to_dict
from .influence_score import build_asset_influence_score
from .learning_governance import propose_weight_candidate_from_recent_retros
from .memory_classification import SOURCE_PUBLISHED_RESULT, classify_memory
from .models import MemoryKind

if TYPE_CHECKING:
    from .store import AgentCoreStore


METRIC_LABEL_VERSION = "metric-labels-v0.1"


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip().replace(",", "")
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


def _first_number(metrics: dict[str, Any], keys: tuple[str, ...]) -> tuple[str, float] | None:
    for key in keys:
        if key in metrics:
            value = _number(metrics.get(key))
            if value is not None:
                return key, value
    return None


def _bucket(value: float, *, low: float, mid: float, high: float) -> str:
    if value <= 0:
        return "zero"
    if value < low:
        return "low"
    if value < mid:
        return "mid"
    if value < high:
        return "high"
    return "spike"


def _rate_bucket(value: float) -> str:
    return _bucket(value, low=0.02, mid=0.08, high=0.18)


def build_metric_labels(metrics: dict[str, Any]) -> dict[str, Any]:
    """Translate raw platform metrics into comparable learning labels.

    This function deliberately omits missing dimensions instead of inventing
    zeros.  Unknown metrics should have been rejected before persistence; here
    we only classify observable facts.
    """
    if not isinstance(metrics, dict):
        metrics = {}

    labels: dict[str, Any] = {}

    attention = _first_number(metrics, ("views", "play_count", "impressions", "reach"))
    if attention:
        key, value = attention
        labels["attention"] = {
            "source_metric": key,
            "value": value,
            "bucket": _bucket(value, low=100, mid=1000, high=10000),
            "meaning": "用户是否停下/平台是否给到基础曝光",
        }

    retention = _first_number(metrics, ("completion_rate", "avg_completion_rate", "watch_completion_rate"))
    if retention:
        key, value = retention
        labels["retention"] = {
            "source_metric": key,
            "value": value,
            "bucket": _rate_bucket(value),
            "meaning": "内容中段和结构是否撑得住",
        }

    trust = _first_number(metrics, ("engagement_rate", "save_rate", "collect_rate", "share_rate"))
    if trust:
        key, value = trust
        labels["trust"] = {
            "source_metric": key,
            "value": value,
            "bucket": _rate_bucket(value),
            "meaning": "内容是否带来信任、收藏、互动或传播",
        }
    elif any(key in metrics for key in ("likes", "comments", "shares", "collects", "saves")):
        weighted = (
            (_number(metrics.get("likes")) or 0.0)
            + 2.0 * (_number(metrics.get("comments")) or 0.0)
            + 3.0 * (_number(metrics.get("shares")) or 0.0)
            + 3.0 * ((_number(metrics.get("collects")) or 0.0) + (_number(metrics.get("saves")) or 0.0))
        )
        labels["trust"] = {
            "source_metric": "weighted_interactions",
            "value": weighted,
            "bucket": _bucket(weighted, low=10, mid=100, high=1000),
            "meaning": "无互动率时用加权互动量近似信任/传播",
        }

    action = _first_number(metrics, ("new_followers", "follows", "profile_visits", "leads", "clicks", "conversions"))
    if action:
        key, value = action
        labels["action"] = {
            "source_metric": key,
            "value": value,
            "bucket": _bucket(value, low=1, mid=10, high=100),
            "meaning": "用户是否进一步行动",
        }

    fit = _first_number(metrics, ("target_audience_match", "target_comment_ratio", "follower_conversion_rate"))
    if fit:
        key, value = fit
        labels["fit"] = {
            "source_metric": key,
            "value": value,
            "bucket": _rate_bucket(value),
            "meaning": "吸引来的是否是目标受众",
        }

    risk = _first_number(metrics, ("negative_feedback", "not_interested", "reports", "unfollows", "complaints"))
    if risk:
        key, value = risk
        labels["risk"] = {
            "source_metric": key,
            "value": value,
            "bucket": _bucket(value, low=1, mid=5, high=20),
            "meaning": "负反馈/伤账号风险",
        }

    return {
        "version": METRIC_LABEL_VERSION,
        "labels": labels,
        "available_metrics": sorted(str(key) for key in metrics.keys()),
        "missing_dimensions": [
            item for item in ("attention", "retention", "trust", "action", "fit", "risk")
            if item not in labels
        ],
        "confidence": round(min(1.0, 0.18 * len(labels)), 3),
    }


def review_content_asset(
    store: "AgentCoreStore",
    *,
    asset_id: str,
    scores: dict[str, int],
    prediction: dict[str, Any] | None = None,
    task_id: str | None = None,
    notes: str = "",
) -> dict[str, Any]:
    """Persist a rubric score and optional immutable pre-publish prediction."""
    asset = store.get_content_asset(asset_id)
    score = store.record_content_score(
        asset_id=asset_id,
        scores=scores,
        task_id=task_id,
        notes=notes,
        metadata={
            "asset_version": asset["version"],
            "platform": asset.get("platform"),
            "account_id": asset.get("account_id"),
        },
    )
    prediction_record = None
    if prediction:
        # The product workflow allows one blind prediction per immutable asset
        # version. Preserve it even if a caller retries without a task id.
        prediction_record = store.get_prediction_by_asset(asset_id, task_id)
        if prediction_record is None:
            prediction_record = store.create_prediction(
                asset_id=asset_id, prediction=prediction, task_id=task_id,
            )
    return {
        "asset_id": asset_id,
        "asset_version": asset["version"],
        "score": score,
        "prediction": prediction_record,
        "ready_for_publish_review": score.get("weighted_total", 0) >= 6.0
        and not score.get("risk_flags"),
    }


def reconcile_published_metrics(
    store: "AgentCoreStore",
    publishing_task_id: str,
    metrics: dict[str, Any] | None = None,
    *,
    snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Reconcile actual metrics and create governed learning candidates.

    The blind prediction is settled exactly once.  Raw metrics become
    comparable labels, and the interpretation is stored as a pending
    ``learning_candidate`` instead of silently mutating durable strategy.
    """
    publishing = store.get_publishing_task(publishing_task_id)
    asset = store.get_content_asset(publishing["asset_id"])
    if snapshot is not None:
        metrics = snapshot.get("metrics") or {}
    metrics = dict(metrics or {})
    metric_labels = build_metric_labels(metrics)
    experiment_id = asset.get("experiment_id")
    if experiment_id:
        with store._connect() as db:
            db.execute(
                """UPDATE account_experiments SET status='review_due',updated_at=?
                WHERE id=? AND user_id=? AND account_id=? AND status='running'""",
                (datetime.now(timezone.utc).isoformat(), experiment_id,
                 asset.get("user_id") or "default", asset.get("account_id")),
            )
    prediction = store.get_prediction_by_asset(asset["id"])
    if prediction is None:
        result = {
            "status": "metrics_recorded", "prediction": "missing",
            "memory_candidate_id": None,
            "learning_candidate_id": None,
            "metric_labels": metric_labels,
        }
        if experiment_id:
            result["experiment_id"] = experiment_id
        return result
    if prediction.get("status") == "retro_completed":
        return {
            "status": "already_reconciled",
            "prediction_id": prediction["id"],
            "retro": prediction.get("retro"),
            "metric_labels": metric_labels,
            "memory_candidate_id": None,
            "learning_candidate_id": None,
        }

    retro = reconcile(prediction["prediction"], metrics)
    retro.prediction_id = prediction["id"]
    retro.asset_id = asset["id"]
    retro_data = retro_to_dict(retro)
    retro_data["metric_labels"] = metric_labels
    influence_score = build_asset_influence_score(store, asset["id"], metric_labels=metric_labels)
    retro_data["influence_score"] = influence_score
    if snapshot is not None:
        retro_data["metric_snapshot_id"] = snapshot.get("id")
    store.record_retro(prediction["id"], retro_data)

    summary = (
        f"内容《{asset['title']}》发布结果复盘：预测偏差={retro.bias_direction}；"
        f"实际指标={json.dumps(metrics, ensure_ascii=False, sort_keys=True)}"
    )
    evidence = [{
        "source": "published_result",
        "publishing_task_id": publishing_task_id,
        "prediction_id": prediction["id"],
        "platform": publishing.get("platform"),
    }]
    classification = classify_memory(
        MemoryKind.EPISODIC.value,
        summary,
        source=SOURCE_PUBLISHED_RESULT,
        account_id=asset.get("account_id"),
        platform=asset.get("platform"),
        evidence=evidence,
    )
    candidate = store.add_memory_candidate(
        kind=MemoryKind.EPISODIC,
        user_id=asset.get("user_id") or "default",
        account_id=asset.get("account_id"),
        platform=asset.get("platform"),
        content=summary,
        evidence=evidence,
        confidence=0.55,  # result is real; interpretation still requires review
        task_id=prediction.get("task_id"),
        provenance="publish_result",
        classification=classification.to_dict(),
    )
    receipt_refs: list[str] = []
    snapshot_id = str((snapshot or {}).get("id") or "").strip()
    if snapshot_id:
        for ref in store.list_receipt_refs(
            asset_id=asset["id"], receipt_type="metric_snapshot", limit=50,
        ):
            if ref.get("source_id") == snapshot_id:
                receipt_refs.append(ref["id"])
                break
    preflight_id = None
    preflights = store.list_preflight_records(asset_id=asset["id"], limit=1)
    if preflights:
        preflight_id = preflights[0]["id"]
    learning_candidate = store.create_learning_candidate(
        candidate_type="memory",
        user_id=asset.get("user_id") or "default",
        account_id=asset.get("account_id"),
        platform=asset.get("platform"),
        asset_id=asset["id"],
        preflight_id=preflight_id,
        prediction_id=prediction["id"],
        receipt_refs=receipt_refs,
        evidence_refs=[
            item for item in (
                f"publishing_task:{publishing_task_id}",
                f"metric_snapshot:{snapshot_id}" if snapshot_id else "",
                f"prediction:{prediction['id']}",
                f"legacy_memory_candidate:{candidate['id']}",
                f"preflight:{preflight_id}" if preflight_id else "",
            )
            if item
        ],
        proposal={
            "kind": "published_metric_retro",
            "content": summary,
            "retro": retro_data,
            "metric_labels": metric_labels,
            "influence_score": influence_score,
            "guardrail": "pending candidate only; do not promote to durable memory or strategy without review",
        },
        confidence=min(0.82, 0.45 + metric_labels["confidence"] * 0.35),
    )
    weight_governance = propose_weight_candidate_from_recent_retros(
        store,
        user_id=asset.get("user_id") or "default",
        account_id=asset.get("account_id"),
        platform=asset.get("platform"),
    )
    strategy_candidate_id = None
    if experiment_id:
        with store._connect() as db:
            experiment = db.execute(
                """SELECT project_id,user_id,account_id FROM account_experiments
                WHERE id=? AND user_id=? AND account_id=?""",
                (experiment_id, asset.get("user_id") or "default", asset.get("account_id")),
            ).fetchone()
        if experiment is not None:
            from .account_lifecycle import AccountLifecycleService
            strategy_candidate = AccountLifecycleService(store).create_strategy_candidate(
                user_id=experiment["user_id"], account_id=experiment["account_id"],
                project_id=experiment["project_id"], trigger="experiment_retro",
                proposal={
                    "type": "review_experiment",
                    "experiment_id": experiment_id,
                    "bias_direction": retro.bias_direction,
                    "note": "复盘结果仅生成策略候选，需用户决定后才能改变策略",
                },
                evidence_refs=[
                    f"publishing_task:{publishing_task_id}",
                    f"prediction:{prediction['id']}",
                    f"memory_candidate:{candidate['id']}",
                ],
                confidence=0.55,
            )
            strategy_candidate_id = strategy_candidate["id"]
    result = {
        "status": "reconciled",
        "prediction_id": prediction["id"],
        "retro": retro_data,
        "memory_candidate_id": candidate["id"],
        "memory_status": candidate["status"],
        "learning_candidate_id": learning_candidate["id"],
        "learning_candidate_status": learning_candidate["status"],
        "metric_labels": metric_labels,
        "influence_score": influence_score,
        "weight_governance": weight_governance,
        "weight_candidate_id": weight_governance.get("weight_candidate_id"),
    }
    if experiment_id:
        result["experiment_id"] = experiment_id
        result["strategy_candidate_id"] = strategy_candidate_id
    return result


def get_learning_status(
    store: "AgentCoreStore", *, user_id: str, account_id: str | None = None,
) -> dict[str, Any]:
    assets = store.list_content_assets(account_id=account_id)
    asset_ids = {asset["id"] for asset in assets if asset.get("user_id", "default") == user_id}
    scores = [score for score in store.list_content_scores() if score["asset_id"] in asset_ids]
    predictions = [item for item in store.list_predictions() if item["asset_id"] in asset_ids]
    benchmarks = store.list_benchmark_accounts(user_id)
    cadence = store.get_or_create_cadence(user_id=user_id, account_id=account_id)
    cadence_status = store.get_cadence_status(user_id, account_id)
    return {
        "user_id": user_id,
        "account_id": account_id,
        "content_assets": len(asset_ids),
        "content_scores": len(scores),
        "predictions_pending": sum(item["status"] == "pending" for item in predictions),
        "retrospectives": sum(item["status"] == "retro_completed" for item in predictions),
        "benchmark_accounts": len(benchmarks),
        "cadence": {**cadence, "alert": cadence_status["alert"]},
    }
