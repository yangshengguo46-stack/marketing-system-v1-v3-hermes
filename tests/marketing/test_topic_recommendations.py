from __future__ import annotations

import sqlite3

from agent.marketing.data_paths import MarketingDataPaths
from agent.marketing.domains import (
    ContentAssetRepository,
    ContentProductionPolicy,
    EvidenceRepository,
)
from agent.marketing.domains.topic_recommendations import TopicRecommendationRepository
from agent.marketing.intelligence import OperatingLoopRepository
from agent.marketing.intelligence import topic_recommendations as daily
from cron.blueprint_catalog import fill_blueprint, get_blueprint
from cron.product_output_contracts import validate_product_cron_output
from hermes_state import SessionDB


def _paths(tmp_path, monkeypatch) -> MarketingDataPaths:
    config = tmp_path / "config"
    config.mkdir()
    state = tmp_path / "state.db"
    SessionDB(db_path=state).close()
    paths = MarketingDataPaths(tmp_path, config, state)
    monkeypatch.setenv("MARKETING_OS_USER_DATA", str(tmp_path))
    monkeypatch.setenv("MARKETING_OS_CONFIG_DIR", str(config))
    monkeypatch.setenv("MARKETING_OS_AGENT_DB", str(state))
    return paths


def _receipts(paths):
    plan = ContentProductionPolicy().plan(
        objective="AI 是泡沫吗？全平台制作",
        kind="cross_platform_campaign",
        platforms=["douyin", "wechat_official", "youtube"],
        audience="关注 AI 产业的知识工作者",
        evidence_refs=["evidence_verified"],
        account_context={
            "account_id": "acct-main",
            "connected": True,
            "lifecycle": {
                "stage": "operating",
                "audience_hypothesis": {"segments": ["知识工作者"]},
                "positioning": {"promise": "证据化解释 AI"},
                "content_system": {"pillars": ["产业判断"]},
                "strategy_alignment": {
                    "positioning_current": True,
                    "content_system_current": True,
                },
            },
        },
    )
    saved = ContentAssetRepository(paths).save_production_plan(
        user_id="default", account_id="acct-main", plan=plan
    )
    preflight = OperatingLoopRepository(paths).create_preflight(
        user_id="default",
        account_id="acct-main",
        plan_id=saved["plan_id"],
        platform="douyin",
        session_id="cron-first",
        formula_version="test-v1",
        input={},
        scores={"overall": 0.8},
        decision={
            "preflight_decision": {"go": True, "status": "ready_for_asset_draft"}
        },
    )
    return saved, preflight


def _sole_entity_id(paths: MarketingDataPaths) -> str:
    with sqlite3.connect(paths.agent_db) as db:
        rows = db.execute(
            "SELECT id FROM marketing_operating_entities "
            "WHERE user_id='default' AND status='active' ORDER BY id"
        ).fetchall()
    assert len(rows) == 1
    return str(rows[0][0])


def test_platform_targets_bind_real_account_and_label_public_prior_fallback():
    targets = daily._platform_production_targets(
        entity_context={
            "linked_account_contexts": [
                {
                    "account_id": "acct-douyin",
                    "connected": True,
                    "account": {"id": "acct-douyin", "platform": "douyin"},
                },
                {
                    "account_id": "acct-wechat",
                    "connected": True,
                    "account": {
                        "id": "acct-wechat",
                        "platform": "wechat_official",
                    },
                },
            ]
        },
        platforms=["douyin", "wechat_official", "youtube"],
        fallback_account_id="acct-anchor",
    )

    assert targets["douyin"] == {
        "platform": "douyin",
        "account_id": "acct-douyin",
        "execution_account_id": "acct-anchor",
        "binding_status": "linked_platform_account",
        "personalization_available": True,
        "candidate_account_ids": ["acct-douyin"],
    }
    assert targets["youtube"]["account_id"] is None
    assert targets["youtube"]["execution_account_id"] == "acct-anchor"
    assert targets["youtube"]["binding_status"] == (
        "public_prior_only_no_linked_account"
    )
    assert targets["youtube"]["personalization_available"] is False


