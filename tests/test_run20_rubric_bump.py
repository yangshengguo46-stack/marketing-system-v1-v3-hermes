"""RUN-20: Rubric evolution protocol tests.

Tests the full bump lifecycle:
  propose → validate → re-score → consistency check → audit → accept/reject

Key principles:
  - Weights must sum to 1.0
  - Minimum 5 samples required
  - New ranking must match actual ranking on >= 4/5 samples
  - Cross-model audit can veto
"""

import pytest
from engine.agent_core.content_bump import (
    BumpProposal,
    BumpResult,
    CONSISTENCY_THRESHOLD,
    MIN_SAMPLES_FOR_BUMP,
    apply_new_weights,
    attempt_bump,
    check_consistency,
    re_score_with_new_weights,
    validate_new_weights,
)
from engine.agent_core.content_rubric import OPINION_VIDEO_RUBRIC, get_rubric


# ── Weight validation tests ───────────────────────────────────────────


class TestValidateWeights:
    def test_valid_weights(self):
        weights = {d.key: d.weight for d in OPINION_VIDEO_RUBRIC}
        validate_new_weights("opinion_video", weights)

    def test_weights_dont_sum_to_one(self):
        weights = {d.key: 0.1 for d in OPINION_VIDEO_RUBRIC}
        with pytest.raises(ValueError, match="must sum to 1.0"):
            validate_new_weights("opinion_video", weights)

    def test_missing_key(self):
        weights = {d.key: d.weight for d in OPINION_VIDEO_RUBRIC if d.key != "hook"}
        weights["topic"] *= 2  # compensate
        with pytest.raises(ValueError, match="missing weight"):
            validate_new_weights("opinion_video", weights)

    def test_negative_weight(self):
        weights = {d.key: d.weight for d in OPINION_VIDEO_RUBRIC}
        weights["hook"] = -0.1
        weights["topic"] = 0.3
        with pytest.raises(ValueError, match="must be non-negative"):
            validate_new_weights("opinion_video", weights)

    def test_extra_key(self):
        weights = {d.key: d.weight for d in OPINION_VIDEO_RUBRIC}
        weights["extra"] = 0.1
        with pytest.raises(ValueError, match="unknown weight"):
            validate_new_weights("opinion_video", weights)


# ── Re-score tests ────────────────────────────────────────────────────


class TestReScore:
    def test_same_weights_same_result(self):
        scores = {d.key: 7 for d in OPINION_VIDEO_RUBRIC}
        old_weights = {d.key: d.weight for d in OPINION_VIDEO_RUBRIC}
        new_total = re_score_with_new_weights(scores, old_weights)
        # Positive: 0.7*0.90*10 = 6.3; negative: -0.7*0.10*10 = -0.7
        assert new_total == 5.6

    def test_different_weights_different_result(self):
        scores = {d.key: 7 for d in OPINION_VIDEO_RUBRIC}
        # Shift weight from cta to hook (keep sum=1.0)
        new_weights = {d.key: d.weight for d in OPINION_VIDEO_RUBRIC}
        new_weights["hook"] = 0.28
        new_weights["cta"] = 0.01
        new_total = re_score_with_new_weights(scores, new_weights)
        # All scores equal so total should still be 5.6 (same fraction of weights)
        assert new_total == 5.6

    def test_weight_shift_affects_unequal_scores(self):
        scores = {d.key: 5 for d in OPINION_VIDEO_RUBRIC}
        scores["hook"] = 10
        scores["cta"] = 0
        # Default weights: hook=0.18, cta=0.11
        old_weights = {d.key: d.weight for d in OPINION_VIDEO_RUBRIC}
        old_total = re_score_with_new_weights(scores, old_weights)

        # Shift more weight to hook (keep sum=1.0)
        new_weights = dict(old_weights)
        new_weights["hook"] = 0.28
        new_weights["cta"] = 0.01
        new_total = re_score_with_new_weights(scores, new_weights)

        assert new_total > old_total  # more weight on high-scoring dimension


# ── Consistency check tests ───────────────────────────────────────────


class TestConsistency:
    def test_perfect_match(self):
        ranking = ["a", "b", "c", "d", "e"]
        assert check_consistency(ranking, ranking, ranking)[0] is True

    def test_one_position_off(self):
        """1 position difference is allowed."""
        old = ["a", "b", "c", "d", "e"]
        new = ["b", "a", "c", "d", "e"]  # a and b swapped
        actual = ["a", "b", "c", "d", "e"]
        passed, ratio = check_consistency(old, new, actual)
        assert passed is True
        assert ratio >= 0.8

    def test_completely_wrong(self):
        old = ["a", "b", "c", "d", "e"]
        new = ["e", "d", "c", "b", "a"]  # reversed
        actual = ["a", "b", "c", "d", "e"]
        passed, ratio = check_consistency(old, new, actual)
        assert passed is False

    def test_empty_actual(self):
        passed, ratio = check_consistency([], [], [])
        assert passed is False
        assert ratio == 0.0


# ── Bump attempt tests ────────────────────────────────────────────────


