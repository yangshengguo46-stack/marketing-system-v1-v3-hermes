"""RUN-19: T+3d retrospective reconciliation tests.

Tests accuracy classification, bias detection, and the full
score → predict → retro → bias pattern → bump prompt lifecycle.
"""

import pytest
from engine.agent_core.content_retro import (
    PREDICTION_METRICS,
    RetroResult,
    reconcile,
    detect_bias_pattern,
    retro_to_dict,
)
from engine.agent_core.store import AgentCoreStore


PREDICTION = {
    "expected_views": {"low": 500, "mid": 2000, "high": 10000},
    "expected_completion_rate": {"low": 0.15, "mid": 0.30, "high": 0.50},
    "expected_likes": {"low": 10, "mid": 50, "high": 200},
    "expected_comments": {"low": 2, "mid": 15, "high": 60},
    "expected_shares": {"low": 1, "mid": 10, "high": 50},
}


# ── Reconcile tests ───────────────────────────────────────────────────


class TestReconcile:
    def test_all_mid_correct(self):
        actual = {
            "views": 2000,
            "completion_rate": 0.30,
            "likes": 50,
            "comments": 15,
            "shares": 10,
        }
        result = reconcile(PREDICTION, actual)
        assert result.overall_bucket == "mid_correct"
        assert result.bias_direction == "neutral"
        assert len(result.accuracies) == 5

    def test_all_over_predicted(self):
        """Actual much lower than predicted → agent was too optimistic."""
        actual = {
            "views": 100,
            "completion_rate": 0.05,
            "likes": 2,
            "comments": 0,
            "shares": 0,
        }
        result = reconcile(PREDICTION, actual)
        assert result.bias_direction == "over"
        over_count = sum(1 for a in result.accuracies if a.direction == "over")
        assert over_count >= 3

    def test_all_under_predicted(self):
        """Actual much higher than predicted → agent was too pessimistic."""
        actual = {
            "views": 50000,
            "completion_rate": 0.80,
            "likes": 500,
            "comments": 200,
            "shares": 100,
        }
        result = reconcile(PREDICTION, actual)
        assert result.bias_direction == "under"
        under_count = sum(1 for a in result.accuracies if a.direction == "under")
        assert under_count >= 3

    def test_mixed_bias(self):
        """Some over, some under → mixed."""
        actual = {
            "views": 100,  # over
            "completion_rate": 0.80,  # under
            "likes": 50,  # mid
            "comments": 15,  # mid
            "shares": 10,  # mid
        }
        result = reconcile(PREDICTION, actual)
        assert result.bias_direction == "mixed"

    def test_missing_metric_skipped(self):
        actual = {"views": 2000}  # only one metric
        result = reconcile(PREDICTION, actual)
        assert len(result.accuracies) == 1
        assert result.accuracies[0].metric == "views"

    def test_missing_prediction_key_skipped(self):
        pred = {"expected_views": {"low": 100, "mid": 500, "high": 2000}}
        actual = {"views": 500, "likes": 100}
        result = reconcile(pred, actual)
        assert len(result.accuracies) == 1  # only views

    def test_retro_to_dict(self):
        actual = {"views": 2000, "completion_rate": 0.30, "likes": 50, "comments": 15, "shares": 10}
        result = reconcile(PREDICTION, actual)
        d = retro_to_dict(result)
        assert "accuracies" in d
        assert "overall_bucket" in d
        assert "bias_direction" in d
        assert len(d["accuracies"]) == 5

    def test_metric_accuracy_fields(self):
        actual = {"views": 2000}
        result = reconcile(PREDICTION, actual)
        acc = result.accuracies[0]
        assert acc.metric == "views"
        assert acc.predicted_low == 500
        assert acc.predicted_mid == 2000
        assert acc.predicted_high == 10000
        assert acc.actual == 2000
        assert acc.bucket in ("mid_correct", "low_correct", "high_correct", "over_predicted", "under_predicted")


# ── Bias pattern detection tests ──────────────────────────────────────


