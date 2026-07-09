"""End-to-end wiring tests for the product-owned learning flywheel."""

from __future__ import annotations

from agent_core.learning_pipeline import (
    build_metric_labels,
    get_learning_status,
    reconcile_published_metrics,
    review_content_asset,
)
from agent_core.store import AgentCoreStore


SCORES = {
    "hook": 8, "topic": 8, "emotion": 6, "density": 7,
    "pacing": 7, "viewpoint": 8, "cta": 6,
    "title_bait_risk": 1, "controversy_overload_risk": 1,
}
PREDICTION = {
    "expected_views": {"low": 100, "mid": 500, "high": 1000},
    "expected_completion_rate": {"low": 0.2, "mid": 0.35, "high": 0.5},
    "expected_engagement_rate": {"low": 0.02, "mid": 0.05, "high": 0.1},
}


def test_metric_labels_convert_raw_metrics_without_fake_missing_values():
    labels = build_metric_labels({
        "views": 1200,
        "completion_rate": 0.41,
        "engagement_rate": 0.06,
    })

    assert labels["version"] == "metric-labels-v0.1"
    assert labels["labels"]["attention"]["bucket"] == "high"
    assert labels["labels"]["retention"]["bucket"] == "spike"
    assert labels["labels"]["trust"]["bucket"] == "mid"
    assert "action" in labels["missing_dimensions"]
    assert "risk" in labels["missing_dimensions"]


def _asset(store: AgentCoreStore):
    return store.create_content_asset(
        user_id="user-1", account_id="acct-1", platform="douyin",
        title="新能源汽车选题", type="script", content={"script": "正文"},
    )


def test_review_writes_score_and_immutable_prediction(tmp_path):
    store = AgentCoreStore(tmp_path / "core.db")
    asset = _asset(store)

    result = review_content_asset(
        store, asset_id=asset["id"], scores=SCORES,
        prediction=PREDICTION, notes="发布前评审",
    )

    assert result["score"]["asset_id"] == asset["id"]
    assert result["prediction"]["prediction"] == PREDICTION
    second = review_content_asset(
        store, asset_id=asset["id"], scores=SCORES,
        prediction={"expected_views": {"low": 1, "mid": 2, "high": 3}},
    )
    assert second["prediction"]["id"] == result["prediction"]["id"]
    assert second["prediction"]["prediction"] == PREDICTION


def test_content_approval_publish_and_metrics_drive_flywheel(tmp_path):
    store = AgentCoreStore(tmp_path / "core.db")
    asset = _asset(store)
    review_content_asset(store, asset_id=asset["id"], scores=SCORES, prediction=PREDICTION)

    store.transition_content_asset(asset["id"], "review")
    store.transition_content_asset(asset["id"], "approved")
    assert store.get_cadence_status("user-1", "acct-1")["buffer"] == 1

    publishing = store.create_publishing_task(asset_id=asset["id"], platform="douyin")
    published = store.complete_publishing_task(
        publishing["id"], effect_id="effect-real",
        receipt={"status": "ok", "platform_post_id": "post-123"},
    )
    assert published["next_metrics_at"] is not None
    assert store.get_cadence_status("user-1", "acct-1")["buffer"] == 0

    completed = store.collect_metrics(publishing["id"], {
        "views": 1200, "completion_rate": 0.41, "engagement_rate": 0.06,
    })

    assert completed["learning"]["status"] == "reconciled"
    assert completed["learning"]["memory_status"] == "pending"
    assert completed["learning"]["learning_candidate_id"]
    assert completed["learning"]["learning_candidate_status"] == "pending"
    assert completed["learning"]["metric_labels"]["labels"]["attention"]["source_metric"] == "views"
    prediction = store.get_prediction_by_asset(asset["id"])
    assert prediction["status"] == "retro_completed"
    assert prediction["retro"]["metric_labels"]["labels"]["retention"]["source_metric"] == "completion_rate"
    learning_candidate = store.get_learning_candidate(completed["learning"]["learning_candidate_id"])
    assert learning_candidate["status"] == "pending"
    assert learning_candidate["candidate_type"] == "memory"
    assert learning_candidate["prediction_id"] == prediction["id"]
    assert learning_candidate["receipt_refs"]
    assert learning_candidate["proposal"]["guardrail"].startswith("pending candidate only")
    memories = store.list_memories(user_id="user-1", account_id="acct-1", status="pending")
    assert len(memories) == 1
    assert memories[0]["classification"]["source"] == "published_result"
    assert "post-123" not in memories[0]["content"]  # receipt IDs are evidence refs, not prose


def test_learning_status_is_user_and_account_scoped(tmp_path):
    store = AgentCoreStore(tmp_path / "core.db")
    owned = _asset(store)
    store.create_content_asset(user_id="other", account_id="acct-2", title="other")
    review_content_asset(store, asset_id=owned["id"], scores=SCORES, prediction=PREDICTION)

    status = get_learning_status(store, user_id="user-1", account_id="acct-1")

    assert status["content_assets"] == 1
    assert status["content_scores"] == 1
    assert status["predictions_pending"] == 1
    assert status["retrospectives"] == 0
    assert status["cadence"]["account_id"] == "acct-1"


def test_metrics_without_prediction_are_recorded_without_fake_learning(tmp_path):
    store = AgentCoreStore(tmp_path / "core.db")
    asset = _asset(store)
    publishing = store.create_publishing_task(asset_id=asset["id"], platform="douyin")
    store.complete_publishing_task(
        publishing["id"], effect_id="effect-real",
        receipt={"status": "ok", "platform_post_id": "post-456"},
    )

    result = reconcile_published_metrics(store, publishing["id"], {"views": 10})

    assert result["status"] == "metrics_recorded"
    assert result["prediction"] == "missing"
    assert result["memory_candidate_id"] is None
    assert result["learning_candidate_id"] is None
    assert result["metric_labels"]["labels"]["attention"]["value"] == 10.0
    assert store.list_learning_candidates() == []
