from __future__ import annotations

import json

import hermes_state
import pytest

from agent.epistemic_contract import _issue_system_authority
from agent.marketing.data_paths import MarketingDataPaths
from agent.marketing.domains import AccountLifecycleRepository, AccountStrategyRepository
from agent.marketing.domains.public_content_observations import (
    PUBLIC_CONTENT_SCHEMA,
    PublicContentObservationRepository,
    decode_browser_public_content_result,
)
from agent.marketing.evidence_capture import enrich_tool_result_with_evidence
from agent.marketing.learning import SystemLearningProjector
from hermes_state import SessionDB


def _paths(tmp_path):
    state_path = tmp_path / "state.db"
    SessionDB(db_path=state_path).close()
    return MarketingDataPaths(tmp_path, tmp_path / "config", state_path)


def _payload(*, observed_at="2026-07-14T02:00:00+00:00", views=100):
    return {
        "schema": PUBLIC_CONTENT_SCHEMA,
        "platform": "douyin",
        "observed_at": observed_at,
        "items": [
            {
                "source_item_id": "public-video-1",
                "source_url": "https://www.douyin.com/video/public-video-1?from=feed",
                "creator": {
                    "platform_account_id": "creator-88",
                    "handle": "public_creator",
                    "name": "公开创作者",
                    "profile_url": "https://www.douyin.com/user/creator-88",
                },
                "content": {
                    "content_type": "video",
                    "title": "AI 工作流为什么总是失败",
                    "caption": "先展示失败，再拆解人工复核。",
                    "duration_ms": 48_000,
                    "hashtags": ["AI工作流", "复盘"],
                    "sound_id": "sound-1",
                },
                "published_at": "2026-07-14T00:00:00+00:00",
                "feedback": {
                    "metrics": {
                        "views": views,
                        "likes": views // 10,
                        "comments": views // 20,
                        "shares": views // 25,
                    },
                    "visible_comment_count": 8,
                },
                "rank": 2,
            }
        ],
    }


def _model_observation():
    return {
        "content_features": {
            "hook": "先展示失败结果",
            "format": "失败复盘",
            "proof_mechanism": "人工复核前后对比",
            "call_to_action": "分享自己的失败环节",
        },
        "audience": {
            "cohorts": ["正在搭建 AI 工作流的职场人"],
            "jobs": ["降低自动化失控风险"],
            "trust_barriers": ["担心只展示成功案例"],
        },
        "reaction": {
            "sample_size": 8,
            "clusters": [
                {
                    "cohort": "有失败经验的实践者",
                    "stance": "experience_sharing",
                    "need_projection": "belonging",
                    "cognitive_projection": "Fe",
                    "existence_strategy": "confirm",
                    "themes": ["人工复核", "失败成本"],
                    "count": 5,
                },
                {
                    "cohort": "谨慎采用者",
                    "stance": "skeptical",
                    "need_projection": "safety",
                    "cognitive_projection": "Ti",
                    "existence_strategy": "preserve",
                    "themes": ["样本是否充分"],
                    "count": 3,
                },
            ],
            "question_patterns": ["复核需要多久"],
            "objection_patterns": ["没有长期样本"],
        },
        "disconfirming_signals": ["后续同类内容没有经验分享型反馈"],
        "data_gaps": ["不知道是否存在付费流量", "只看到公开可见互动"],
    }


def _benchmark_projection():
    return {
        "suggested_role": "trust",
        "selection_reason": "以失败复盘和边界说明建立信任，可作为信任表达样本",
        "match_dimensions": {
            "audience_overlap": 0.8,
            "format_fit": 0.9,
            "creator_resource_fit": 0.7,
        },
        "observation_dimensions": {
            "hook": {"pattern": "先失败后解释"},
            "trust": {"pattern": "主动展示边界与人工复核"},
            "engagement": {"pattern": "经验分享和成本质疑并存"},
        },
        "disconfirming_signals": ["跨作品观察后该表达没有稳定出现"],
    }


