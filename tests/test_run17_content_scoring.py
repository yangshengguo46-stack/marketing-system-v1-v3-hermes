"""RUN-17: Content scoring protocol tests.

Tests the 9-dimension rubric (7 positive + 2 negative), score validation,
weighted total computation, store persistence, event emission, and
multi-scorer support.
"""

import pytest
from engine.agent_core.content_rubric import (
    OPINION_VIDEO_RUBRIC,
    ContentScore,
    compute_weighted_total,
    get_rubric,
    rubric_to_dict,
    score_content,
    validate_scores,
)
from engine.agent_core.store import AgentCoreStore


# ── Rubric structure tests ────────────────────────────────────────────


class TestRubricStructure:
    def test_nine_dimensions(self):
        assert len(OPINION_VIDEO_RUBRIC) == 9

    def test_weights_sum_to_one(self):
        total = sum(d.weight for d in OPINION_VIDEO_RUBRIC)
        assert abs(total - 1.0) < 1e-6

    def test_all_keys_unique(self):
        keys = [d.key for d in OPINION_VIDEO_RUBRIC]
        assert len(keys) == len(set(keys))

    def test_all_weights_positive(self):
        for d in OPINION_VIDEO_RUBRIC:
            assert d.weight > 0

    def test_dimension_keys(self):
        keys = {d.key for d in OPINION_VIDEO_RUBRIC}
        assert keys == {"hook", "topic", "emotion", "density", "pacing", "viewpoint", "cta",
                        "title_bait_risk", "controversy_overload_risk"}

    def test_get_rubric_default(self):
        rubric = get_rubric()
        assert rubric == OPINION_VIDEO_RUBRIC

    def test_get_rubric_explicit(self):
        rubric = get_rubric("opinion_video")
        assert len(rubric) == 9

    def test_get_rubric_unknown(self):
        with pytest.raises(ValueError, match="unknown rubric type"):
            get_rubric("nonexistent")

    def test_rubric_to_dict(self):
        items = rubric_to_dict()
        assert len(items) == 9
        assert all("key" in i and "label" in i and "weight" in i and "is_negative" in i for i in items)


# ── Score validation tests ────────────────────────────────────────────


class TestScoreValidation:
    def test_valid_full_scores(self):
        scores = {d.key: 8 for d in OPINION_VIDEO_RUBRIC}
        validate_scores(scores)  # should not raise

    def test_valid_zero_scores(self):
        scores = {d.key: 0 for d in OPINION_VIDEO_RUBRIC}
        validate_scores(scores)

    def test_valid_max_scores(self):
        scores = {d.key: 10 for d in OPINION_VIDEO_RUBRIC}
        validate_scores(scores)

    def test_missing_dimension(self):
        scores = {d.key: 8 for d in OPINION_VIDEO_RUBRIC if d.key != "hook"}
        with pytest.raises(ValueError, match="missing dimension"):
            validate_scores(scores)

    def test_extra_dimension(self):
        scores = {d.key: 8 for d in OPINION_VIDEO_RUBRIC}
        scores["extra"] = 5
        with pytest.raises(ValueError, match="unknown dimension"):
            validate_scores(scores)

    def test_score_out_of_range_negative(self):
        scores = {d.key: 8 for d in OPINION_VIDEO_RUBRIC}
        scores["hook"] = -1
        with pytest.raises(ValueError, match="must be int 0"):
            validate_scores(scores)

    def test_score_out_of_range_too_high(self):
        scores = {d.key: 8 for d in OPINION_VIDEO_RUBRIC}
        scores["hook"] = 11
        with pytest.raises(ValueError, match="must be int 0"):
            validate_scores(scores)

    def test_non_int_score(self):
        scores = {d.key: 8 for d in OPINION_VIDEO_RUBRIC}
        scores["hook"] = 8.5
        with pytest.raises(ValueError, match="must be int 0"):
            validate_scores(scores)


# ── Weighted total computation tests ──────────────────────────────────