def make_calibration_pool(n: int = 5):
    """Create a calibration pool with n samples."""
    pool = []
    for i in range(n):
        scores = {d.key: max(0, 8 - i) for d in OPINION_VIDEO_RUBRIC}
        total = sum(scores[d.key] * d.weight for d in OPINION_VIDEO_RUBRIC) * 10 / 10
        pool.append({
            "asset_id": f"asset_{i}",
            "scores": scores,
            "weighted_total": round(total, 2),
        })
    return pool


class TestAttemptBump:
    def test_rejected_insufficient_samples(self):
        pool = make_calibration_pool(3)  # < MIN_SAMPLES_FOR_BUMP
        proposal = BumpProposal(
            rubric_type="opinion_video",
            old_weights={d.key: d.weight for d in OPINION_VIDEO_RUBRIC},
            new_weights={d.key: d.weight for d in OPINION_VIDEO_RUBRIC},
        )
        result = attempt_bump(proposal, pool, actual_ranking=["asset_0", "asset_1", "asset_2"])
        assert result.accepted is False
        assert "insufficient samples" in result.rejection_reason

    def test_rejected_invalid_weights(self):
        pool = make_calibration_pool(5)
        proposal = BumpProposal(
            rubric_type="opinion_video",
            old_weights={d.key: d.weight for d in OPINION_VIDEO_RUBRIC},
            new_weights={d.key: 0.05 for d in OPINION_VIDEO_RUBRIC},  # sum != 1.0
        )
        result = attempt_bump(proposal, pool, actual_ranking=["asset_0", "asset_1", "asset_2", "asset_3", "asset_4"])
        assert result.accepted is False
        assert "invalid weights" in result.rejection_reason

    def test_accepted_with_same_weights(self):
        """Same weights should produce same ranking → consistent → accepted."""
        pool = make_calibration_pool(5)
        weights = {d.key: d.weight for d in OPINION_VIDEO_RUBRIC}
        proposal = BumpProposal(
            rubric_type="opinion_video",
            old_weights=weights,
            new_weights=weights,
        )
        actual = ["asset_0", "asset_1", "asset_2", "asset_3", "asset_4"]
        result = attempt_bump(proposal, pool, actual_ranking=actual)
        assert result.accepted is True
        assert result.consistency_passed is True
        assert len(result.re_scored) == 5

    def test_rejected_audit_veto(self):
        pool = make_calibration_pool(5)
        weights = {d.key: d.weight for d in OPINION_VIDEO_RUBRIC}
        proposal = BumpProposal(
            rubric_type="opinion_video",
            old_weights=weights,
            new_weights=weights,
        )
        actual = ["asset_0", "asset_1", "asset_2", "asset_3", "asset_4"]
        result = attempt_bump(proposal, pool, actual_ranking=actual, audit_result=False)
        assert result.accepted is False
        assert "audit rejected" in result.rejection_reason
        assert result.audit_passed is False

    def test_accepted_with_audit_pass(self):
        pool = make_calibration_pool(5)
        weights = {d.key: d.weight for d in OPINION_VIDEO_RUBRIC}
        proposal = BumpProposal(
            rubric_type="opinion_video",
            old_weights=weights,
            new_weights=weights,
        )
        actual = ["asset_0", "asset_1", "asset_2", "asset_3", "asset_4"]
        result = attempt_bump(proposal, pool, actual_ranking=actual, audit_result=True)
        assert result.accepted is True
        assert result.audit_passed is True

    def test_re_scored_contains_both_totals(self):
        pool = make_calibration_pool(5)
        weights = {d.key: d.weight for d in OPINION_VIDEO_RUBRIC}
        proposal = BumpProposal(
            rubric_type="opinion_video",
            old_weights=weights,
            new_weights=weights,
        )
        actual = ["asset_0", "asset_1", "asset_2", "asset_3", "asset_4"]
        result = attempt_bump(proposal, pool, actual_ranking=actual)
        for item in result.re_scored:
            assert "old_total" in item
            assert "new_total" in item
            assert "asset_id" in item


# ── Apply new weights tests ───────────────────────────────────────────


class TestApplyNewWeights:
    def test_returns_new_rubric(self):
        old_weights = {d.key: d.weight for d in OPINION_VIDEO_RUBRIC}
        new_weights = dict(old_weights)
        new_weights["hook"] = 0.23
        new_weights["topic"] = 0.08  # compensate
        new_rubric = apply_new_weights("opinion_video", new_weights)
        assert len(new_rubric) == 9
        # Check weights changed
        old_hook = next(d for d in OPINION_VIDEO_RUBRIC if d.key == "hook")
        new_hook = next(d for d in new_rubric if d.key == "hook")
        assert new_hook.weight == 0.23
        assert old_hook.weight == 0.18  # original unchanged

    def test_original_rubric_unchanged(self):
        original = get_rubric("opinion_video")
        original_weights = {d.key: d.weight for d in original}
        new_weights = dict(original_weights)
        new_weights["hook"] = 0.28
        new_weights["cta"] = 0.01
        apply_new_weights("opinion_video", new_weights)
        # Original should be unchanged
        after = get_rubric("opinion_video")
        after_weights = {d.key: d.weight for d in after}
        assert after_weights == original_weights

    def test_invalid_weights_raise(self):
        weights = {d.key: 0.05 for d in OPINION_VIDEO_RUBRIC}
        with pytest.raises(ValueError):
            apply_new_weights("opinion_video", weights)
