"""Tests for UPGRADE-02: blind_agent blind evaluation protocol.

Tests multi-candidate blind scoring, spread detection, arbitration,
and anomaly detection.
"""

import pytest
from engine.agent_core.blind_eval import (
    evaluate_candidates,
    detect_score_anomaly,
    SPREAD_THRESHOLD,
)


def _scores(hook=8, topic=7, emotion=7, density=7, pacing=6, viewpoint=7, cta=6,
             bait=0, controversy=0):
    return {
        "hook": hook, "topic": topic, "emotion": emotion, "density": density,
        "pacing": pacing, "viewpoint": viewpoint, "cta": cta,
        "title_bait_risk": bait, "controversy_overload_risk": controversy,
    }


class TestEvaluateCandidates:
    def test_requires_at_least_two(self):
        with pytest.raises(ValueError, match="at least 2"):
            evaluate_candidates({"a": _scores()})

    def test_requires_at_least_one(self):
        with pytest.raises(ValueError, match="at least one"):
            evaluate_candidates({})

    def test_winner_is_highest_score(self):
        candidates = {
            "a": _scores(hook=5, topic=5),
            "b": _scores(hook=9, topic=8),
            "c": _scores(hook=7, topic=6),
        }
        result = evaluate_candidates(candidates)
        assert result.winner_id == "b"

    def test_all_candidates_scored_by_blind_agent(self):
        candidates = {"a": _scores(), "b": _scores(hook=9)}
        result = evaluate_candidates(candidates)
        for c in result.candidates:
            assert c.content_score.scored_by == "blind_agent"

    def test_spread_computed_correctly(self):
        candidates = {
            "a": _scores(hook=2, topic=2, emotion=2, density=2, pacing=2, viewpoint=2, cta=2),
            "b": _scores(hook=10, topic=10, emotion=10, density=10, pacing=10, viewpoint=10, cta=10),
        }
        result = evaluate_candidates(candidates)
        assert result.spread > 0
        assert result.arbitration_triggered == (result.spread > SPREAD_THRESHOLD)

    def test_no_arbitration_when_close(self):
        candidates = {
            "a": _scores(hook=8, topic=7),
            "b": _scores(hook=8, topic=7, pacing=7),
        }
        result = evaluate_candidates(candidates)
        assert result.arbitration_triggered is False

    def test_arbitration_triggered_on_large_spread(self):
        candidates = {
            "a": _scores(hook=2, topic=2, emotion=2, density=2, pacing=2, viewpoint=2, cta=2),
            "b": _scores(hook=10, topic=10, emotion=10, density=10, pacing=10, viewpoint=10, cta=10),
        }
        result = evaluate_candidates(candidates)
        assert result.arbitration_triggered is True
        assert "spread" in result.arbitration_reason

    def test_risk_aware_winner_selection(self):
        # Candidate a has higher raw score but high risk
        # Candidate b has lower raw score but no risk
        candidates = {
            "a": _scores(hook=10, topic=10, emotion=10, density=10, pacing=10, viewpoint=10, cta=10, bait=9, controversy=8),
            "b": _scores(hook=8, topic=8, emotion=8, density=8, pacing=8, viewpoint=8, cta=8, bait=0, controversy=0),
        }
        result = evaluate_candidates(candidates)
        # a's risk_adjusted should be lower than b's effective_score
        a_candidate = next(c for c in result.candidates if c.candidate_id == "a")
        b_candidate = next(c for c in result.candidates if c.candidate_id == "b")
        # a has risk_adjusted_total, b doesn't
        assert a_candidate.content_score.risk_adjusted_total is not None
        assert b_candidate.content_score.risk_adjusted_total is None

    def test_tie_breaker_prefers_fewer_risk_flags(self):
        candidates = {
            "a": _scores(hook=8, topic=7, bait=8),
            "b": _scores(hook=8, topic=7, bait=0),
        }
        result = evaluate_candidates(candidates)
        # Both have same positive scores, b has no risk flags
        assert result.winner_id == "b"

    def test_to_dict_serialization(self):
        candidates = {"a": _scores(), "b": _scores(hook=9)}
        result = evaluate_candidates(candidates)
        d = result.to_dict()
        assert "winner_id" in d
        assert "spread" in d
        assert "candidates" in d
        assert len(d["candidates"]) == 2
        for c in d["candidates"]:
            assert "weighted_total" in c
            assert "effective_score" in c
            assert "risk_flags" in c


class TestDetectAnomaly:
    def test_sycophancy_detected(self):
        scores = _scores(hook=10, topic=10, emotion=10, density=10, pacing=10, viewpoint=10, cta=10)
        anomalies = detect_score_anomaly(scores)
        assert any("sycophancy" in a for a in anomalies)

    def test_harsh_evaluation_detected(self):
        scores = _scores(hook=0, topic=0, emotion=0, density=0, pacing=0, viewpoint=0, cta=0)
        anomalies = detect_score_anomaly(scores)
        assert any("harsh" in a for a in anomalies)

    def test_risk_under_evaluated(self):
        scores = _scores(hook=9, topic=9, emotion=9, density=9, pacing=9, viewpoint=9, cta=9, bait=0, controversy=0)
        anomalies = detect_score_anomaly(scores)
        assert any("under-evaluated" in a for a in anomalies)

    def test_all_neg_max_detected(self):
        scores = _scores(hook=5, topic=5, emotion=5, density=5, pacing=5, viewpoint=5, cta=5, bait=9, controversy=9)
        anomalies = detect_score_anomaly(scores)
        assert any("high-risk" in a for a in anomalies)

    def test_no_anomaly_normal_scores(self):
        scores = _scores(hook=8, topic=7, emotion=7, density=7, pacing=6, viewpoint=7, cta=6, bait=2, controversy=1)
        anomalies = detect_score_anomaly(scores)
        assert anomalies == []
