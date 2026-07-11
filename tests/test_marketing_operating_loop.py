from __future__ import annotations

import json

from agent.marketing.data_paths import MarketingDataPaths
from agent.marketing.domains import (
    ContentAssetRepository,
    ContentProductionPolicy,
    PublishingRepository,
)
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


def _review_ready_asset(tmp_path):
    paths, plan = _saved_plan(tmp_path)
    loop = OperatingLoopRepository(paths)
    preflight = create_content_production_preflight(
        loop,
        {
            "user_id": "default",
            "account_id": "acct-1",
            "session_id": "session-publish",
            "plan_id": plan["plan_id"],
            "plan": plan,
            "evidence_refs": ["evidence_demo"],
        },
    )
    asset_id = "asset-publish-1"
    now = "2026-07-11T00:00:00+00:00"
    content = {
        "_production_plan_id": plan["plan_id"],
        "platform_variants": {
            "zhihu": {"title": "测试文章", "body_markdown": "正文"},
        },
        "feature_snapshot": {"version": "test"},
    }
    with ContentAssetRepository(paths)._transaction() as db:
        db.execute(
            """INSERT INTO content_assets
            (id,user_id,account_id,platform,title,type,status,version,content_json,
             metrics_json,created_at,updated_at)
            VALUES (?,?,?,'multi_article','测试文章','script','review_ready',1,?,'{}',?,?)""",
            (
                asset_id,
                "default",
                "acct-1",
                json.dumps(content, ensure_ascii=False),
                now,
                now,
            ),
        )
    return paths, plan, preflight, asset_id


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
        "attention", "retention", "trust", "action", "account_fit", "sound", "risk"
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


def test_publish_action_prelogs_once_and_binds_native_approval(tmp_path):
    paths, plan, preflight, asset_id = _review_ready_asset(tmp_path)
    publishing = PublishingRepository(paths)

    first = publishing.prepare_action(
        user_id="default",
        account_id="acct-1",
        asset_id=asset_id,
        platform="zhihu",
        provider="playwright_mcp",
        session_id="session-publish",
        tool_call_id="tool-call-1",
    )
    duplicate = publishing.prepare_action(
        user_id="default",
        account_id="acct-1",
        asset_id=asset_id,
        platform="zhihu",
        provider="playwright_mcp",
    )
    executing = publishing.mark_execution_started(
        first["id"], approval_ref="hermes-approval:turn-1:tool-call-1"
    )

    assert first["id"] == duplicate["id"]
    assert first["plan_id"] == plan["plan_id"]
    assert first["preflight_id"] == preflight["preflight_id"]
    assert executing["status"] == "executing"
    assert executing["approval_ref"].startswith("hermes-approval:")
    asset = ContentAssetRepository(paths).get(
        asset_id=asset_id, user_id="default", account_id="acct-1"
    )
    assert asset["status"] == "approved"


def test_publish_success_requires_platform_evidence_and_schedules_metrics(tmp_path):
    paths, _plan, preflight, asset_id = _review_ready_asset(tmp_path)
    publishing = PublishingRepository(paths)
    action = publishing.prepare_action(
        user_id="default",
        account_id="acct-1",
        asset_id=asset_id,
        platform="zhihu",
        provider="playwright_mcp",
    )
    publishing.mark_execution_started(action["id"], approval_ref="approval-once")

    try:
        publishing.settle_action(
            action["id"], outcome="published", provider_result={}
        )
        assert False, "a success without platform evidence must be rejected"
    except ValueError as exc:
        assert "platform_post_id" in str(exc)

    settled = publishing.settle_action(
        action["id"],
        outcome="published",
        provider_result={
            "platform_post_id": "zhihu-post-123",
            "published_url": "https://www.zhihu.com/question/1/answer/2",
        },
        verification_source="creator_center_query",
    )
    checkpoints = publishing.list_metric_checkpoints(action["id"])
    receipt = OperatingLoopRepository(paths).get_receipt(settled["receipt_id"])

    assert settled["status"] == "published"
    assert receipt["summary"]["platform_post_id"] == "zhihu-post-123"
    assert receipt["summary"]["verification_source"] == "creator_center_query"
    assert [item["label"] for item in checkpoints] == ["1h", "6h", "24h", "3d", "7d"]
    assert OperatingLoopRepository(paths).get_preflight(preflight["preflight_id"])["status"] == "settled"
    asset = ContentAssetRepository(paths).get(
        asset_id=asset_id, user_id="default", account_id="acct-1"
    )
    assert asset["status"] == "published"


