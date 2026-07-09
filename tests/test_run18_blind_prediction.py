"""RUN-18: Blind prediction mechanism tests.

Tests the immutable prediction lifecycle:
  create (blind) → immutable → retro (settle accounts) → idempotent retro

Key principle: predictions cannot be rewritten after seeing data.
"""

import pytest
from engine.agent_core.store import AgentCoreStore


@pytest.fixture
def store(tmp_path):
    return AgentCoreStore(tmp_path / "test_run18.db")


@pytest.fixture
def asset(store):
    return store.create_content_asset(title="test video for prediction", type="script")


@pytest.fixture
def task(store):
    session = store.create_or_get_session(user_id="test_user")
    return store.create_task(
        session_id=session["id"],
        user_id="test_user",
        objective="test prediction objective",
    )


SAMPLE_PREDICTION = {
    "expected_views": {"low": 500, "mid": 2000, "high": 10000},
    "expected_completion_rate": {"low": 0.15, "mid": 0.30, "high": 0.50},
    "expected_likes": {"low": 10, "mid": 50, "high": 200},
    "expected_comments": {"low": 2, "mid": 15, "high": 60},
    "expected_shares": {"low": 1, "mid": 10, "high": 50},
    "confidence": "yellow",
    "bet": "钩子强但话题偏小众，预计 2000 左右播放",
}

SAMPLE_RETRO = {
    "actual_views": 3500,
    "actual_completion_rate": 0.35,
    "actual_likes": 78,
    "actual_comments": 22,
    "actual_shares": 8,
    "accuracy": {
        "views": "mid_correct",
        "completion_rate": "mid_correct",
        "likes": "mid_correct",
        "comments": "mid_correct",
        "shares": "low_correct",
    },
    "notes": "播放量超预期，话题比预想更广",
}


class TestCreatePrediction:
    def test_create_and_retrieve(self, store, asset):
        pred = store.create_prediction(
            asset_id=asset["id"],
            prediction=SAMPLE_PREDICTION,
        )
        assert pred["asset_id"] == asset["id"]
        assert pred["status"] == "pending"
        assert pred["prediction"] == SAMPLE_PREDICTION
        assert pred["retro"] is None

        fetched = store.get_prediction(pred["id"])
        assert fetched["prediction"] == SAMPLE_PREDICTION

    def test_create_with_task(self, store, asset, task):
        pred = store.create_prediction(
            asset_id=asset["id"],
            prediction=SAMPLE_PREDICTION,
            task_id=task["id"],
        )
        assert pred["task_id"] == task["id"]

        events = store.list_events(task["id"])
        pred_events = [e for e in events if e["event_type"] == "content.prediction_created"]
        assert len(pred_events) == 1

    def test_no_event_without_task(self, store, asset):
        pred = store.create_prediction(
            asset_id=asset["id"],
            prediction=SAMPLE_PREDICTION,
        )
        assert pred["task_id"] is None

    def test_get_nonexistent_raises(self, store):
        with pytest.raises(KeyError, match="prediction not found"):
            store.get_prediction("pred_nonexistent")


class TestImmutability:
    """The core principle: predictions are immutable once written."""

    def test_duplicate_returns_existing(self, store, asset, task):
        """Creating a prediction for the same asset+task returns the original."""
        pred1 = store.create_prediction(
            asset_id=asset["id"],
            prediction=SAMPLE_PREDICTION,
            task_id=task["id"],
        )
        pred2 = store.create_prediction(
            asset_id=asset["id"],
            prediction={"different": "prediction"},
            task_id=task["id"],
        )
        # Same ID, original content preserved
        assert pred1["id"] == pred2["id"]
        assert pred2["prediction"] == SAMPLE_PREDICTION
        assert pred2["prediction"] != {"different": "prediction"}

    def test_no_task_allows_multiple(self, store, asset):
        """Without task_id, multiple predictions can be created for the same asset."""
        pred1 = store.create_prediction(
            asset_id=asset["id"],
            prediction={"v1": True},
        )
        pred2 = store.create_prediction(
            asset_id=asset["id"],
            prediction={"v2": True},
        )
        assert pred1["id"] != pred2["id"]

    def test_prediction_not_modified_by_retro(self, store, asset):
        """Retro updates status and retro_json, but prediction_json stays unchanged."""
        pred = store.create_prediction(
            asset_id=asset["id"],
            prediction=SAMPLE_PREDICTION,
        )
        original_prediction = pred["prediction"]

        store.record_retro(pred["id"], SAMPLE_RETRO)
        updated = store.get_prediction(pred["id"])
        assert updated["prediction"] == original_prediction
        assert updated["retro"] == SAMPLE_RETRO
        assert updated["status"] == "retro_completed"


