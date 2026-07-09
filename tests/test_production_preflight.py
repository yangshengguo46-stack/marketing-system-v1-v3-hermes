"""CORE-LOOP-04: content-production preflight boundaries."""

from engine.agent_core.hermes_adapter import HermesAgentService
from engine.agent_core.production_preflight import (
    build_content_production_preflight,
    create_content_production_preflight,
)
from engine.agent_core.store import AgentCoreStore
from engine.video_core.high_end_preflight import preflight_high_end_video_project
from engine.video_core.schema import Budget, BudgetLine, Project, Scene, Shot, StyleLock


def _demo_video_project() -> Project:
    return Project(
        id="video-preflight-demo",
        brief="一条高质感 AI 教育数字人短片",
        script="普通人不是缺工具，而是缺一条能跑通的路径。",
        style_lock=StyleLock(
            palette="warm orange and black",
            art_style="cinematic, premium social short",
            reference_asset_ids=["asset-hero"],
            locked=True,
        ),
        scenes=[
            Scene(
                id="scene-1",
                summary="主角在夜晚办公桌前意识到 AI 可以成为副驾驶",
                shots=[
                    Shot(
                        id="shot-1",
                        scene_id="scene-1",
                        slot_id="slot-1",
                        storyboard_asset_id="storyboard-1",
                        asset_refs=["asset-hero"],
                        camera_prompt="slow push-in, shallow depth of field",
                        duration_sec=2.5,
                    ),
                    Shot(
                        id="shot-2",
                        scene_id="scene-1",
                        slot_id="slot-2",
                        storyboard_asset_id="storyboard-2",
                        asset_refs=["asset-hero"],
                        camera_prompt="cut to screen reflection, subtle parallax",
                        duration_sec=3.0,
                    ),
                ],
            )
        ],
        timeline={
            "slots": [
                {"id": "slot-1", "order": 1, "duration_sec": 2.5, "shot_id": "shot-1"},
                {"id": "slot-2", "order": 2, "duration_sec": 3.0, "shot_id": "shot-2"},
            ]
        },
        budget=Budget(
            total=120,
            approved=True,
            lines=[BudgetLine(label="shots", allocated=84), BudgetLine(label="retry", allocated=24)],
        ),
    )


def test_content_preflight_persists_general_record(tmp_path):
    store = AgentCoreStore(tmp_path / "content-preflight.db")

    result = create_content_production_preflight(store, {
        "objective": "写一篇公众号软文，讲普通人怎么用 AI 做副业",
        "kind": "article_soft",
        "platforms": ["wechat_official"],
        "account_id": "acct_ai",
        "audience_context": {
            "target_reader": "想用 AI 提升收入的普通职场人",
            "pain_points": ["不知道从哪里开始"],
        },
        "evidence": [{"title": "AI 工具公开资料", "url": "https://example.com/ai"}],
    })

    assert result["preflight_id"].startswith("preflight_")
    assert result["scope"] == "content_business_preflight"
    assert result["decision"]["status"] == "ready_for_asset_draft"
    assert result["decision"]["go"] is True
    assert result["influence_score"]["version"] == "influenceos-score-v0.1"
    assert result["preflight_decision"]["version"] == "preflight-decision-v0.1"
    assert result["preflight_decision"]["status"] == result["decision"]["status"]

    stored = store.get_preflight_record(result["preflight_id"])
    assert stored["formula_version"] == "content-production-preflight-v0.1"
    assert stored["scores"]["overall"] >= 0.62
    assert stored["decision"]["selected_lane"] == "article_soft"
    assert stored["decision"]["preflight_decision"]["version"] == "preflight-decision-v0.1"
    assert stored["decision"]["video_previsualization_status"] == "not_required_for_lane"


def test_premium_video_general_preflight_delegates_film_previsualization(tmp_path):
    store = AgentCoreStore(tmp_path / "premium-preflight.db")
    project = _demo_video_project()

    result = create_content_production_preflight(store, {
        "objective": "做一条真人数字人高质量视频",
        "kind": "premium_human_video",
        "platforms": ["douyin"],
        "account_id": "acct_ai",
        "audience_context": {"target_reader": "AI 教育创业者"},
        "video_project": project.model_dump(),
    })

    assert result["kind"] == "premium_human_video"
    assert result["decision"]["status"] == "delegate_to_video_previsualization"
    assert result["decision"]["go"] is False
    assert result["preflight_decision"]["status"] == "delegate_to_video_previsualization"
    assert result["video_previsualization"]["scope"] == "film_previsualization"
    assert result["video_previsualization"]["agent"] == "high_end_video_previsualization_agent"
    assert "shot_feasibility" in result["video_previsualization"]["scores"]

    stored = store.get_preflight_record(result["preflight_id"])
    assert stored["scores"]["overall"] == result["scores"]["overall"]
    assert "shot_feasibility" not in stored["scores"]
    assert "visual_continuity_basis" not in stored["scores"]
    assert stored["decision"]["video_previsualization_status"] == result["video_previsualization"]["status"]


def test_video_core_preflight_is_film_scope_only():
    report = preflight_high_end_video_project(_demo_video_project())

    assert report["scope"] == "film_previsualization"
    assert "platform_attention_score" in report["not_responsible_for"]
    assert "long_term_memory_promotion" in report["not_responsible_for"]
    assert "visual_continuity" in report["owns"]
    assert report["observations"]["shot_count"] == 2


def test_content_preflight_build_without_account_blocks_on_audience_context():
    result = build_content_production_preflight({
        "objective": "写一篇公众号软文",
        "kind": "article_soft",
        "evidence": [{"title": "证据", "url": "https://example.com"}],
    })

    assert result["decision"]["status"] == "needs_audience_context"
    assert "audience_context_missing" in result["decision"]["blockers"]
    assert result["preflight_decision"]["next_action"].startswith("通过账号生命周期")


def test_initial_plan_routes_content_production_through_preflight():
    steps = HermesAgentService._build_initial_plan("帮我写一篇公众号软文", None)
    tools = [step.get("tool_name") for step in steps]

    assert tools[0] == "marketing_plan_content_production"
    assert tools[1] == "marketing_draft_content_preflight"
    assert "marketing_draft_soft_article_create" in tools
