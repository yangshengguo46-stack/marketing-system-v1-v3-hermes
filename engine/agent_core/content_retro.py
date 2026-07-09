"""RUN-19: T+3d retrospective reconciliation.

Compares blind predictions (RUN-18) against actual performance data
and produces a structured accuracy report. Tracks bias direction to
trigger rubric upgrade prompts (RUN-20) when patterns emerge.

Accuracy buckets per metric:
  - low_correct:  actual <= predicted.low
  - mid_correct:  predicted.low < actual <= predicted.high
  - high_correct: actual > predicted.high
  - over_predicted: actual < predicted.low (agent was too optimistic)
  - under_predicted: actual > predicted.high (agent was too pessimistic)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from .content_rubric import get_rubric

AccuracyBucket = Literal["low_correct", "mid_correct", "high_correct", "over_predicted", "under_predicted"]

# Metrics that are compared in retro
PREDICTION_METRICS = (
    "views", "completion_rate", "engagement_rate",
    "likes", "comments", "shares",
)


@dataclass
class MetricAccuracy:
    metric: str
    predicted_low: float
    predicted_mid: float
    predicted_high: float
    actual: float
    bucket: AccuracyBucket
    direction: str  # "accurate" | "over" | "under"


@dataclass
class RetroResult:
    prediction_id: str
    asset_id: str
    accuracies: list[MetricAccuracy]
    overall_bucket: AccuracyBucket
    bias_direction: str  # "neutral" | "over" | "under" | "mixed"
    notes: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


def _classify_metric(
    actual: float,
    predicted: dict[str, float],
) -> MetricAccuracy:
    """Classify a single metric's accuracy."""
    low = predicted.get("low", 0)
    mid = predicted.get("mid", 0)
    high = predicted.get("high", 0)

    if actual < low:
        bucket: AccuracyBucket = "over_predicted"
        direction = "over"
    elif actual > high:
        bucket = "under_predicted"
        direction = "under"
    elif actual <= mid * 1.2 and actual >= mid * 0.8:
        bucket = "mid_correct"
        direction = "accurate"
    elif actual <= low:
        bucket = "low_correct"
        direction = "accurate"
    else:
        bucket = "high_correct"
        direction = "accurate"

    return MetricAccuracy(
        metric="",
        predicted_low=low,
        predicted_mid=mid,
        predicted_high=high,
        actual=actual,
        bucket=bucket,
        direction=direction,
    )


def reconcile(
    prediction: dict[str, Any],
    actual: dict[str, Any],
    *,
    metrics: tuple[str, ...] = PREDICTION_METRICS,
) -> RetroResult:
    """Compare a prediction against actual data and produce accuracy report.

    Args:
        prediction: The prediction dict (expected_* with low/mid/high ranges)
        actual: The actual performance data
        metrics: Which metrics to compare

    Returns:
        RetroResult with per-metric accuracy and overall bias direction.
    """
    accuracies: list[MetricAccuracy] = []
    over_count = 0
    under_count = 0

    for metric in metrics:
        pred_key = f"expected_{metric}"
        pred_val = prediction.get(pred_key)
        actual_val = actual.get(metric)

        if pred_val is None or actual_val is None:
            continue

        acc = _classify_metric(float(actual_val), pred_val)
        acc.metric = metric
        accuracies.append(acc)

        if acc.direction == "over":
            over_count += 1
        elif acc.direction == "under":
            under_count += 1

    # Overall bias direction
    if over_count > under_count and over_count >= 2:
        bias_direction = "over"
    elif under_count > over_count and under_count >= 2:
        bias_direction = "under"
    elif over_count == 0 and under_count == 0:
        bias_direction = "neutral"
    else:
        bias_direction = "mixed"

    # Overall bucket (worst case)
    buckets = [a.bucket for a in accuracies]
    if "over_predicted" in buckets and "under_predicted" in buckets:
        overall_bucket: AccuracyBucket = "mid_correct"  # mixed errors cancel out
    elif "over_predicted" in buckets:
        overall_bucket = "over_predicted"
    elif "under_predicted" in buckets:
        overall_bucket = "under_predicted"
    elif "mid_correct" in buckets:
        overall_bucket = "mid_correct"
    elif buckets:
        overall_bucket = buckets[0]
    else:
        overall_bucket = "mid_correct"

    return RetroResult(
        prediction_id="",
        asset_id="",
        accuracies=accuracies,
        overall_bucket=overall_bucket,
        bias_direction=bias_direction,
        raw={"prediction": prediction, "actual": actual},
    )


def detect_bias_pattern(
    retro_results: list[RetroResult],
    *,
    threshold: int = 3,
) -> dict[str, Any]:
    """Detect if there's a consistent bias pattern across multiple retros.

    Per Cheat on Content's principle: 3 same-direction misses in a row
    triggers a rubric upgrade prompt.

    Returns dict with:
      - pattern: "over" | "under" | "none"
      - consecutive_count: int
      - should_prompt_bump: bool
    """
    if not retro_results:
        return {"pattern": "none", "consecutive_count": 0, "should_prompt_bump": False}

    # Sort by created_at (assumed to be in order, most recent last)
    directions = [r.bias_direction for r in retro_results]

    # Count consecutive same-direction from the end
    consecutive = 0
    last_direction = None
    for d in reversed(directions):
        if d == last_direction and d in ("over", "under"):
            consecutive += 1
        elif d in ("over", "under"):
            consecutive = 1
            last_direction = d
        else:
            break

    should_bump = consecutive >= threshold

    return {
        "pattern": last_direction or "none",
        "consecutive_count": consecutive,
        "should_prompt_bump": should_bump,
    }


def retro_to_dict(retro: RetroResult) -> dict[str, Any]:
    """Serialize RetroResult to a dict for storage."""
    return {
        "accuracies": [
            {
                "metric": a.metric,
                "predicted_low": a.predicted_low,
                "predicted_mid": a.predicted_mid,
                "predicted_high": a.predicted_high,
                "actual": a.actual,
                "bucket": a.bucket,
                "direction": a.direction,
            }
            for a in retro.accuracies
        ],
        "overall_bucket": retro.overall_bucket,
        "bias_direction": retro.bias_direction,
        "notes": retro.notes,
    }