def test_unknown_publish_is_queryable_and_can_recover_without_retry(tmp_path):
    paths, _plan, _preflight, asset_id = _review_ready_asset(tmp_path)
    publishing = PublishingRepository(paths)
    action = publishing.prepare_action(
        user_id="default",
        account_id="acct-1",
        asset_id=asset_id,
        platform="zhihu",
        provider="playwright_mcp",
    )
    publishing.mark_execution_started(action["id"], approval_ref="approval-once")
    unknown = publishing.settle_action(
        action["id"],
        outcome="unknown",
        provider_result={"failure_code": "provider_disconnected_after_click"},
    )
    unresolved = publishing.list_unresolved_actions(
        user_id="default", account_id="acct-1"
    )
    recovered = publishing.settle_action(
        action["id"],
        outcome="published",
        provider_result={"published_url": "https://www.zhihu.com/p/123456"},
        verification_source="works_list_recovery_query",
    )
    replay = publishing.settle_action(
        action["id"],
        outcome="published",
        provider_result={"published_url": "https://www.zhihu.com/p/123456"},
        verification_source="works_list_recovery_query",
    )

    assert unknown["status"] == "unknown"
    assert [item["id"] for item in unresolved] == [action["id"]]
    assert recovered["status"] == "published"
    assert replay["receipt_id"] == recovered["receipt_id"]
    assert len(publishing.list_metric_checkpoints(action["id"])) == 5
    assert publishing.list_unresolved_actions(account_id="acct-1") == []

    far_future = "2099-01-01T00:00:00+00:00"
    due = publishing.list_due_metric_checkpoints(
        as_of=far_future, user_id="default", account_id="acct-1"
    )
    assert [item["label"] for item in due] == ["1h", "6h", "24h", "3d", "7d"]


def test_publish_rejects_cross_platform_or_homepage_receipts(tmp_path):
    paths, _plan, _preflight, asset_id = _review_ready_asset(tmp_path)
    publishing = PublishingRepository(paths)
    action = publishing.prepare_action(
        user_id="default",
        account_id="acct-1",
        asset_id=asset_id,
        platform="zhihu",
        provider="playwright_mcp",
    )
    publishing.mark_execution_started(action["id"], approval_ref="approval-once")

    for invalid_url in (
        "https://www.douyin.com/video/123",
        "https://www.zhihu.com/",
        "http://www.zhihu.com/p/123",
    ):
        try:
            publishing.settle_action(
                action["id"],
                outcome="published",
                provider_result={"published_url": invalid_url},
                verification_source="query",
            )
            assert False, invalid_url
        except ValueError:
            pass

    try:
        publishing.settle_action(
            action["id"],
            outcome="published",
            provider_result={"platform_post_id": "not a stable id"},
            verification_source="query",
        )
        assert False, "whitespace is not valid inside a stable platform post id"
    except ValueError:
        pass


def test_native_publish_result_seam_settles_provider_envelope(tmp_path, monkeypatch):
    from agent.marketing import publish_capture

    paths, _plan, _preflight, asset_id = _review_ready_asset(tmp_path)
    monkeypatch.setenv("MARKETING_OS_USER_DATA", str(paths.user_data))
    monkeypatch.setenv("MARKETING_OS_CONFIG_DIR", str(paths.config_dir))
    monkeypatch.setenv("MARKETING_OS_AGENT_DB", str(paths.agent_db))
    monkeypatch.setattr(
        publish_capture,
        "read_tool_session_scope",
        lambda **_kwargs: {"user_id": "default", "account_id": "acct-1"},
    )
    publishing = PublishingRepository(paths)
    action = publishing.prepare_action(
        user_id="default",
        account_id="acct-1",
        asset_id=asset_id,
        platform="zhihu",
        provider="playwright_mcp",
    )
    publishing.mark_execution_started(action["id"], approval_ref="approval-once")

    enriched = publish_capture.enrich_tool_result_with_publish_receipt(
        tool_name="marketing_effect_publish",
        args={"action_id": action["id"]},
        result=json.dumps(
            {
                "marketing_publish_result": {
                    "outcome": "published",
                    "platform_post_id": "answer-2",
                    "published_url": "https://www.zhihu.com/question/1/answer/2",
                    "verification_source": "works_list_query",
                }
            }
        ),
        session_id="session-publish",
    )
    payload = json.loads(enriched)

    assert payload["marketing_publish_result"]["receipt_id"]
    assert publishing.get_action(action["id"])["status"] == "published"


def test_native_publish_result_seam_ignores_every_other_tool(tmp_path):
    original = json.dumps(
        {
            "marketing_publish_result": {
                "outcome": "published",
                "platform_post_id": "fabricated",
            }
        }
    )
    from agent.marketing.publish_capture import enrich_tool_result_with_publish_receipt

    assert enrich_tool_result_with_publish_receipt(
        tool_name="web_extract",
        args={"action_id": "anything"},
        result=original,
        session_id="session-publish",
    ) == original