class TestWeightedTotal:
    def test_all_max_scores(self):
        scores = {d.key: 10 for d in OPINION_VIDEO_RUBRIC}
        total = compute_weighted_total(scores)
        # Positive dims: 10*0.90*10 = 9.0; negative dims: -10*0.10*10 = -1.0
        assert total == 8.0

    def test_all_zero_scores(self):
        scores = {d.key: 0 for d in OPINION_VIDEO_RUBRIC}
        total = compute_weighted_total(scores)
        assert total == 0.0

    def test_all_mid_scores(self):
        scores = {d.key: 5 for d in OPINION_VIDEO_RUBRIC}
        total = compute_weighted_total(scores)
        # Positive: 0.5*0.90*10 = 4.5; negative: -0.5*0.10*10 = -0.5
        assert total == 4.0

    def test_weighted_by_importance(self):
        # hook weight=0.18, cta weight=0.11
        # If hook=10, cta=0, and everything else=5:
        scores = {d.key: 5 for d in OPINION_VIDEO_RUBRIC}
        scores["hook"] = 10
        scores["cta"] = 0
        total = compute_weighted_total(scores)
        # base (all 5): 0.5*0.90*10 - 0.5*0.10*10 = 4.5 - 0.5 = 4.0
        # hook delta: (1.0-0.5)*0.18*10 = +0.9
        # cta delta: (0.0-0.5)*0.11*10 = -0.55
        # total = 4.0 + 0.9 - 0.55 = 4.35
        assert total == 4.35

    def test_total_range(self):
        scores = {d.key: 7 for d in OPINION_VIDEO_RUBRIC}
        total = compute_weighted_total(scores)
        assert 0.0 <= total <= 10.0


# ── score_content helper tests ────────────────────────────────────────


class TestScoreContent:
    def test_returns_content_score(self):
        scores = {d.key: 7 for d in OPINION_VIDEO_RUBRIC}
        result = score_content(scores, notes="good hook", scored_by="agent")
        assert isinstance(result, ContentScore)
        assert result.rubric_type == "opinion_video"
        # Positive: 0.7*0.90*10 = 6.3; negative: -0.7*0.10*10 = -0.7
        assert result.weighted_total == 5.6
        assert result.notes == "good hook"
        assert result.scored_by == "agent"

    def test_with_metadata(self):
        scores = {d.key: 6 for d in OPINION_VIDEO_RUBRIC}
        result = score_content(scores, metadata={"version": "v2", "script_path": "scripts/foo.md"})
        assert result.metadata["version"] == "v2"
        assert result.metadata["script_path"] == "scripts/foo.md"

    def test_invalid_scores_raise(self):
        scores = {d.key: 8 for d in OPINION_VIDEO_RUBRIC if d.key != "hook"}
        with pytest.raises(ValueError):
            score_content(scores)


# ── Store integration tests ───────────────────────────────────────────


@pytest.fixture
def store(tmp_path):
    return AgentCoreStore(tmp_path / "test_run17.db")


@pytest.fixture
def asset(store):
    """Create a content asset for scoring."""
    return store.create_content_asset(title="test video script", type="script")


@pytest.fixture
def task(store):
    """Create a task for event emission."""
    session = store.create_or_get_session(user_id="test_user")
    return store.create_task(
        session_id=session["id"],
        user_id="test_user",
        objective="test objective",
    )