class TestRetro:
    def test_record_retro(self, store, asset):
        pred = store.create_prediction(
            asset_id=asset["id"],
            prediction=SAMPLE_PREDICTION,
        )
        result = store.record_retro(pred["id"], SAMPLE_RETRO)
        assert result["status"] == "retro_completed"
        assert result["retro"] == SAMPLE_RETRO
        assert result["retro_at"] is not None

    def test_retro_idempotent(self, store, asset):
        """Recording retro twice is idempotent."""
        pred = store.create_prediction(
            asset_id=asset["id"],
            prediction=SAMPLE_PREDICTION,
        )
        store.record_retro(pred["id"], SAMPLE_RETRO)
        result = store.record_retro(pred["id"], {"different": "retro"})
        # Second call returns existing, doesn't overwrite
        assert result["retro"] == SAMPLE_RETRO
        assert result["retro"] != {"different": "retro"}

    def test_retro_nonexistent_raises(self, store):
        with pytest.raises(KeyError, match="prediction not found"):
            store.record_retro("pred_nonexistent", SAMPLE_RETRO)

    def test_retro_event_emitted(self, store, asset, task):
        pred = store.create_prediction(
            asset_id=asset["id"],
            prediction=SAMPLE_PREDICTION,
            task_id=task["id"],
        )
        store.record_retro(pred["id"], SAMPLE_RETRO)
        events = store.list_events(task["id"])
        retro_events = [e for e in events if e["event_type"] == "content.retrospective"]
        assert len(retro_events) == 1
        assert retro_events[0]["payload"]["prediction_id"] == pred["id"]


class TestQueryPredictions:
    def test_get_by_asset(self, store, asset):
        pred = store.create_prediction(
            asset_id=asset["id"],
            prediction=SAMPLE_PREDICTION,
        )
        found = store.get_prediction_by_asset(asset["id"])
        assert found is not None
        assert found["id"] == pred["id"]

    def test_get_by_asset_and_task(self, store, asset, task):
        pred = store.create_prediction(
            asset_id=asset["id"],
            prediction=SAMPLE_PREDICTION,
            task_id=task["id"],
        )
        found = store.get_prediction_by_asset(asset["id"], task["id"])
        assert found is not None
        assert found["id"] == pred["id"]

    def test_get_by_asset_not_found(self, store):
        assert store.get_prediction_by_asset("asset_nonexistent") is None

    def test_list_by_asset(self, store, asset):
        store.create_prediction(asset_id=asset["id"], prediction={"v1": True})
        store.create_prediction(asset_id=asset["id"], prediction={"v2": True})
        results = store.list_predictions(asset_id=asset["id"])
        assert len(results) == 2

    def test_list_by_status(self, store, asset):
        pred = store.create_prediction(asset_id=asset["id"], prediction=SAMPLE_PREDICTION)
        store.record_retro(pred["id"], SAMPLE_RETRO)
        store.create_prediction(asset_id=asset["id"], prediction={"v2": True})
        pending = store.list_predictions(status="pending")
        completed = store.list_predictions(status="retro_completed")
        assert len(pending) == 1
        assert len(completed) == 1

    def test_list_all(self, store, asset):
        store.create_prediction(asset_id=asset["id"], prediction={"v1": True})
        results = store.list_predictions()
        assert len(results) >= 1


class TestSecretsRedaction:
    def test_secrets_redacted_in_prediction(self, store, asset):
        pred = store.create_prediction(
            asset_id=asset["id"],
            prediction={"api_key": "sk-1234567890abcdef", "views": 1000},
        )
        fetched = store.get_prediction(pred["id"])
        assert fetched["prediction"]["api_key"] == "[REDACTED]"
        assert fetched["prediction"]["views"] == 1000

    def test_secrets_redacted_in_retro(self, store, asset):
        pred = store.create_prediction(asset_id=asset["id"], prediction=SAMPLE_PREDICTION)
        store.record_retro(pred["id"], {"api_key": "sk-secret1234567890", "views": 5000})
        fetched = store.get_prediction(pred["id"])
        assert fetched["retro"]["api_key"] == "[REDACTED]"
        assert fetched["retro"]["views"] == 5000


class TestFullLifecycle:
    """Full lifecycle: score → predict → publish → retro → check accuracy."""

    def test_score_then_predict_then_retro(self, store, asset, task):
        from engine.agent_core.content_rubric import OPINION_VIDEO_RUBRIC

        # 1. Score the content
        scores = {d.key: 7 for d in OPINION_VIDEO_RUBRIC}
        score = store.record_content_score(
            asset_id=asset["id"],
            scores=scores,
            task_id=task["id"],
        )
        assert score["weighted_total"] == 5.6

        # 2. Write blind prediction
        pred = store.create_prediction(
            asset_id=asset["id"],
            prediction=SAMPLE_PREDICTION,
            task_id=task["id"],
        )
        assert pred["status"] == "pending"

        # 3. Record retro with actual data
        retro = store.record_retro(pred["id"], SAMPLE_RETRO)
        assert retro["status"] == "retro_completed"

        # 4. Verify prediction was not modified
        final = store.get_prediction(pred["id"])
        assert final["prediction"] == SAMPLE_PREDICTION
        assert final["retro"] == SAMPLE_RETRO

        # 5. Check events
        events = store.list_events(task["id"])
        event_types = [e["event_type"] for e in events]
        assert "content.scored" in event_types
        assert "content.prediction_created" in event_types
        assert "content.retrospective" in event_types