def test_native_publish_effect_reuses_hermes_consent_and_provider(tmp_path, monkeypatch):
    from agent.marketing.providers import (
        clear_publish_providers,
        register_publish_provider,
    )
    from model_tools import handle_function_call

    class FakeProvider:
        name = "playwright_mcp"

        def publish(self, action):
            return {
                "outcome": "published",
                "platform_post_id": "answer-native-1",
                "published_url": "https://www.zhihu.com/question/1/answer/9",
                "verification_source": "fake_works_list_query",
            }

        def query(self, action):
            return {"outcome": "unknown", "failure_code": "not_needed"}

    paths, _plan, _preflight, asset_id = _review_ready_asset(tmp_path)
    monkeypatch.setenv("MARKETING_OS_USER_DATA", str(paths.user_data))
    monkeypatch.setenv("MARKETING_OS_CONFIG_DIR", str(paths.config_dir))
    monkeypatch.setenv("MARKETING_OS_AGENT_DB", str(paths.agent_db))
    monkeypatch.setattr(
        "agent.marketing.session_scope.read_tool_session_scope",
        lambda **_kwargs: {"user_id": "default", "account_id": "acct-1"},
    )
    monkeypatch.setattr(
        "agent.marketing.publish_capture.read_tool_session_scope",
        lambda **_kwargs: {"user_id": "default", "account_id": "acct-1"},
    )
    monkeypatch.setattr(
        "tools.approval.request_elicitation_consent", lambda *_args, **_kwargs: "accept"
    )
    publishing = PublishingRepository(paths)
    action = publishing.prepare_action(
        user_id="default",
        account_id="acct-1",
        asset_id=asset_id,
        platform="zhihu",
        provider="playwright_mcp",
    )
    clear_publish_providers()
    register_publish_provider(FakeProvider())
    try:
        result = json.loads(
            handle_function_call(
                "marketing_effect_publish",
                {"action_id": action["id"]},
                task_id="turn-1",
                session_id="session-publish",
            )
        )
    finally:
        clear_publish_providers()

    assert result["marketing_publish_result"]["receipt_id"]
    assert publishing.get_action(action["id"])["status"] == "published"


def test_native_publish_effect_denial_never_starts_provider(tmp_path, monkeypatch):
    from agent.marketing.providers import (
        clear_publish_providers,
        register_publish_provider,
    )
    from model_tools import handle_function_call

    calls = []

    class FakeProvider:
        name = "playwright_mcp"

        def publish(self, action):
            calls.append(action["id"])
            return {"outcome": "unknown"}

        def query(self, action):
            return {"outcome": "unknown"}

    paths, _plan, _preflight, asset_id = _review_ready_asset(tmp_path)
    monkeypatch.setenv("MARKETING_OS_USER_DATA", str(paths.user_data))
    monkeypatch.setenv("MARKETING_OS_CONFIG_DIR", str(paths.config_dir))
    monkeypatch.setenv("MARKETING_OS_AGENT_DB", str(paths.agent_db))
    monkeypatch.setattr(
        "agent.marketing.session_scope.read_tool_session_scope",
        lambda **_kwargs: {"user_id": "default", "account_id": "acct-1"},
    )
    monkeypatch.setattr(
        "agent.marketing.publish_capture.read_tool_session_scope",
        lambda **_kwargs: {"user_id": "default", "account_id": "acct-1"},
    )
    monkeypatch.setattr(
        "tools.approval.request_elicitation_consent", lambda *_args, **_kwargs: "decline"
    )
    publishing = PublishingRepository(paths)
    action = publishing.prepare_action(
        user_id="default",
        account_id="acct-1",
        asset_id=asset_id,
        platform="zhihu",
        provider="playwright_mcp",
    )
    clear_publish_providers()
    register_publish_provider(FakeProvider())
    try:
        result = json.loads(
            handle_function_call(
                "marketing_effect_publish",
                {"action_id": action["id"]},
                task_id="turn-1",
                session_id="session-publish",
            )
        )
    finally:
        clear_publish_providers()

    assert "not approved" in result["error"]
    assert calls == []
    assert publishing.get_action(action["id"])["status"] == "prepared"


def test_publish_effect_tools_are_hidden_until_real_provider_registers():
    from agent.marketing.providers import (
        clear_publish_providers,
        register_publish_provider,
    )
    from model_tools import get_tool_definitions

    class FakeProvider:
        name = "playwright_mcp"

        def publish(self, action):
            return {"outcome": "unknown"}

        def query(self, action):
            return {"outcome": "unknown"}

    clear_publish_providers()
    before = {
        item["function"]["name"]
        for item in get_tool_definitions(enabled_toolsets=["marketing"], quiet_mode=True)
    }
    register_publish_provider(FakeProvider())
    try:
        after = {
            item["function"]["name"]
            for item in get_tool_definitions(enabled_toolsets=["marketing"], quiet_mode=True)
        }
    finally:
        clear_publish_providers()

    assert "marketing_effect_publish" not in before
    assert "marketing_publish_query" not in before
    assert "marketing_effect_publish" in after
    assert "marketing_publish_query" in after