class TestStoreContentScore:
    def test_record_and_retrieve(self, store, asset):
        scores = {d.key: 8 for d in OPINION_VIDEO_RUBRIC}
        result = store.record_content_score(
            asset_id=asset["id"],
            scores=scores,
            notes="strong hook, weak cta",
        )
        assert result["asset_id"] == asset["id"]
        assert result["rubric_type"] == "opinion_video"
        # Positive: 0.8*0.90*10 = 7.2; negative: -0.8*0.10*10 = -0.8
        assert result["weighted_total"] == 6.4
        assert result["notes"] == "strong hook, weak cta"
        assert result["scored_by"] == "agent"
        assert result["scores"] == scores

    def test_get_by_id(self, store, asset):
        scores = {d.key: 7 for d in OPINION_VIDEO_RUBRIC}
        created = store.record_content_score(asset_id=asset["id"], scores=scores)
        fetched = store.get_content_score(created["id"])
        assert fetched["id"] == created["id"]
        assert fetched["weighted_total"] == 5.6

    def test_get_nonexistent_raises(self, store):
        with pytest.raises(KeyError, match="content score not found"):
            store.get_content_score("score_nonexistent")

    def test_list_by_asset(self, store, asset):
        scores1 = {d.key: 6 for d in OPINION_VIDEO_RUBRIC}
        scores2 = {d.key: 8 for d in OPINION_VIDEO_RUBRIC}
        store.record_content_score(asset_id=asset["id"], scores=scores1)
        store.record_content_score(asset_id=asset["id"], scores=scores2)
        results = store.list_content_scores(asset_id=asset["id"])
        assert len(results) == 2
        # Most recent first; 8*0.9-8*0.1=6.4, 6*0.9-6*0.1=4.8
        assert results[0]["weighted_total"] == 6.4
        assert results[1]["weighted_total"] == 4.8

    def test_list_by_rubric_type(self, store, asset):
        scores = {d.key: 7 for d in OPINION_VIDEO_RUBRIC}
        store.record_content_score(asset_id=asset["id"], scores=scores, rubric_type="opinion_video")
        results = store.list_content_scores(rubric_type="opinion_video")
        assert len(results) == 1
        results_other = store.list_content_scores(rubric_type="nonexistent")
        assert len(results_other) == 0

    def test_list_by_scored_by(self, store, asset):
        scores = {d.key: 7 for d in OPINION_VIDEO_RUBRIC}
        store.record_content_score(asset_id=asset["id"], scores=scores, scored_by="agent")
        store.record_content_score(asset_id=asset["id"], scores=scores, scored_by="blind_agent")
        agent_results = store.list_content_scores(scored_by="agent")
        blind_results = store.list_content_scores(scored_by="blind_agent")
        assert len(agent_results) == 1
        assert len(blind_results) == 1

    def test_event_emitted_with_task(self, store, asset, task):
        scores = {d.key: 8 for d in OPINION_VIDEO_RUBRIC}
        store.record_content_score(
            asset_id=asset["id"],
            scores=scores,
            task_id=task["id"],
        )
        events = store.list_events(task["id"])
        score_events = [e for e in events if e["event_type"] == "content.scored"]
        assert len(score_events) == 1
        payload = score_events[0]["payload"]
        assert payload["asset_id"] == asset["id"]
        assert payload["weighted_total"] == 6.4
        assert payload["scored_by"] == "agent"

    def test_no_event_without_task(self, store, asset):
        scores = {d.key: 8 for d in OPINION_VIDEO_RUBRIC}
        store.record_content_score(asset_id=asset["id"], scores=scores)
        # No task_id → no event, but score still recorded
        results = store.list_content_scores(asset_id=asset["id"])
        assert len(results) == 1

    def test_invalid_scores_rejected(self, store, asset):
        scores = {d.key: 8 for d in OPINION_VIDEO_RUBRIC if d.key != "hook"}
        with pytest.raises(ValueError, match="missing dimension"):
            store.record_content_score(asset_id=asset["id"], scores=scores)

    def test_metadata_persisted(self, store, asset):
        scores = {d.key: 7 for d in OPINION_VIDEO_RUBRIC}
        store.record_content_score(
            asset_id=asset["id"],
            scores=scores,
            metadata={"script_path": "scripts/test.md", "version": "v1"},
        )
        results = store.list_content_scores(asset_id=asset["id"])
        assert results[0]["metadata"]["script_path"] == "scripts/test.md"
        assert results[0]["metadata"]["version"] == "v1"

    def test_multiple_scores_same_asset(self, store, asset):
        """An asset can be scored multiple times (e.g., agent + blind_agent + user)."""
        scores = {d.key: 7 for d in OPINION_VIDEO_RUBRIC}
        store.record_content_score(asset_id=asset["id"], scores=scores, scored_by="agent")
        store.record_content_score(asset_id=asset["id"], scores=scores, scored_by="blind_agent")
        store.record_content_score(asset_id=asset["id"], scores=scores, scored_by="user")
        results = store.list_content_scores(asset_id=asset["id"])
        assert len(results) == 3
        scored_by_set = {r["scored_by"] for r in results}
        assert scored_by_set == {"agent", "blind_agent", "user"}

    def test_secrets_redacted_in_metadata(self, store, asset):
        scores = {d.key: 7 for d in OPINION_VIDEO_RUBRIC}
        store.record_content_score(
            asset_id=asset["id"],
            scores=scores,
            metadata={"api_key": "sk-1234567890abcdef"},
        )
        results = store.list_content_scores(asset_id=asset["id"])
        assert results[0]["metadata"]["api_key"] == "[REDACTED]"