def test_public_content_capture_builds_delayed_feedback_natural_experiment(tmp_path):
    repository = PublicContentObservationRepository(_paths(tmp_path))
    first = repository.capture_browser_result(
        user_id="default",
        account_id="acct-1",
        payload=_payload(),
        session_id="session-1",
    )
    second = repository.capture_browser_result(
        user_id="default",
        account_id="acct-1",
        payload=_payload(observed_at="2026-07-14T08:00:00+00:00", views=250),
        session_id="session-1",
    )

    assert first["captured"][0]["case_id"] == second["captured"][0]["case_id"]
    cases = repository.list_cases(user_id="default", account_id="acct-1")
    assert cases[0]["observation_count"] == 2

    interpreted = repository.interpret_observation(
        user_id="default",
        account_id="acct-1",
        observation_id=second["captured"][0]["observation_id"],
        model_observation=_model_observation(),
        confidence=0.65,
    )
    summary = interpreted["receipt"]["summary"]
    assert summary["metric_delta"]["status"] == "compared"
    assert summary["metric_delta"]["metrics"]["views"] == 150
    assert summary["metric_delta"]["counter_decreases"] == []
    assert summary["model_observation"]["reaction"]["aggregation"] == "anonymous_clusters_only"
    assert summary["model_observation"]["existence_ontology"]["directly_observable"] is False
    assert summary["model_observation"]["reaction"]["clusters"][0][
        "existence_strategy"
    ] == "confirm"
    assert interpreted["model_candidate"]["status"] == "pending"
    assert interpreted["strategy_candidate"] is None

    corrected = repository.capture_browser_result(
        user_id="default",
        account_id="acct-1",
        payload=_payload(observed_at="2026-07-14T10:00:00+00:00", views=240),
        session_id="session-1",
    )
    correction = repository.interpret_observation(
        user_id="default",
        account_id="acct-1",
        observation_id=corrected["captured"][0]["observation_id"],
        model_observation=_model_observation(),
        confidence=0.6,
    )
    corrected_delta = correction["receipt"]["summary"]["metric_delta"]
    assert corrected_delta["metrics"]["views"] == -10
    assert "views" in corrected_delta["counter_decreases"]


def test_public_observation_rejects_raw_comments_and_overconfidence(tmp_path):
    repository = PublicContentObservationRepository(_paths(tmp_path))
    payload = _payload()
    payload["items"][0]["feedback"]["raw_comments"] = [{"user": "x", "text": "y"}]
    with pytest.raises(ValueError, match="raw commenter data"):
        repository.capture_browser_result(
            user_id="default",
            account_id="acct-1",
            payload=payload,
            session_id="session-1",
        )

    captured = repository.capture_browser_result(
        user_id="default",
        account_id="acct-1",
        payload=_payload(),
        session_id="session-1",
    )
    with pytest.raises(ValueError, match="between 0 and 0.7"):
        repository.interpret_observation(
            user_id="default",
            account_id="acct-1",
            observation_id=captured["captured"][0]["observation_id"],
            model_observation=_model_observation(),
            confidence=0.9,
        )