def test_daily_batch_delivers_only_preflight_go_candidates_and_is_idempotent(
    tmp_path, monkeypatch
):
    paths = _paths(tmp_path, monkeypatch)
    plan, preflight = _receipts(paths)
    blueprints = plan["platform_blueprints"]

    monkeypatch.setattr(
        daily,
        "_preflight_candidates",
        lambda **_kwargs: [
            {
                "rank": 1,
                "topic": "AI 是泡沫吗？",
                "angle": "区分估值、需求与生产率",
                "why_now": "基础设施投入与收入兑现同时进入争议期",
                "audience": "知识工作者",
                "platforms": [],
                "plan_id": plan["plan_id"],
                "preflight_id": preflight["id"],
                "target_platforms": plan["target_platforms"],
                "evidence_refs": ["evidence_verified"],
                "signal_refs": ["signal_today"],
                "decision_status": "ready_for_asset_draft",
                "recommendation_eligible": True,
                "recommendation_type": "general",
                "recommended_platforms": [
                    "douyin",
                    "wechat_official",
                    "youtube",
                ],
                "platform_matches": [
                    {
                        "platform": "douyin",
                        "match_score": 91,
                        "strong_match": True,
                    },
                    {
                        "platform": "wechat_official",
                        "match_score": 86,
                        "strong_match": True,
                    },
                    {
                        "platform": "youtube",
                        "match_score": 81,
                        "strong_match": True,
                    },
                ],
                "influence_score": 72.5,
                "preflight": {
                    "status": "ready_for_asset_draft",
                    "score": 72.5,
                    "primary_reason": "证据和账号匹配通过",
                    "blockers": [],
                    "warnings": [],
                    "next_action": "draft",
                },
                "platform_blueprints": blueprints,
            },
            {
                "rank": 2,
                "topic": "没有证据的热点",
                "angle": "",
                "why_now": "",
                "audience": "",
                "platforms": [],
                "plan_id": plan["plan_id"],
                "preflight_id": preflight["id"],
                "target_platforms": plan["target_platforms"],
                "evidence_refs": [],
                "signal_refs": [],
                "decision_status": "needs_evidence",
                "recommendation_eligible": False,
                "influence_score": 31,
                "preflight": {
                    "status": "needs_evidence",
                    "score": 31,
                    "primary_reason": "缺证据",
                    "blockers": ["url_evidence_missing"],
                    "warnings": [],
                    "next_action": "collect_evidence",
                },
                "platform_blueprints": blueprints,
            },
        ],
    )
    entity_id = _sole_entity_id(paths)
    first = daily.build_daily_topic_recommendation_batch(
        user_id="default",
        entity_id=entity_id,
        account_id="acct-main",
        session_id="cron-first",
        as_of_date="2026-07-17",
        candidates=[{"topic": "a"}, {"topic": "b"}],
        target_platforms=plan["target_platforms"],
        paths=paths,
    )

    assert first["recommended_count"] == 1
    assert first["research_only_count"] == 1
    assert "AI 是泡沫吗？" in first["delivery_text"]
    assert "### 通用选题" in first["delivery_text"]
    assert "平台预演匹配：douyin 91%" in first["delivery_text"]
    assert "没有证据的热点" not in first["delivery_text"]
    assert "douyin" in first["delivery_text"]
    assert "wechat_official" in first["delivery_text"]
    assert "youtube" in first["delivery_text"]

    monkeypatch.setattr(
        daily,
        "_preflight_candidates",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("must reuse daily batch")
        ),
    )
    retried = daily.build_daily_topic_recommendation_batch(
        user_id="default",
        entity_id=entity_id,
        account_id="acct-main",
        session_id="cron-retry",
        as_of_date="2026-07-17",
        candidates=[{"topic": "different retry input"}],
        target_platforms=plan["target_platforms"],
        paths=paths,
    )
    assert retried["id"] == first["id"]
    assert retried["delivery_sha256"] == first["delivery_sha256"]
    # The original batch remains immutable while every retry gets its own
    # delivery receipt, so parallel retries cannot steal each other's proof.
    assert retried["source_session_id"] == "cron-first"
    latest = TopicRecommendationRepository(paths).latest_for_entity(
        user_id="default", entity_id=entity_id
    )
    assert latest is not None
    assert latest["id"] == first["id"]
    approved = TopicRecommendationRepository(paths).get_candidate(
        candidate_id=latest["recommendations"][0]["id"],
        user_id="default",
        entity_id=entity_id,
    )
    assert approved["topic"] == "AI 是泡沫吗？"
    assert approved["recommendation_eligible"] is True
    assert (
        TopicRecommendationRepository(paths).validate_delivery(
            source_session_id="cron-retry", content=retried["delivery_text"]
        )["id"]
        == first["id"]
    )