class TestBiasPattern:
    def test_no_results(self):
        result = detect_bias_pattern([])
        assert result["pattern"] == "none"
        assert result["should_prompt_bump"] is False

    def test_three_over_in_a_row(self):
        """3 consecutive over-predictions → should prompt bump."""
        retros = [
            RetroResult(prediction_id="", asset_id="", accuracies=[], overall_bucket="over_predicted", bias_direction="over"),
            RetroResult(prediction_id="", asset_id="", accuracies=[], overall_bucket="over_predicted", bias_direction="over"),
            RetroResult(prediction_id="", asset_id="", accuracies=[], overall_bucket="over_predicted", bias_direction="over"),
        ]
        result = detect_bias_pattern(retros)
        assert result["pattern"] == "over"
        assert result["consecutive_count"] == 3
        assert result["should_prompt_bump"] is True

    def test_two_over_not_enough(self):
        retros = [
            RetroResult(prediction_id="", asset_id="", accuracies=[], overall_bucket="over_predicted", bias_direction="over"),
            RetroResult(prediction_id="", asset_id="", accuracies=[], overall_bucket="over_predicted", bias_direction="over"),
        ]
        result = detect_bias_pattern(retros)
        assert result["consecutive_count"] == 2
        assert result["should_prompt_bump"] is False

    def test_three_under_in_a_row(self):
        retros = [
            RetroResult(prediction_id="", asset_id="", accuracies=[], overall_bucket="under_predicted", bias_direction="under"),
            RetroResult(prediction_id="", asset_id="", accuracies=[], overall_bucket="under_predicted", bias_direction="under"),
            RetroResult(prediction_id="", asset_id="", accuracies=[], overall_bucket="under_predicted", bias_direction="under"),
        ]
        result = detect_bias_pattern(retros)
        assert result["pattern"] == "under"
        assert result["should_prompt_bump"] is True

    def test_pattern_broken_by_neutral(self):
        """A neutral result breaks the consecutive count."""
        retros = [
            RetroResult(prediction_id="", asset_id="", accuracies=[], overall_bucket="over_predicted", bias_direction="over"),
            RetroResult(prediction_id="", asset_id="", accuracies=[], overall_bucket="mid_correct", bias_direction="neutral"),
            RetroResult(prediction_id="", asset_id="", accuracies=[], overall_bucket="over_predicted", bias_direction="over"),
            RetroResult(prediction_id="", asset_id="", accuracies=[], overall_bucket="over_predicted", bias_direction="over"),
        ]
        result = detect_bias_pattern(retros)
        assert result["consecutive_count"] == 2  # only last 2
        assert result["should_prompt_bump"] is False

    def test_custom_threshold(self):
        retros = [
            RetroResult(prediction_id="", asset_id="", accuracies=[], overall_bucket="over_predicted", bias_direction="over"),
            RetroResult(prediction_id="", asset_id="", accuracies=[], overall_bucket="over_predicted", bias_direction="over"),
        ]
        result = detect_bias_pattern(retros, threshold=2)
        assert result["should_prompt_bump"] is True


# ── Store integration: full lifecycle ─────────────────────────────────


@pytest.fixture
def store(tmp_path):
    return AgentCoreStore(tmp_path / "test_run19.db")


@pytest.fixture
def asset(store):
    return store.create_content_asset(title="test retro lifecycle", type="script")


@pytest.fixture
def task(store):
    session = store.create_or_get_session(user_id="test_user")
    return store.create_task(
        session_id=session["id"],
        user_id="test_user",
        objective="test retro objective",
    )


class TestStoreRetroLifecycle:
    def test_full_score_predict_retro_with_reconciliation(self, store, asset, task):
        from engine.agent_core.content_rubric import OPINION_VIDEO_RUBRIC

        # 1. Score
        scores = {d.key: 7 for d in OPINION_VIDEO_RUBRIC}
        store.record_content_score(
            asset_id=asset["id"], scores=scores, task_id=task["id"],
        )

        # 2. Predict
        pred = store.create_prediction(
            asset_id=asset["id"],
            prediction=PREDICTION,
            task_id=task["id"],
        )

        # 3. T+3d: collect actual data and reconcile
        actual = {
            "views": 2000,
            "completion_rate": 0.30,
            "likes": 50,
            "comments": 15,
            "shares": 10,
        }
        retro_result = reconcile(PREDICTION, actual)
        retro_dict = retro_to_dict(retro_result)

        # 4. Record retro in store
        stored = store.record_retro(pred["id"], retro_dict)
        assert stored["status"] == "retro_completed"
        assert stored["retro"]["overall_bucket"] == "mid_correct"
        assert stored["retro"]["bias_direction"] == "neutral"

        # 5. Verify prediction unchanged
        final = store.get_prediction(pred["id"])
        assert final["prediction"] == PREDICTION
        assert final["retro"]["bias_direction"] == "neutral"

    def test_bias_pattern_from_stored_retros(self, store, asset, task):
        """Create multiple predictions+retros and detect bias pattern."""
        # Create 3 assets with over-predictions
        results = []
        for i in range(3):
            a = store.create_content_asset(title=f"video {i}", type="script")
            pred = store.create_prediction(
                asset_id=a["id"],
                prediction=PREDICTION,
                task_id=task["id"],
            )
            actual = {"views": 100, "completion_rate": 0.05, "likes": 2, "comments": 0, "shares": 0}
            retro = reconcile(PREDICTION, actual)
            store.record_retro(pred["id"], retro_to_dict(retro))
            results.append(retro)

        pattern = detect_bias_pattern(results)
        assert pattern["pattern"] == "over"
        assert pattern["should_prompt_bump"] is True
