from __future__ import annotations

from agent.marketing.data_paths import MarketingDataPaths
from agent.marketing.workflows import topic_production


def _paths(tmp_path):
    return MarketingDataPaths(
        user_data=tmp_path,
        config_dir=tmp_path / "config",
        agent_db=tmp_path / "state.db",
    )


def _candidate():
    return {
        "id": "topic_candidate_ai_bubble",
        "user_id": "default",
        "entity_id": "entity-1",
        "account_id": "acct-main",
        "topic": "当前的 AI 是泡沫吗？",
        "angle": "区分估值、真实需求与生产率",
        "plan_id": "plan-1",
        "preflight_id": "preflight-1",
        "target_platforms": ["wechat_official", "douyin", "x", "future_social"],
        "evidence_refs": ["evidence-1"],
        "signal_refs": ["signal-1"],
        "recommendation_eligible": True,
        "candidate": {
            "recommendation_type": "general",
            "recommended_platforms": ["wechat_official", "douyin", "x"],
            "platform_matches": [
                {"platform": "douyin", "match_score": 91},
                {"platform": "wechat_official", "match_score": 86},
            ],
            "platform_blueprints": {},
        },
    }


def test_topic_workflow_fans_article_and_video_out_as_siblings(tmp_path, monkeypatch):
    monkeypatch.setattr(
        topic_production.TopicRecommendationRepository,
        "get_candidate",
        lambda self, **kwargs: _candidate(),
    )
    monkeypatch.setattr(
        topic_production, "_automatic_voiceover_authorized", lambda: True
    )
    workflow = topic_production.create_topic_production_workflow(
        candidate_id="topic_candidate_ai_bubble",
        user_id="default",
        entity_id="entity-1",
        paths=_paths(tmp_path),
    )
    steps = {step["key"]: step for step in workflow["steps"]}

    assert workflow["policy"]["automatic_voiceover_authorized"] is True
    assert workflow["policy"]["paid_generation_allowed"] is False
    assert steps["article.write.wechat_official"]["depends_on"] == [
        "topic_brief.freeze"
    ]
    assert steps["video.direct.douyin"]["depends_on"] == ["topic_brief.freeze"]
    assert not any(
        key.startswith("article.")
        for key in steps["video.direct.douyin"]["depends_on"]
    )
    assert not any(
        key.startswith("video.")
        for key in steps["article.write.wechat_official"]["depends_on"]
    )
    assert "article.write.wechat_official" in steps
    assert "article.qa.wechat_official" in steps
    assert "video.direct.douyin" in steps
    assert "video.preflight.douyin" in steps
    assert "article.write.x" in steps
    assert "video.direct.x" in steps
    # future_social was evaluated, but was not recommended. Production must not
    # silently manufacture every platform that happened to be scored.
    assert "platform.research.future_social" not in steps
    assert steps["video.previs.douyin"]["depends_on"] == [
        "video.preflight.douyin",
        "video.material.douyin",
        "video.audio.douyin",
    ]
    assert steps["video.render.douyin"]["depends_on"] == ["video.previs.douyin"]
    assert steps["video.qa.douyin"]["depends_on"] == ["video.render.douyin"]
    assert set(steps["video.draft_box"]["depends_on"]) == {
        "video.qa.douyin",
        "video.qa.x",
    }
    assert set(steps["article.draft_box"]["depends_on"]) == {
        "article.qa.wechat_official",
        "article.qa.x",
    }
    assert not any(
        dependency.startswith("article.")
        for key, step in steps.items()
        if key.startswith("video.")
        for dependency in step["depends_on"]
    )
    assert set(steps["production.complete"]["depends_on"]) == {
        "article.draft_box",
        "video.draft_box",
    }


def test_topic_workflow_is_idempotent_per_preflighted_candidate(tmp_path, monkeypatch):
    monkeypatch.setattr(
        topic_production.TopicRecommendationRepository,
        "get_candidate",
        lambda self, **kwargs: _candidate(),
    )
    paths = _paths(tmp_path)
    first = topic_production.create_topic_production_workflow(
        candidate_id="topic_candidate_ai_bubble",
        user_id="default",
        entity_id="entity-1",
        paths=paths,
    )
    second = topic_production.create_topic_production_workflow(
        candidate_id="topic_candidate_ai_bubble",
        user_id="default",
        entity_id="entity-1",
        paths=paths,
    )
    assert second["id"] == first["id"]
    assert len(second["steps"]) == len(first["steps"])


def test_explicit_user_override_can_add_an_evaluated_platform(tmp_path, monkeypatch):
    candidate = _candidate()
    candidate["candidate"]["recommended_platforms"] = ["wechat_official"]
    monkeypatch.setattr(
        topic_production.TopicRecommendationRepository,
        "get_candidate",
        lambda self, **kwargs: candidate,
    )
    workflow = topic_production.create_topic_production_workflow(
        candidate_id="topic_candidate_ai_bubble",
        user_id="default",
        entity_id="entity-1",
        selected_platforms=["wechat_official", "douyin"],
        explicit_user_override=True,
        paths=_paths(tmp_path),
    )
    keys = {step["key"] for step in workflow["steps"]}

    assert workflow["input"]["explicit_user_platform_override"] is True
    assert workflow["input"]["selected_platforms"] == ["wechat_official", "douyin"]
    assert "article.write.wechat_official" in keys
    assert "video.direct.douyin" in keys


def test_platform_override_must_be_explicit_and_preflighted(tmp_path, monkeypatch):
    monkeypatch.setattr(
        topic_production.TopicRecommendationRepository,
        "get_candidate",
        lambda self, **kwargs: _candidate(),
    )
    try:
        topic_production.create_topic_production_workflow(
            candidate_id="topic_candidate_ai_bubble",
            user_id="default",
            entity_id="entity-1",
            selected_platforms=["douyin"],
            paths=_paths(tmp_path),
        )
    except ValueError as exc:
        assert "explicit user override" in str(exc)
    else:
        raise AssertionError("implicit platform override must be rejected")

    try:
        topic_production.create_topic_production_workflow(
            candidate_id="topic_candidate_ai_bubble",
            user_id="default",
            entity_id="entity-1",
            selected_platforms=["unpreflighted_platform"],
            explicit_user_override=True,
            paths=_paths(tmp_path),
        )
    except ValueError as exc:
        assert "not evaluated" in str(exc)
    else:
        raise AssertionError("unpreflighted platform override must be rejected")