def test_real_candidate_pipeline_creates_cross_platform_plan_and_preflight(
    tmp_path, monkeypatch
):
    paths = _paths(tmp_path, monkeypatch)
    evidence = EvidenceRepository(paths).capture_web_extract_result(
        user_id="default",
        account_id="acct-main",
        result={
            "results": [
                {
                    "url": "https://example.com/ai-report",
                    "title": "AI infrastructure report",
                    "content": "Evidence about AI infrastructure spending, revenue and adoption.",
                    "error": None,
                }
            ]
        },
        session_id="cron-real",
    )[0]
    context = {
        "user_id": "default",
        "account_id": "acct-main",
        "connected": True,
        "account": {"id": "acct-main", "platform": "douyin"},
        "lifecycle": {
            "stage": "operating",
            "audience_hypothesis": {"segments": ["关注 AI 产业的知识工作者"]},
            "positioning": {"promise": "用证据解释 AI 产业"},
            "content_system": {"pillars": ["产业判断"]},
            "strategy_alignment": {
                "positioning_current": True,
                "content_system_current": True,
            },
        },
        "account_dna": {},
    }
    entity = {
        "id": "entity-main",
        "account_ids": ["acct-main"],
        "platforms": ["douyin", "wechat_official"],
    }
    monkeypatch.setattr(
        daily.OperatingEntityRepository, "get", lambda *_args, **_kwargs: entity
    )
    monkeypatch.setattr(
        daily.AccountContextRepository, "read", lambda *_args, **_kwargs: context
    )
    monkeypatch.setattr(
        daily.AccountContextRepository,
        "read_operating_entity",
        lambda *_args, **_kwargs: {
            "shared_operating_context": context,
            "operating_entity": entity,
        },
    )

    candidates = daily._preflight_candidates(
        user_id="default",
        entity_id="entity-main",
        account_id="acct-main",
        session_id="cron-real",
        candidates=[
            {
                "topic": "当前的 AI 是泡沫吗？",
                "angle": "区分估值、需求和生产率",
                "why_now": "基础设施投入和收入兑现同时进入争议期",
                "audience": "关注 AI 产业的知识工作者",
                "evidence_refs": [evidence["id"]],
                "signal_refs": ["signal_today"],
                "platform_fit_hypotheses": [
                    {
                        "platform": "douyin",
                        "match_score": 96,
                        "rationale": "争议性结论适合短视频开场",
                        "evidence_refs": [evidence["id"]],
                    },
                    {
                        "platform": "wechat_official",
                        "match_score": 90,
                        "rationale": "多层证据适合深度图文",
                        "evidence_refs": [evidence["id"]],
                    },
                    {
                        "platform": "youtube",
                        "match_score": 86,
                        "rationale": "可扩展为长视频论证",
                        "evidence_refs": [evidence["id"]],
                    },
                    {
                        "platform": "instagram",
                        "match_score": 55,
                        "rationale": "纯视觉化表达的证据密度偏弱",
                        "evidence_refs": [evidence["id"]],
                    },
                ],
            }
        ],
        target_platforms=["douyin", "wechat_official", "youtube", "instagram"],
        paths=paths,
    )

    result = candidates[0]
    assert result["recommendation_eligible"] is True
    assert result["influence_score"] >= 58
    assert result["plan_id"].startswith("production_plan_")
    assert result["preflight_id"].startswith("preflight_")
    assert result["recommendation_type"] == "general"
    assert len(result["recommended_platforms"]) >= 2
    assert result["platform_matches"][0]["match_score"] >= 75
    assert result["platform_matches"][-1]["platform"] == "instagram"
    assert set(result["platform_blueprints"]) == {
        "douyin",
        "wechat_official",
        "youtube",
        "instagram",
    }


