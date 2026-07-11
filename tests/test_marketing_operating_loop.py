from __future__ import annotations

from agent.marketing.data_paths import MarketingDataPaths
from agent.marketing.domains import ContentAssetRepository, ContentProductionPolicy
from agent.marketing.intelligence import (
    OperatingLoopRepository,
    create_content_production_preflight,
)
from agent.marketing.intelligence.influence_score import build_influence_score
from agent.marketing.intelligence.content_prediction import build_prediction_dimensions
from agent.marketing.intelligence.content_retro import reconcile, retro_to_dict
from agent.marketing.intelligence.content_rubric import OPINION_VIDEO_RUBRIC, score_content
from agent.marketing.intelligence.learning_governance import (
    propose_weight_candidate_from_recent_retros,
    summarize_learning_patterns,
)
from agent.marketing.intelligence.memory_classification import classify_memory
from agent.marketing.intelligence.preflight_decision import build_preflight_decision


def _paths(tmp_path):
    return MarketingDataPaths(
        user_data=tmp_path,
        config_dir=tmp_path / "config",
        agent_db=tmp_path / "agent-runtime" / "agent_core.db",
    )


def _saved_plan(tmp_path):
    paths = _paths(tmp_path)
    plan = ContentProductionPolicy().plan(
        objective="写一篇有证据的 AI 行业分析",
        kind="article_soft",
        platforms=["zhihu"],
        audience="希望提高工作效率的职场人",
        evidence_refs=["evidence_demo"],
        account_context={"account_id": "acct-1", "connected": True},
    )
    saved = ContentAssetRepository(paths).save_production_plan(
        user_id="default", account_id="acct-1", plan=plan
    )
    return paths, saved


def test_influence_formula_keeps_missing_dimensions_explicit():
    result = build_influence_score(
        {"preflight_scores": {"platform_fit": 0.8, "evidence_strength": 0.7}}
    )

    assert result["version"] == "influenceos-score-v0.1"
    assert result["components"]["PlatformReachPotential"]["source"] == "preflight.platform_fit"
    assert "HumanAttentionKernel" in result["missing_dimensions"]
    assert result["confidence"] < 1


def test_preflight_hard_gate_overrides_formula_score():
    score = build_influence_score(
        {
            "preflight_scores": {
                "platform_fit": 0.9,
                "evidence_strength": 0.9,
                "production_feasibility": 0.9,
                "audience_fit": 0.9,
            }
        }
    )
    decision = build_preflight_decision(
        score,
        context={
            "selected_lane": "article_soft",
            "blockers": ["audience_context_missing"],
        },
    )

    assert decision["go"] is False
    assert decision["status"] == "needs_audience_context"


def test_prediction_and_retro_use_the_same_observable_dimensions():
    prediction = build_prediction_dimensions(
        kind="faceless_video",
        confidence="low",
        platforms=["douyin"],
        scores={"hook": 8, "pacing": 6, "viewpoint": 7, "cta": 4},
        evidence_ready=True,
        legacy_metrics={
            "expected_views": {"low": 500, "mid": 2000, "high": 10000},
            "expected_completion_rate": {"low": 0.15, "mid": 0.3, "high": 0.5},
        },
        basis=["content_score"],
    )
    retro = reconcile(
        {
            "expected_views": prediction["dimensions"]["attention"]["range"],
            "expected_completion_rate": prediction["dimensions"]["retention"]["range"],
        },
        {"views": 1200, "completion_rate": 0.2},
    )

    assert set(prediction["dimensions"]) == {
        "attention", "retention", "trust", "action", "account_fit", "risk"
    }
    assert len(retro_to_dict(retro)["accuracies"]) == 2


def test_rubric_and_learning_governance_require_repeated_results():
    scores = {dimension.key: 7 for dimension in OPINION_VIDEO_RUBRIC}
    content_score = score_content(scores)
    proposal = {
        "kind": "published_metric_retro",
        "metric_labels": {
            "labels": {
                "attention": {"bucket": "high"},
                "retention": {"bucket": "low"},
                "action": {"bucket": "zero"},
            }
        },
        "retro": {"bias_direction": "over"},
    }
    one = summarize_learning_patterns(
        [{"id": "one", "status": "pending", "proposal": proposal}]
    )
    repeated = summarize_learning_patterns(
        [
            {"id": f"sample-{index}", "status": "pending", "proposal": proposal}
            for index in range(3)
        ]
    )

    assert content_score.weighted_total >= 0
    assert one["status"] == "insufficient_evidence"
    assert repeated["status"] == "ready"
    assert repeated["top_support_count"] >= 3


