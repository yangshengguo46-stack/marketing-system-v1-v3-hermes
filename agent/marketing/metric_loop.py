"""Hermes-native metric receipt and learning loop.

Cron decides when this runner is called.  Platform Providers observe facts.
Publishing owns checkpoint state, OperatingLoop owns receipts/candidates, and
the intelligence modules interpret observations.  This orchestrator owns none
of those truths and deliberately stops at a pending candidate.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from agent.marketing.data_paths import MarketingDataPaths
from agent.marketing.domains.account_strategy import AccountStrategyRepository
from agent.marketing.domains.publishing import PublishingRepository
from agent.marketing.intelligence.content_retro import reconcile, retro_to_dict
from agent.marketing.intelligence.influence_score import build_influence_score
from agent.marketing.intelligence.learning_governance import (
    propose_publish_recovery_skill_candidate,
    propose_weight_candidate_from_recent_retros,
)
from agent.marketing.intelligence.metric_labels import build_metric_labels
from agent.marketing.intelligence.store import OperatingLoopRepository
from agent.marketing.providers.metrics import get_metric_provider


METRIC_LOOP_VERSION = "metric-receipt-loop-v0.1"
_METRIC_KEY = re.compile(r"^[a-z][a-z0-9_]{0,79}$")
_SENSITIVE_KEY = re.compile(
    r"(?:api[_-]?key|authorization|cookie|password|secret|token)", re.IGNORECASE
)
_SENSITIVE_TEXT = re.compile(
    r"(?i)(api[_-]?key|authorization|cookie|password|secret|token)\s*[:=]\s*[^\s,;]+"
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if value == value and value not in {float("inf"), float("-inf")} else None
    if isinstance(value, str):
        text = value.strip().replace(",", "")
        if not text:
            return None
        try:
            parsed = float(text)
        except ValueError:
            return None
        if parsed != parsed or parsed in {float("inf"), float("-inf")}:
            return None
        return int(parsed) if parsed.is_integer() else parsed
    return None


def normalize_observed_metrics(value: Any) -> dict[str, int | float]:
    """Accept only finite scalar observations and reject secret-shaped keys."""

    if not isinstance(value, dict) or not value:
        raise ValueError("observed metrics must be a non-empty object")
    if len(value) > 100:
        raise ValueError("observed metrics exceed the bounded contract")
    result: dict[str, int | float] = {}
    for raw_key, raw_value in value.items():
        key = str(raw_key or "").strip().lower()
        if not _METRIC_KEY.fullmatch(key) or _SENSITIVE_KEY.search(key):
            raise ValueError(f"invalid metric key: {key or '<empty>'}")
        number = _number(raw_value)
        if number is None:
            raise ValueError(f"metric {key} must be a finite number")
        result[key] = number
    return result


def _safe_reason(value: Any) -> str:
    text = " ".join(str(value or "").split())
    return _SENSITIVE_TEXT.sub(lambda match: f"{match.group(1)}=[REDACTED]", text)[:500]


def _legacy_prediction(action: dict[str, Any]) -> dict[str, Any]:
    raw = (action.get("request") or {}).get("prediction")
    if not isinstance(raw, dict):
        return {}
    result = {
        str(key): value
        for key, value in raw.items()
        if str(key).startswith("expected_") and isinstance(value, dict)
    }
    dimensions_root = raw.get("prediction_dimensions") or raw
    dimensions = (
        dimensions_root.get("dimensions") if isinstance(dimensions_root, dict) else None
    )
    if isinstance(dimensions, dict):
        for item in dimensions.values():
            if not isinstance(item, dict):
                continue
            metric = str(item.get("expected_metric") or "").strip()
            range_value = item.get("range")
            if metric and isinstance(range_value, dict):
                result.setdefault(f"expected_{metric}", range_value)
    # An all-zero traffic range means "not calibrated", not a prediction.
    return {
        key: value
        for key, value in result.items()
        if any(_number(value.get(bound)) not in {None, 0} for bound in ("low", "mid", "high"))
    }


class MetricLoopRunner:
    """Collect due checkpoints and recover interpretation after a crash."""

    def __init__(self, paths: MarketingDataPaths | None = None):
        self.paths = paths or MarketingDataPaths.from_env()
        self.publishing = PublishingRepository(self.paths)
        self.loop = OperatingLoopRepository(self.paths)
        self.strategy = AccountStrategyRepository(self.paths)

    def run_due(
        self,
        *,
        as_of: str | None = None,
        limit: int = 100,
        retry_delay: timedelta = timedelta(minutes=15),
    ) -> dict[str, Any]:
        now = datetime.fromisoformat(as_of) if as_of else _now()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        stale_before = now - timedelta(minutes=30)
        recovered = self.publishing.recover_stale_metric_claims(
            stale_before=_iso(stale_before), retry_at=_iso(now)
        )
        reconciliation = self._reconcile_observed(limit=limit)
        due = self.publishing.list_due_metric_checkpoints(
            as_of=_iso(now), limit=limit
        )
        collected: list[str] = []
        deferred: list[str] = []
        unavailable: list[str] = []

        for pending in due:
            checkpoint = self.publishing.claim_metric_checkpoint(
                pending["id"], as_of=_iso(now)
            )
            if checkpoint is None:
                continue
            action = self.publishing.get_action(checkpoint["publish_action_id"])
            try:
                provider = get_metric_provider(action["provider"])
                result = provider.collect_metrics(action, checkpoint)
                state = str((result or {}).get("state") or "").strip().lower()
                if state == "observed":
                    metrics = normalize_observed_metrics(result.get("metrics"))
                    verification = str(result.get("verification_source") or "").strip()
                    if not verification:
                        raise ValueError("observed metrics require verification_source")
                    receipt = self.loop.create_receipt(
                        source_kind=f"metric:{action['platform']}:{action['provider']}",
                        source_id=checkpoint["id"],
                        receipt_type="metric_checkpoint_observed",
                        user_id=action["user_id"],
                        account_id=action["account_id"],
                        platform=action["platform"],
                        plan_id=action["plan_id"],
                        preflight_id=action["preflight_id"],
                        session_id=action["session_id"],
                        summary={
                            "checkpoint_id": checkpoint["id"],
                            "checkpoint_label": checkpoint["label"],
                            "metrics": metrics,
                            "verification_source": verification,
                            "observed_at": str(result.get("observed_at") or _iso(now)),
                            "provider": action["provider"],
                            "version": METRIC_LOOP_VERSION,
                        },
                    )
                    self.publishing.mark_metric_observed(
                        checkpoint["id"], metric_receipt_id=receipt["id"]
                    )
                    collected.append(checkpoint["id"])
                elif state == "not_ready":
                    seconds = max(60, min(int(result.get("retry_after_seconds") or retry_delay.total_seconds()), 86400))
                    self.publishing.defer_metric_checkpoint(
                        checkpoint["id"],
                        retry_at=_iso(now + timedelta(seconds=seconds)),
                        error=_safe_reason(result.get("reason") or "platform_metrics_not_ready"),
                    )
                    deferred.append(checkpoint["id"])
                elif state == "unavailable":
                    reason = _safe_reason(result.get("reason") or "platform_metrics_unavailable")
                    receipt = self.loop.create_receipt(
                        source_kind=f"metric:{action['platform']}:{action['provider']}",
                        source_id=checkpoint["id"],
                        receipt_type="metric_checkpoint_unavailable",
                        user_id=action["user_id"],
                        account_id=action["account_id"],
                        platform=action["platform"],
                        plan_id=action["plan_id"],
                        preflight_id=action["preflight_id"],
                        session_id=action["session_id"],
                        summary={
                            "checkpoint_id": checkpoint["id"],
                            "checkpoint_label": checkpoint["label"],
                            "reason": reason,
                            "provider": action["provider"],
                            "version": METRIC_LOOP_VERSION,
                        },
                    )
                    self.publishing.mark_metric_unavailable(
                        checkpoint["id"], metric_receipt_id=receipt["id"]
                    )
                    unavailable.append(checkpoint["id"])
                else:
                    raise ValueError("metric provider returned an unsupported state")
            except Exception as exc:
                self.publishing.defer_metric_checkpoint(
                    checkpoint["id"],
                    retry_at=_iso(now + retry_delay),
                    error=_safe_reason(f"{type(exc).__name__}: {exc}"),
                )
                deferred.append(checkpoint["id"])

        after = self._reconcile_observed(limit=limit)
        return {
            "version": METRIC_LOOP_VERSION,
            "recovered_stale_claims": recovered,
            "due_count": len(due),
            "collected": collected,
            "deferred": deferred,
            "unavailable": unavailable,
            "reconciled": [*reconciliation, *after],
        }

    def _reconcile_observed(self, *, limit: int) -> list[dict[str, Any]]:
        reconciled: list[dict[str, Any]] = []
        for checkpoint in self.publishing.list_observed_metric_checkpoints(limit=limit):
            action = self.publishing.get_action(checkpoint["publish_action_id"])
            receipt = self.loop.get_receipt(checkpoint["metric_receipt_id"])
            metrics = normalize_observed_metrics(receipt["summary"].get("metrics"))
            labels = build_metric_labels(metrics)
            prediction = _legacy_prediction(action)
            if prediction:
                retro_value = retro_to_dict(reconcile(prediction, metrics))
                retro_value["status"] = "compared"
            else:
                retro_value = {
                    "status": "prediction_unavailable",
                    "accuracies": [],
                    "overall_bucket": None,
                    "bias_direction": "unknown",
                    "note": "没有经过校准的发布前指标区间；只沉淀真实标签，不伪造预测偏差。",
                }
            preflight = self.loop.get_preflight(action["preflight_id"])
            calibration = self.strategy.get_active_influence_calibration(
                user_id=action["user_id"], account_id=action["account_id"]
            )
            influence = build_influence_score(
                {
                    "preflight_scores": preflight["scores"],
                    "metric_labels": labels,
                    "weights": calibration.get("weights") if calibration else None,
                }
            )
            receipt_refs = list(
                dict.fromkeys(
                    [ref for ref in (action.get("receipt_id"), receipt["id"]) if ref]
                )
            )
            candidate = self.loop.create_learning_candidate(
                source_key=f"metric-retro:{checkpoint['id']}",
                candidate_type="memory",
                user_id=action["user_id"],
                account_id=action["account_id"],
                platform=action["platform"],
                preflight_id=action["preflight_id"],
                prediction_id=action["preflight_id"] if prediction else None,
                receipt_refs=receipt_refs,
                evidence_refs=[
                    f"publish_action:{action['id']}",
                    f"metric_checkpoint:{checkpoint['id']}",
                ],
                proposal={
                    "kind": "published_metric_retro",
                    "version": METRIC_LOOP_VERSION,
                    "checkpoint_id": checkpoint["id"],
                    "checkpoint_label": checkpoint["label"],
                    "content_kind": (action.get("request") or {}).get("content_kind") or "",
                    "metric_labels": labels,
                    "retro": retro_value,
                    "influence_score": influence,
                    "guardrail": "pending candidate only; acceptance and account knowledge projection require governance",
                },
                confidence=min(0.82, 0.45 + labels["confidence"] * 0.35),
            )
            weight = propose_weight_candidate_from_recent_retros(
                self.loop,
                user_id=action["user_id"],
                account_id=action["account_id"],
                platform=action["platform"],
            )
            recovery_skill = propose_publish_recovery_skill_candidate(
                self.publishing,
                self.loop,
                user_id=action["user_id"],
                account_id=action["account_id"],
                platform=action["platform"],
                provider=action["provider"],
                content_kind=str((action.get("request") or {}).get("content_kind") or "") or None,
            )
            self.publishing.mark_metric_reconciled(checkpoint["id"])
            reconciled.append(
                {
                    "checkpoint_id": checkpoint["id"],
                    "candidate_id": candidate["id"],
                    "weight_candidate_id": weight.get("weight_candidate_id"),
                    "skill_candidate_id": recovery_skill.get("skill_candidate_id"),
                    "skill_candidate_status": recovery_skill.get("status"),
                }
            )
        return reconciled


def run_due_metric_checkpoints(
    *,
    paths: MarketingDataPaths | None = None,
    as_of: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """Callable entrypoint for the native Hermes Cron owner."""

    return MetricLoopRunner(paths).run_due(as_of=as_of, limit=limit)