def test_platform_match_preflight_keeps_one_platform_topic_out_of_general_pool():
    matches = daily._platform_match_scores(
        platforms=["douyin", "xiaohongshu"],
        hypotheses={
            "douyin": {
                "match_score": 100,
                "rationale": "强冲突开场适合短视频",
                "evidence_refs": ["evidence-1"],
            },
            "xiaohongshu": {
                "match_score": 50,
                "rationale": "当前视觉证据不足",
                "evidence_refs": ["evidence-1"],
            },
        },
        preflight={
            "influence_score": {"score": 60},
            "platform_assessments": {
                "douyin": {"fit": 0.8, "guidance_status": "platform_specific"},
                "xiaohongshu": {
                    "fit": 0.8,
                    "guidance_status": "platform_specific",
                },
            },
        },
    )

    assert matches[0]["platform"] == "douyin"
    assert matches[0]["match_score"] == 88
    assert matches[0]["strong_match"] is True
    assert matches[1]["platform"] == "xiaohongshu"
    assert matches[1]["match_score"] == 56
    assert matches[1]["strong_match"] is False
    assert len([item for item in matches if item["strong_match"]]) == 1


def test_product_delivery_contract_rejects_missing_or_rewritten_preflight_output(
    tmp_path, monkeypatch
):
    paths = _paths(tmp_path, monkeypatch)
    plan, preflight = _receipts(paths)
    store = TopicRecommendationRepository(paths)
    entity_id = _sole_entity_id(paths)
    batch = store.start_batch(
        user_id="default",
        entity_id=entity_id,
        account_id="acct-main",
        as_of_date="2026-07-17",
        source_session_id="cron-guarded",
        target_platforms=["douyin"],
        input_summary={},
    )
    completed = store.complete_batch(
        batch_id=batch["id"],
        delivery_text="已通过预演的唯一输出",
        candidates=[
            {
                "rank": 1,
                "topic": "有回执的选题",
                "angle": "",
                "plan_id": plan["plan_id"],
                "preflight_id": preflight["id"],
                "target_platforms": ["douyin"],
                "evidence_refs": ["evidence_verified"],
                "signal_refs": [],
                "decision_status": "ready_for_asset_draft",
                "recommendation_eligible": True,
                "influence_score": 70,
            }
        ],
    )
    job = {
        "product_contract": "marketing.daily_topic_recommendations.v1",
        "marketing_account_id": "acct-main",
    }

    accepted = validate_product_cron_output(
        job=job,
        session_id="cron-guarded",
        content=completed["delivery_text"],
    )
    assert accepted["id"] == batch["id"]

    try:
        validate_product_cron_output(
            job=job,
            session_id="cron-guarded",
            content="模型自己改写过的推荐",
        )
    except ValueError as exc:
        assert "differs" in str(exc)
    else:
        raise AssertionError("rewritten output must fail closed")

    try:
        validate_product_cron_output(
            job=job,
            session_id="cron-without-batch",
            content=completed["delivery_text"],
        )
    except ValueError as exc:
        assert "completed preflight batch" in str(exc)
    else:
        raise AssertionError("missing batch must fail closed")


