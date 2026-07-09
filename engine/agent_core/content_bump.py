"""RUN-20: Rubric evolution protocol.

Implements the "bump = full re-score" principle from Cheat on Content:
  1. Propose new weights for an existing rubric
  2. Re-score all assets in the calibration pool with new weights
  3. Check consistency: new ranking must match actual performance ranking
     on >= 4/5 samples (THRESHOLD)
  4. Cross-model audit: an independent model/agent reviews the proposed bump
  5. If all checks pass, the new rubric replaces the old one

The rubric is a working bench, not a museum. Old observations get deleted,
not archived in the rubric file. Git history is the archive.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .content_rubric import (
    RubricDimension,
    get_rubric,
    compute_weighted_total,
    validate_scores,
)

# Minimum number of samples with real performance data required to attempt a bump
MIN_SAMPLES_FOR_BUMP = 5

# Consistency threshold: new ranking must match actual ranking on >= this fraction
CONSISTENCY_THRESHOLD = 4  # out of 5, i.e. 80%


@dataclass
class BumpProposal:
    """A proposed rubric weight change."""

    rubric_type: str
    old_weights: dict[str, float]
    new_weights: dict[str, float]
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class BumpResult:
    """Result of a rubric bump attempt."""

    proposal: BumpProposal
    accepted: bool
    re_scored: list[dict[str, Any]]  # per-asset new scores
    consistency_passed: bool
    consistency_ratio: float  # fraction of samples where ranking matches
    audit_passed: bool | None  # None = audit not performed
    rejection_reason: str = ""


def validate_new_weights(
    rubric_type: str,
    new_weights: dict[str, float],
) -> None:
    """Validate that proposed weights are well-formed."""
    rubric = get_rubric(rubric_type)
    expected_keys = {d.key for d in rubric}
    provided_keys = set(new_weights.keys())

    missing = expected_keys - provided_keys
    if missing:
        raise ValueError(f"missing weight keys: {missing}")

    extra = provided_keys - expected_keys
    if extra:
        raise ValueError(f"unknown weight keys: {extra}")

    for key, val in new_weights.items():
        if not isinstance(val, (int, float)) or val < 0:
            raise ValueError(f"weight for '{key}' must be non-negative, got {val}")

    total = sum(new_weights.values())
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"weights must sum to 1.0, got {total}")


def re_score_with_new_weights(
    scores: dict[str, int],
    new_weights: dict[str, float],
    rubric_type: str = "opinion_video",
) -> float:
    """Compute weighted total using new weights instead of the rubric's defaults."""
    rubric = get_rubric(rubric_type)
    validate_scores(scores, rubric_type)
    validate_new_weights(rubric_type, new_weights)

    total = 0.0
    for dim in rubric:
        normalized = scores[dim.key] / dim.scale
        contribution = normalized * new_weights[dim.key] * 10.0
        if dim.is_negative:
            total -= contribution
        else:
            total += contribution
    return round(max(total, 0.0), 2)


def check_consistency(
    old_ranking: list[str],  # asset IDs sorted by old weighted_total desc
    new_ranking: list[str],  # asset IDs sorted by new weighted_total desc
    actual_ranking: list[str],  # asset IDs sorted by actual performance desc
) -> tuple[bool, float]:
    """Check if new ranking is consistent with actual performance.

    Returns (passed, ratio) where ratio is the fraction of samples
    where the new ranking matches the actual ranking.
    """
    if not actual_ranking:
        return False, 0.0

    # Compare new ranking position vs actual ranking position
    n = len(actual_ranking)
    matches = 0
    for i, asset_id in enumerate(actual_ranking):
        if asset_id in new_ranking:
            new_pos = new_ranking.index(asset_id)
            # Allow 1 position difference as "matching"
            if abs(new_pos - i) <= 1:
                matches += 1

    ratio = matches / n if n > 0 else 0.0
    passed = matches >= CONSISTENCY_THRESHOLD or ratio >= 0.8
    return passed, ratio


