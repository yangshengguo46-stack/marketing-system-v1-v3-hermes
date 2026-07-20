from __future__ import annotations

from types import SimpleNamespace

from agent.marketing.domains.account_context import AccountContextRepository
from agent.marketing.workflows.topic_workers import (
    TopicProductionWorkers,
    _article_writer_projection,
    _bounded_preflight_projection,
    _evidence_pack_projection,
    _knowledge_for_production_target,
)


def test_video_intake_submits_one_official_kanban_without_running_legacy_steps(
    monkeypatch,
):
    captured = {}

    class Knowledge:
        def retrieve_for_preflight(self, **_kwargs):
            return {"platform": [], "market": [], "content": [], "account": []}

    class Loop:
        def get_preflight(self, preflight_id):
            return {"id": preflight_id, "scores": {"fit": 0.8}, "decision": {"go": True}}

    class OfficialKanban:
        def submit(self, **kwargs):
            captured.update(kwargs)
            return {
                "id": "video-execution-1",
                "root_task_id": "kanban-root-1",
                "tenant": "marketing-video-douyin",
                "workspace_path": "/tmp/marketing-video-douyin",
                "status": "queued",
            }

    monkeypatch.setattr(
        "agent.marketing.workflows.topic_workers.KnowledgeBaseRepository",
        lambda _paths: Knowledge(),
    )
    brief = {
        "candidate_id": "candidate-1",
        "topic": "AI 是泡沫吗",
        "plan_id": "plan-1",
        "preflight_id": "preflight-1",
        "evidence_refs": ["evidence-1"],
        "evidence_pack": [{"id": "evidence-1"}],
        "signal_refs": ["signal-1"],
        "platform_targets": {
            "douyin": {
                "execution_account_id": "acct-anchor",
                "personalization_available": False,
                "binding_status": "public_prior_only_no_linked_account",
            }
        },
        "platform_blueprints": {"douyin": {"aspect_ratio": "9:16"}},
    }
    context = SimpleNamespace(
        workflow={
            "owner_user_id": "default",
            "owner_entity_id": "entity-1",
            "input": {"account_id": "acct-anchor"},
            "steps": [
                {
                    "key": "topic_brief.freeze",
                    "state": "succeeded",
                    "output": {
                        "topic_brief": brief,
                        "lane_orders": {"video": {"douyin": {"plan_id": "video-plan"}}},
                    },
                }
            ],
        },
        step={"input": {"platform": "douyin"}},
        attempt_id="attempt-1",
    )
    worker = object.__new__(TopicProductionWorkers)
    worker.paths = SimpleNamespace()
    worker.loop = Loop()
    worker.video_kanban = OfficialKanban()

    result = worker.submit_official_video(context)

    assert result.output["execution_id"] == "video-execution-1"
    assert result.output["status"] == "queued"
    assert captured["entity_id"] == "entity-1"
    assert captured["context"]["origin_preflight"]["id"] == "preflight-1"
    assert captured["context"]["evidence_refs"] == ["evidence-1"]


def test_unbound_platform_keeps_execution_owner_but_cannot_borrow_personal_model():
    worker = object.__new__(TopicProductionWorkers)
    context = worker._platform_account_context(
        user_id="default",
        account_id="acct-douyin-anchor",
        production_target={
            "binding_status": "public_prior_only_no_linked_account",
            "personalization_available": False,
        },
    )
    knowledge = _knowledge_for_production_target(
        {
            "platform": [{"id": "platform-public"}],
            "market": [{"id": "market-public"}],
            "content": [{"id": "content-public"}],
            "account": [{"id": "douyin-private"}],
        },
        production_target={"personalization_available": False},
    )

    assert context == {
        "account_id": "acct-douyin-anchor",
        "connected": False,
        "personalization_available": False,
        "binding_status": "public_prior_only_no_linked_account",
    }
    assert knowledge["account"] == []
    assert knowledge["platform"] == [{"id": "platform-public"}]


