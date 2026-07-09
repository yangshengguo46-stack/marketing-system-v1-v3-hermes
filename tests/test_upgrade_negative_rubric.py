"""Tests for UPGRADE-01: Negative signal dimensions in content rubric.

Tests the 9-dimension rubric (7 positive + 2 negative) and verifies:
- Weights sum to 1.0
- Negative dimensions subtract from total
- Risk flags and risk_adjusted_total are computed correctly
- Existing rubric functions still work with new dimensions
"""

import pytest
from engine.agent_core.content_rubric import (
    RubricDimension,
    OPINION_VIDEO_RUBRIC,
    get_rubric,
    validate_scores,
    compute_weighted_total,
    score_content,
    rubric_to_dict,
)


class TestRubricStructure:
    def test_nine_dimensions(self):
        assert len(OPINION_VIDEO_RUBRIC) == 9

    def test_weights_sum_to_one(self):
        total = sum(d.weight for d in OPINION_VIDEO_RUBRIC)
        assert abs(total - 1.0) < 1e-6

    def test_positive_weights_sum(self):
        pos = sum(d.weight for d in OPINION_VIDEO_RUBRIC if not d.is_negative)
        assert abs(pos - 0.90) < 1e-6

    def test_negative_weights_sum(self):
        neg = sum(d.weight for d in OPINION_VIDEO_RUBRIC if d.is_negative)
        assert abs(neg - 0.10) < 1e-6

    def test_negative_dimensions_exist(self):
        keys = {d.key for d in OPINION_VIDEO_RUBRIC}
        assert "title_bait_risk" in keys
        assert "controversy_overload_risk" in keys

    def test_negative_dims_marked(self):
        for d in OPINION_VIDEO_RUBRIC:
            if d.key in ("title_bait_risk", "controversy_overload_risk"):
                assert d.is_negative is True
            else:
                assert d.is_negative is False

    def test_rubric_to_dict_includes_is_negative(self):
        dicts = rubric_to_dict("opinion_video")
        assert all("is_negative" in d for d in dicts)
        neg = [d for d in dicts if d["is_negative"]]
        assert len(neg) == 2


class TestScoringWithNegative:
    def _perfect_positive_scores(self):
        return {
            "hook": 9, "topic": 8, "emotion": 8, "density": 8,
            "pacing": 7, "viewpoint": 8, "cta": 7,
            "title_bait_risk": 0, "controversy_overload_risk": 0,
        }

    def test_zero_negative_gives_higher_score(self):
        scores_no_risk = self._perfect_positive_scores()
        scores_with_risk = {**scores_no_risk, "title_bait_risk": 8, "controversy_overload_risk": 8}
        total_no = compute_weighted_total(scores_no_risk)
        total_with = compute_weighted_total(scores_with_risk)
        assert total_no > total_with
        # Difference should be roughly 0.8 * 2 * 0.05 * 10 = 0.8
        assert total_no - total_with >= 0.7

    def test_negative_subtracts_from_total(self):
        scores = self._perfect_positive_scores()
        base = compute_weighted_total(scores)
        scores_risk = {**scores, "title_bait_risk": 10}
        risk = compute_weighted_total(scores_risk)
        # title_bait_risk weight=0.05, score=10 → subtract 0.05*1.0*10 = 0.5
        assert abs((base - risk) - 0.5) < 0.01

    def test_floor_at_zero(self):
        scores = {
            "hook": 0, "topic": 0, "emotion": 0, "density": 0,
            "pacing": 0, "viewpoint": 0, "cta": 0,
            "title_bait_risk": 10, "controversy_overload_risk": 10,
        }
        assert compute_weighted_total(scores) == 0.0

    def test_validate_scores_requires_negative_dims(self):
        scores = {"hook": 8, "topic": 7, "emotion": 7, "density": 7,
                  "pacing": 6, "viewpoint": 7, "cta": 6}
        with pytest.raises(ValueError, match="missing dimension scores"):
            validate_scores(scores)

    def test_validate_scores_rejects_extra_keys(self):
        scores = self._perfect_positive_scores()
        scores["extra_dim"] = 5
        with pytest.raises(ValueError, match="unknown dimension"):
            validate_scores(scores)


class TestRiskFlags:
    def test_no_risk_flags_when_negative_low(self):
        scores = self._perfect_positive_scores()
        cs = score_content(scores)
        assert cs.risk_flags == []
        assert cs.risk_adjusted_total is None

    def test_risk_flag_when_title_bait_high(self):
        scores = {**self._perfect_positive_scores(), "title_bait_risk": 8}
        cs = score_content(scores)
        assert "title_bait_risk" in cs.risk_flags
        assert cs.risk_adjusted_total is not None
        assert cs.risk_adjusted_total < cs.weighted_total

    def test_risk_flag_when_controversy_high(self):
        scores = {**self._perfect_positive_scores(), "controversy_overload_risk": 9}
        cs = score_content(scores)
        assert "controversy_overload_risk" in cs.risk_flags

    def test_both_risk_flags(self):
        scores = {**self._perfect_positive_scores(), "title_bait_risk": 7, "controversy_overload_risk": 8}
        cs = score_content(scores)
        assert len(cs.risk_flags) == 2

    def test_no_risk_flag_at_threshold_minus_one(self):
        scores = {**self._perfect_positive_scores(), "title_bait_risk": 6}
        cs = score_content(scores)
        assert cs.risk_flags == []

    def _perfect_positive_scores(self):
        return {
            "hook": 9, "topic": 8, "emotion": 8, "density": 8,
            "pacing": 7, "viewpoint": 8, "cta": 7,
            "title_bait_risk": 0, "controversy_overload_risk": 0,
        }