def test_marketing_daily_blueprint_carries_scope_tools_and_hard_contract():
    spec = fill_blueprint(
        get_blueprint("marketing-daily-topics"),
        {
            "account_id": "acct-main",
            "platforms": "all,instagram,youtube",
            "candidate_count": "5",
            "time": "09:30",
            "deliver": "origin",
        },
    )

    assert spec["schedule"] == "30 9 * * *"
    assert spec["enabled_toolsets"] == ["marketing", "web"]
    assert spec["marketing_account_id"] == "acct-main"
    assert spec["product_contract"] == "marketing.daily_topic_recommendations.v1"
    assert "逐字等于" in spec["prompt"]
    assert "all,instagram,youtube" in spec["prompt"]


def test_gateway_projects_latest_entity_batch_as_a_bounded_topic_inbox(monkeypatch):
    from agent.marketing import session_scope
    from tui_gateway import server

    monkeypatch.setattr(
        session_scope,
        "resolve_account_scope",
        lambda **_kwargs: {
            "account_id": "acct-main",
            "entity_id": "entity-main",
            "platform": "douyin",
            "user_id": "default",
        },
    )
    monkeypatch.setattr(
        TopicRecommendationRepository,
        "latest_for_entity",
        lambda _self, **_kwargs: {
            "id": "topic-batch-1",
            "as_of_date": "2026-07-17",
            "completed_at": "2026-07-17T01:00:00+00:00",
            "recommended_count": 1,
            "research_only_count": 2,
            "target_platforms": ["douyin", "wechat_official", "youtube"],
            "recommendations": [
                {
                    "id": "topic-candidate-1",
                    "rank": 1,
                    "topic": "当前的 AI 是泡沫吗？",
                    "angle": "区分估值、需求与生产率",
                    "plan_id": "plan-1",
                    "preflight_id": "preflight-1",
                    "target_platforms": ["douyin", "wechat_official", "youtube"],
                    "decision_status": "ready_for_asset_draft",
                    "influence_score": 72.5,
                    "candidate": {
                        "why_now": "投入与收入兑现进入争议期",
                        "audience": "知识工作者",
                        "recommendation_type": "general",
                        "recommended_platforms": [
                            "douyin",
                            "wechat_official",
                            "youtube",
                        ],
                        "platform_matches": [
                            {
                                "platform": "douyin",
                                "match_score": 91,
                                "strong_match": True,
                            },
                            {
                                "platform": "wechat_official",
                                "match_score": 86,
                                "strong_match": True,
                            },
                        ],
                        "preflight": {"primary_reason": "证据充分"},
                        "platform_blueprints": {
                            "douyin": {"opening_contract": "前三秒给结论"},
                            "wechat_official": {"opening_contract": "定义争议"},
                            "youtube": {"opening_contract": "问题建立悬念"},
                        },
                    },
                }
            ],
        },
    )

    response = server._methods["marketing.topic_recommendations.latest"](
        "topic-inbox", {"account_id": "acct-main"}
    )

    batch = response["result"]["batch"]
    assert batch["recommended_count"] == 1
    assert batch["research_only_count"] == 2
    assert batch["recommendations"][0]["topic"] == "当前的 AI 是泡沫吗？"
    assert batch["recommendations"][0]["recommendation_type"] == "general"
    assert batch["recommendations"][0]["recommended_platforms"] == [
        "douyin",
        "wechat_official",
        "youtube",
    ]
    assert batch["recommendations"][0]["platform_matches"][0]["match_score"] == 91
    assert set(batch["recommendations"][0]["platform_blueprints"]) == {
        "douyin",
        "wechat_official",
        "youtube",
    }
    assert "delivery_text" not in batch