def test_linked_platform_model_is_read_from_target_but_stored_under_compat_owner(
    monkeypatch,
):
    monkeypatch.setattr(
        AccountContextRepository,
        "read",
        lambda self, **kwargs: {
            "account_id": kwargs["account_id"],
            "connected": True,
            "account": {"id": kwargs["account_id"], "platform": "douyin"},
            "lifecycle": {"audience_hypothesis": {"segments": ["创业者"]}},
        },
    )
    worker = object.__new__(TopicProductionWorkers)
    worker.paths = SimpleNamespace()

    context = worker._platform_account_context(
        user_id="default",
        account_id="acct-anchor",
        production_target={
            "account_id": "acct-douyin",
            "binding_status": "linked_platform_account",
            "personalization_available": True,
        },
    )

    assert context["account_id"] == "acct-anchor"
    assert context["connected"] is False
    assert context["target_connected"] is True
    assert context["execution_account_id"] == "acct-anchor"
    assert context["target_account_id"] == "acct-douyin"
    assert context["target_account"]["platform"] == "douyin"
    assert context["lifecycle"]["audience_hypothesis"]["segments"] == ["创业者"]


def test_topic_brief_evidence_projection_keeps_source_content_and_lineage_bounded():
    projection = _evidence_pack_projection(
        [
            {
                "id": "evidence-1",
                "title": "AI infrastructure report",
                "canonical_url": "https://example.com/report",
                "excerpt": "x" * 3000,
                "captured_at": "2026-07-19T00:00:00Z",
                "verification_level": "source_integrity",
                "source_type": "owned_content",
                "provider": "marketing_browser_wechat_official",
            }
        ]
    )

    assert projection[0]["id"] == "evidence-1"
    assert projection[0]["source_url"] == "https://example.com/report"
    assert len(projection[0]["excerpt"]) == 2500
    assert projection[0]["verification_level"] == "source_integrity"
    assert projection[0]["source_type"] == "owned_content"
    assert projection[0]["provider"] == "marketing_browser_wechat_official"


def test_article_writer_projection_restores_deliverable_to_top_level():
    projected = _article_writer_projection(
        {
            "platform": "wechat_official",
            "format": "long_article",
            "title": "标题",
            "hook": "开头",
            "thesis": "观点",
            "deliverable": {"body_markdown": "# 完整正文"},
            "claim_evidence_map": [{"claim": "事实", "evidence_refs": ["evidence-1"]}],
            "visual_brief": {"cover": "对比画面"},
            "adaptation_basis": {"cta": "在看"},
        }
    )

    assert projected["body_markdown"] == "# 完整正文"
    assert "deliverable" not in projected
    assert projected["adaptation_basis"]["cta"] == "在看"


def test_bounded_preflight_projection_keeps_durable_review_contract():
    projected = _bounded_preflight_projection(
        {
            "formula_version": "content-production-preflight-v0.9",
            "prior_mode": "cold_start",
            "preflight_decision": {
                "status": "ready_for_asset_draft",
                "go": True,
                "score": 81.5,
                "confidence": 0.72,
                "blockers": [],
                "warnings": ["account_calibration_pending"],
                "required_next_steps": ["human_review"],
            },
            "prediction_contract": {"immutable": True},
            "draft_features": {"platform_native": True},
            "private_internal_trace": {"must_not_persist": True},
        }
    )

    assert projected["go"] is True
    assert projected["score"] == 81.5
    assert projected["warnings"] == ["account_calibration_pending"]
    assert projected["draft_features"] == {"platform_native": True}
    assert "private_internal_trace" not in projected


def test_lane_order_reads_only_the_general_entry_preflight():
    calls = []

    class Content:
        def save_production_plan(self, **_kwargs):
            return {"plan_id": "lane-plan", "kind": "cross_platform_campaign"}

    class Loop:
        def latest_preflight_for_plan(self, **kwargs):
            calls.append(kwargs)
            return {
                "id": "entry-preflight",
                "decision": {"preflight_decision": {"go": True}},
            }

    worker = object.__new__(TopicProductionWorkers)
    worker.content = Content()
    worker.loop = Loop()
    result = worker._ensure_lane_order(
        lane="article",
        kind="cross_platform_campaign",
        platforms=["wechat_official"],
        brief={
            "topic": "AI 泡沫",
            "angle": "真实需求",
            "plan_id": "source-plan",
            "preflight_id": "source-preflight",
            "evidence_refs": ["evidence-1"],
        },
        user_id="default",
        account_id="acct-1",
        account_context={},
        origin_plan={"audience_model": {"segments": ["创业者"]}},
    )

    assert result["preflight_id"] == "entry-preflight"
    assert calls[0]["formula_version"] == "content-production-preflight-v0.9"