def attempt_bump(
    proposal: BumpProposal,
    calibration_pool: list[dict[str, Any]],
    actual_ranking: list[str],
    *,
    audit_result: bool | None = None,
) -> BumpResult:
    """Attempt a rubric weight bump.

    Args:
        proposal: The proposed weight changes
        calibration_pool: List of dicts with 'asset_id', 'scores', and optionally 'weighted_total'
        actual_ranking: Asset IDs sorted by actual performance (best first)
        audit_result: Result of cross-model audit (None = not performed)

    Returns:
        BumpResult with accept/reject decision and details.
    """
    # 1. Validate new weights
    try:
        validate_new_weights(proposal.rubric_type, proposal.new_weights)
    except ValueError as e:
        return BumpResult(
            proposal=proposal,
            accepted=False,
            re_scored=[],
            consistency_passed=False,
            consistency_ratio=0.0,
            audit_passed=audit_result,
            rejection_reason=f"invalid weights: {e}",
        )

    # 2. Check minimum sample count
    if len(calibration_pool) < MIN_SAMPLES_FOR_BUMP:
        return BumpResult(
            proposal=proposal,
            accepted=False,
            re_scored=[],
            consistency_passed=False,
            consistency_ratio=0.0,
            audit_passed=audit_result,
            rejection_reason=f"insufficient samples: {len(calibration_pool)} < {MIN_SAMPLES_FOR_BUMP}",
        )

    # 3. Re-score all samples with new weights
    re_scored = []
    for item in calibration_pool:
        new_total = re_score_with_new_weights(
            item["scores"], proposal.new_weights, proposal.rubric_type,
        )
        re_scored.append({
            "asset_id": item["asset_id"],
            "old_total": item.get("weighted_total", 0),
            "new_total": new_total,
        })

    # 4. Build rankings
    old_ranking = [r["asset_id"] for r in sorted(re_scored, key=lambda x: x["old_total"], reverse=True)]
    new_ranking = [r["asset_id"] for r in sorted(re_scored, key=lambda x: x["new_total"], reverse=True)]

    # 5. Check consistency
    consistency_passed, consistency_ratio = check_consistency(
        old_ranking, new_ranking, actual_ranking,
    )

    if not consistency_passed:
        return BumpResult(
            proposal=proposal,
            accepted=False,
            re_scored=re_scored,
            consistency_passed=False,
            consistency_ratio=consistency_ratio,
            audit_passed=audit_result,
            rejection_reason=f"consistency check failed: {consistency_ratio:.0%} match (need >= 80%)",
        )

    # 6. Cross-model audit (if performed)
    if audit_result is not None and not audit_result:
        return BumpResult(
            proposal=proposal,
            accepted=False,
            re_scored=re_scored,
            consistency_passed=True,
            consistency_ratio=consistency_ratio,
            audit_passed=False,
            rejection_reason="cross-model audit rejected the bump",
        )

    # 7. All checks passed
    return BumpResult(
        proposal=proposal,
        accepted=True,
        re_scored=re_scored,
        consistency_passed=True,
        consistency_ratio=consistency_ratio,
        audit_passed=audit_result,
    )


def apply_new_weights(
    rubric_type: str,
    new_weights: dict[str, float],
) -> tuple[RubricDimension, ...]:
    """Create a new rubric tuple with updated weights.

    This does not mutate the original rubric — it returns a new tuple.
    The caller is responsible for persisting the new rubric.
    """
    validate_new_weights(rubric_type, new_weights)
    rubric = get_rubric(rubric_type)
    new_dims = []
    for dim in rubric:
        new_dims.append(RubricDimension(
            key=dim.key,
            label=dim.label,
            description=dim.description,
            weight=new_weights[dim.key],
            scale=dim.scale,
            is_negative=dim.is_negative,
        ))
    return tuple(new_dims)