def test_public_learning_projects_only_a_benchmark_candidate_after_acceptance(tmp_path):
    paths = _paths(tmp_path)
    lifecycle = AccountLifecycleRepository(paths)
    strategy = AccountStrategyRepository(paths)
    project = lifecycle.begin_project(
        user_id="default", account_id="acct-1", business_goal="建立可信 AI 实战账号"
    )
    profile = strategy.draft_creator_profile(
        user_id="default",
        account_id="acct-1",
        project_id=project["id"],
        profile={
            "identity": {"role": "AI 实践者"},
            "experiences": ["工作流交付"],
            "skills": ["失败复盘"],
            "proof_assets": ["项目记录"],
            "strong_views": ["不夸大"],
            "expression_capabilities": {},
            "production_resources": {},
            "constraints": [],
            "taboos": [],
            "motivations": ["长期品牌"],
            "unknowns": [],
            "sustainability": {},
        },
    )
    strategy.confirm_creator_profile(
        user_id="default",
        account_id="acct-1",
        project_id=project["id"],
        profile_id=profile["id"],
        confirmed_by_user=True,
    )
    route = strategy.draft_market_route(
        user_id="default",
        account_id="acct-1",
        project_id=project["id"],
        route={
            "label": "AI 实战",
            "category": "AI",
            "subcategory": "工作流",
            "target_audience": "职场实践者",
            "urgent_problem": "自动化失控",
            "content_promise": "展示可复核过程",
            "creator_advantage": "真实交付",
            "platform_candidates": ["douyin"],
            "monetization_paths": ["咨询"],
            "sustainability": {},
            "competition_hypothesis": "成功案例多，失败复盘少",
            "risks": ["样本少"],
            "data_gaps": ["市场规模"],
        },
        confidence=0.4,
    )
    strategy.select_market_route(
        user_id="default",
        account_id="acct-1",
        project_id=project["id"],
        route_id=route["id"],
        confirmed_by_user=True,
    )
    audience = lifecycle.draft_audience_hypothesis(
        user_id="default",
        account_id="acct-1",
        project_id=project["id"],
        segments=["AI 工作流实践者"],
        data_gaps=["付费意愿"],
    )
    lifecycle.confirm_audience_hypothesis(
        user_id="default",
        account_id="acct-1",
        project_id=project["id"],
        hypothesis_id=audience["id"],
        confirmed_by_user=True,
    )
    repository = PublicContentObservationRepository(paths)
    captured = repository.capture_browser_result(
        user_id="default",
        account_id="acct-1",
        payload=_payload(),
        session_id="session-1",
    )
    interpreted = repository.interpret_observation(
        user_id="default",
        account_id="acct-1",
        observation_id=captured["captured"][0]["observation_id"],
        model_observation=_model_observation(),
        confidence=0.65,
        project_id=project["id"],
        benchmark_projection=_benchmark_projection(),
    )

    projected = SystemLearningProjector(
        paths,
        authority=_issue_system_authority("test_public_content_observations"),
    ).accept_and_project(
        interpreted["strategy_candidate"]["id"], reason="确认作为公域信任表达候选"
    )
    benchmark = projected["account_strategy"]["benchmark"]
    assert benchmark["selection_status"] == "candidate"
    assert benchmark["role"] == "trust"
    assert benchmark["metadata"]["source_learning_candidate_id"] == interpreted["strategy_candidate"]["id"]
    assert len(projected["account_strategy"]["observations"]) == 3


def test_public_browser_result_is_captured_by_native_post_tool_seam(tmp_path, monkeypatch):
    paths = _paths(tmp_path)
    monkeypatch.setenv("MARKETING_OS_AGENT_DB", str(paths.agent_db))
    monkeypatch.setenv("MARKETING_OS_USER_DATA", str(tmp_path))
    monkeypatch.setenv("MARKETING_OS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setattr(hermes_state, "DEFAULT_DB_PATH", paths.agent_db)
    owner = SessionDB(db_path=paths.agent_db)
    owner.create_session(
        "session-1",
        "tui",
        marketing_user_id="default",
        marketing_account_id="acct-1",
    )
    owner.close()
    wrapped = "Marketing public content observations\n" + json.dumps(_payload())
    assert decode_browser_public_content_result(wrapped)["schema"] == PUBLIC_CONTENT_SCHEMA

    result = enrich_tool_result_with_evidence(
        tool_name="mcp_marketing_browser_browser_capture_public_content",
        args={},
        result=wrapped,
        task_id="session-1",
        session_id="session-1",
        tool_call_id="browser-call-1",
    )

    assert "Marketing OS public natural-experiment capture" in result
    cases = PublicContentObservationRepository(paths).list_cases(
        user_id="default", account_id="acct-1"
    )
    assert len(cases) == 1