def test_memory_classification_is_metadata_not_a_second_memory_store():
    classified = classify_memory(
        "procedural",
        "抖音发布失败后先查询作品列表，再决定是否重试",
        source="failure_recovery",
        account_id="acct-1",
        platform="douyin",
    )

    assert classified.entity == "workflow"
    assert classified.topic == "publishing_workflow"
    assert classified.source == "failure_recovery"


def test_preflight_receipt_and_learning_candidate_are_separate_truths(tmp_path):
    paths, plan = _saved_plan(tmp_path)
    loop = OperatingLoopRepository(paths)
    result = create_content_production_preflight(
        loop,
        {
            "user_id": "default",
            "account_id": "acct-1",
            "session_id": "session-1",
            "plan_id": plan["plan_id"],
            "plan": plan,
            "evidence_refs": ["evidence_demo"],
        },
    )
    preflight = loop.get_preflight(result["preflight_id"])
    original_score = preflight["decision"]["influence_score"]["score"]

    receipt = loop.create_receipt(
        source_kind="publish",
        source_id="douyin-post-1",
        receipt_type="publish_receipt",
        user_id="default",
        account_id="acct-1",
        platform="douyin",
        plan_id=plan["plan_id"],
        preflight_id=preflight["id"],
        summary={"post_id": "douyin-post-1", "views": 1200, "api_key": "must-not-leak"},
    )
    duplicate = loop.create_receipt(
        source_kind="publish",
        source_id="douyin-post-1",
        receipt_type="publish_receipt",
        user_id="default",
        account_id="acct-1",
        platform="douyin",
        plan_id=plan["plan_id"],
        preflight_id=preflight["id"],
        summary={"post_id": "douyin-post-1"},
    )
    candidate = loop.create_learning_candidate(
        candidate_type="strategy",
        user_id="default",
        account_id="acct-1",
        platform="douyin",
        preflight_id=preflight["id"],
        receipt_ids=[receipt["id"]],
        proposal={
            "observation": "预测与现实需要复盘",
            "prediction_score": original_score,
            "actual_views": 1200,
        },
        confidence=0.45,
    )

    assert receipt["id"] == duplicate["id"]
    assert receipt["summary"]["api_key"] == "[REDACTED]"
    assert loop.get_preflight(preflight["id"])["decision"]["influence_score"]["score"] == original_score
    assert candidate["status"] == "pending"
    assert candidate["proposal"]["observation"] == "预测与现实需要复盘"


def test_repeated_receipt_retros_create_weight_candidate_without_applying_it(tmp_path):
    paths, _plan = _saved_plan(tmp_path)
    loop = OperatingLoopRepository(paths)
    proposal = {
        "kind": "published_metric_retro",
        "metric_labels": {
            "labels": {
                "attention": {"bucket": "high"},
                "retention": {"bucket": "low"},
                "action": {"bucket": "zero"},
                "risk": {"bucket": "low"},
            }
        },
        "retro": {"bias_direction": "over"},
        "influence_score": {"score": 46.0},
    }
    for index in range(3):
        loop.create_learning_candidate(
            candidate_type="memory",
            user_id="default",
            account_id="acct-1",
            platform="douyin",
            proposal=proposal,
            evidence_refs=[f"metric-snapshot-{index}"],
            confidence=0.7,
        )

    result = propose_weight_candidate_from_recent_retros(
        loop,
        user_id="default",
        account_id="acct-1",
        platform="douyin",
    )
    candidate = loop.get_learning_candidate(result["weight_candidate_id"])

    assert result["status"] == "candidate_created"
    assert candidate["candidate_type"] == "weight"
    assert candidate["status"] == "pending"
    assert candidate["proposal"]["guardrail"].startswith("pending weight candidate only")
