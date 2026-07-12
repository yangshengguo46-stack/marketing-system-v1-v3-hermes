from __future__ import annotations

import sqlite3

import pytest

from agent.marketing.data_paths import MarketingDataPaths
from agent.marketing.domains import (
    AccountLifecycleRepository,
    AccountStrategyRepository,
    ContentAssetRepository,
    ContentProductionPolicy,
    EvidenceRepository,
)
from agent.marketing.intelligence import OperatingLoopRepository
from hermes_state import SessionDB


def _repositories(tmp_path):
    state_path = tmp_path / "state.db"
    SessionDB(db_path=state_path).close()
    paths = MarketingDataPaths(tmp_path, tmp_path / "config", state_path)
    return (
        AccountLifecycleRepository(paths),
        AccountStrategyRepository(paths),
        EvidenceRepository(paths),
        paths,
    )


def _profile():
    return {
        "identity": {"role": "AI 实践者"},
        "experiences": ["交付过企业 AI 工作流"],
        "skills": ["把复杂工具讲成任务步骤"],
        "proof_assets": ["项目复盘"],
        "strong_views": ["结果先于概念"],
        "expression_capabilities": {"camera": "willing", "writing": "strong"},
        "production_resources": {"hours_per_week": 6},
        "constraints": ["不编造效果"],
        "taboos": ["夸大收益"],
        "motivations": ["长期专业品牌"],
        "unknowns": ["短视频镜头稳定性"],
        "sustainability": {"weekly_topics": 3},
    }


def _route():
    return {
        "label": "职场 AI 实战",
        "category": "AI 教育",
        "subcategory": "职场效率",
        "target_audience": "需要交付真实工作的职场人",
        "urgent_problem": "看过教程但不会解决自己的任务",
        "content_promise": "每条内容解决一个可复用工作任务",
        "creator_advantage": "有真实交付经验",
        "platform_candidates": ["douyin", "zhihu"],
        "monetization_paths": ["课程", "咨询"],
        "sustainability": {"source": "真实项目"},
        "competition_hypothesis": "市场概念内容多，交付复盘少",
        "risks": ["工具迭代快"],
        "data_gaps": ["细分需求规模"],
    }


def _positioning():
    return {
        "promise": "把一个真实工作任务当场做完",
        "differentiation": "不做工具新闻，只做可复用交付",
        "persona": "讲证据的 AI 实战教练",
        "audience_summary": "需要用 AI 完成真实工作的职场人",
        "proof_mechanism": "屏幕实操、前后对比和失败复盘",
        "content_pillars": ["任务实操", "失败复盘", "工作流拆解"],
        "tone": ["直接", "克制"],
        "taboos": ["虚构案例", "承诺收益"],
        "recurring_formats": ["十分钟完成一个任务"],
        "commercial_path": ["免费模板", "课程", "咨询"],
        "monetization_boundary": {"no_guaranteed_income": True},
    }


def _content_system():
    return {
        "acquisition_lanes": ["高频任务搜索"],
        "trust_lanes": ["真实项目复盘"],
        "action_lanes": ["领取模板并复做"],
        "recurring_series": ["今天替你做完"],
        "platform_expression": {"douyin": "先展示结果", "zhihu": "先给证据"},
        "production_workflow": ["选任务", "采证", "预演", "制作", "复核"],
        "publishing_cadence": {"weekly": 3},
        "measurement_plan": {"primary": "qualified_action_rate"},
        "exploration_policy": {"explore_ratio": 0.25},
        "commercial_boundaries": ["不承诺收入", "利益关系披露"],
    }


def test_full_operating_model_is_versioned_evidence_backed_and_restart_safe(tmp_path):
    lifecycle, strategy, evidence, paths = _repositories(tmp_path)
    project = lifecycle.begin_project(
        user_id="default", account_id="acct-1", business_goal="建立可信的 AI 教育账号"
    )

    profile = strategy.draft_creator_profile(
        user_id="default", account_id="acct-1", project_id=project["id"], profile=_profile()
    )
    strategy.confirm_creator_profile(
        user_id="default", account_id="acct-1", project_id=project["id"],
        profile_id=profile["id"], confirmed_by_user=True,
    )
    route = strategy.draft_market_route(
        user_id="default", account_id="acct-1", project_id=project["id"],
        route=_route(), confidence=0.9,
    )
    assert route["confidence"] == 0.45
    strategy.select_market_route(
        user_id="default", account_id="acct-1", project_id=project["id"],
        route_id=route["id"], confirmed_by_user=True,
    )

    audience = lifecycle.draft_audience_hypothesis(
        user_id="default", account_id="acct-1", project_id=project["id"],
        segments=[{"label": "需要交付的职场人"}],
        pains=["教程无法映射到自己的任务"],
        scenarios=["接到临时汇报"],
        jobs=["更快完成一份可提交成果"],
        current_alternatives=["搜索零散教程"],
        trust_barriers=["案例可能是摆拍"],
        desired_outcomes=["当天复用"],
        behavior_signals=["搜索具体文件类型和任务"],
        exclusions=["只追工具新闻"],
        data_gaps=["付费意愿"],
    )
    lifecycle.confirm_audience_hypothesis(
        user_id="default", account_id="acct-1", project_id=project["id"],
        hypothesis_id=audience["id"], confirmed_by_user=True,
    )

    captured = evidence.capture_web_extract_result(
        user_id="default", account_id="acct-1", session_id="session-1",
        result={"results": [{"url": "https://example.com/benchmark",
                             "title": "Benchmark source", "content": "Observed public posts."}]},
    )
    evidence_id = captured[0]["id"]
    benchmarks = []
    for index, role in enumerate(("direct", "format", "negative"), start=1):
        benchmark = strategy.add_benchmark_account(
                user_id="default", account_id="acct-1", project_id=project["id"],
                platform="douyin", account_handle=f"creator-{index}", role=role,
                selection_reason=f"承担 {role} 对标角色",
                match_dimensions={
                    "audience_overlap": 0.8,
                    "format_fit": 0.7,
                    "creator_resource_fit": 0.6,
                },
                evidence_refs=[evidence_id],
            )
        strategy.decide_benchmark_account(
            user_id="default", account_id="acct-1", project_id=project["id"],
            benchmark_id=benchmark["id"], decision="selected", confirmed_by_user=True,
        )
        benchmarks.append(benchmark)
    for benchmark, dimensions in zip(
        benchmarks,
        (("audience", "positioning"), ("content_pillar", "format"),
         ("engagement", "business_model")),
        strict=True,
    ):
        for dimension in dimensions:
            strategy.add_benchmark_observation(
                user_id="default", account_id="acct-1", project_id=project["id"],
                benchmark_id=benchmark["id"], dimension=dimension,
                value={"observation": f"observed {dimension}"},
                evidence_refs=[evidence_id], confidence=0.7,
            )
    readiness = strategy.benchmark_readiness(
        user_id="default", account_id="acct-1", project_id=project["id"]
    )
    assert readiness["ready"] is True
    assert "score" not in readiness
    assert strategy.get_project(
        user_id="default", account_id="acct-1", project_id=project["id"]
    )["stage"] == "benchmark_graph_ready"

    positioning = strategy.draft_positioning(
        user_id="default", account_id="acct-1", project_id=project["id"],
        positioning=_positioning(),
    )
    strategy.approve_positioning(
        user_id="default", account_id="acct-1", project_id=project["id"],
        positioning_id=positioning["id"], confirmed_by_user=True,
    )
    system = strategy.draft_content_system(
        user_id="default", account_id="acct-1", project_id=project["id"],
        system=_content_system(),
    )
    strategy.approve_content_system(
        user_id="default", account_id="acct-1", project_id=project["id"],
        system_id=system["id"], confirmed_by_user=True,
    )
    experiment = strategy.propose_experiment(
        user_id="default", account_id="acct-1", project_id=project["id"],
        hypothesis="结果先行的开头会提高合格行动率",
        variable={"dimension": "opening_structure"},
        variants=[{"id": "a", "opening": "result_first"},
                  {"id": "b", "opening": "problem_first"}],
        prediction={"winner": "a"},
        success_criteria={"primary_metric": "qualified_action_rate", "minimum_samples": 10},
    )
    duplicate = strategy.propose_experiment(
        user_id="default", account_id="acct-1", project_id=project["id"],
        hypothesis="结果先行的开头会提高合格行动率",
        variable={"dimension": "opening_structure"},
        variants=[{"id": "a", "opening": "result_first"},
                  {"id": "b", "opening": "problem_first"}],
        prediction={"winner": "b"},
        success_criteria={"primary_metric": "qualified_action_rate"},
    )
    assert duplicate["id"] == experiment["id"]
    assert experiment["content_system_id"] == system["id"]
    assert experiment["asset_ids"] == []
    strategy.approve_experiment(
        user_id="default", account_id="acct-1", project_id=project["id"],
        experiment_id=experiment["id"], confirmed_by_user=True,
    )
    plan = ContentProductionPolicy().plan(
        objective="做一条结果先行的 AI 工作流短视频",
        kind="faceless_video",
        platforms=["douyin"],
        audience="需要完成真实工作的职场人",
        evidence_refs=[evidence_id],
        experiment_id=experiment["id"],
        account_context={
            "account_id": "acct-1",
            "connected": True,
            "lifecycle": {
                "positioning_id": positioning["id"],
                "positioning": _positioning(),
                "content_system_id": system["id"],
                "content_system": {"id": system["id"]},
                "strategy_alignment": {
                    "positioning_current": True,
                    "content_system_current": True,
                },
            },
        },
    )
    assets = ContentAssetRepository(paths)
    saved_plan = assets.save_production_plan(
        user_id="default", account_id="acct-1", plan=plan
    )
    asset = assets.create_draft(
        user_id="default", account_id="acct-1", title="AI 工作流实测",
        plan_id=saved_plan["plan_id"], asset_type="video", platform="douyin",
        production_kind="faceless_video", content={"script": "展示结果，再还原步骤"},
        evidence_refs=[evidence_id],
    )
    linked_experiment = strategy.get_experiment(
        user_id="default", account_id="acct-1", project_id=project["id"],
        experiment_id=experiment["id"],
    )
    receipt = OperatingLoopRepository(paths).create_receipt(
        source_kind="test:render", source_id="render-1", receipt_type="render_complete",
        user_id="default", account_id="acct-1", plan_id=saved_plan["plan_id"],
        summary={"outcome": "rendered"},
    )
    assert asset["experiment_id"] == experiment["id"]
    assert asset["id"] in linked_experiment["asset_ids"]
    assert receipt["experiment_id"] == experiment["id"]

    restarted = AccountStrategyRepository(paths).read_operating_model(
        user_id="default", account_id="acct-1", project_id=project["id"]
    )
    assert restarted["project"]["stage"] == "experiment_running"
    assert restarted["creator_profile"]["profile"]["skills"] == ["把复杂工具讲成任务步骤"]
    assert restarted["market_route"]["route"]["category"] == "AI 教育"
    assert restarted["content_system"]["system"]["measurement_plan"]["primary"] == (
        "qualified_action_rate"
    )

    revised_audience = lifecycle.draft_audience_hypothesis(
        user_id="default", account_id="acct-1", project_id=project["id"],
        segments=[{"label": "需要向管理层交付成果的职场人"}],
        jobs=["让管理层更快理解复杂信息"],
    )
    lifecycle.confirm_audience_hypothesis(
        user_id="default", account_id="acct-1", project_id=project["id"],
        hypothesis_id=revised_audience["id"], confirmed_by_user=True,
    )
    stale = strategy.read_operating_model(
        user_id="default", account_id="acct-1", project_id=project["id"]
    )
    assert stale["project"]["stage"] == "experiment_running"
    assert stale["strategy_alignment"]["positioning_current"] is False
    assert f"audience_hypothesis:{revised_audience['id']}" in (
        stale["strategy_alignment"]["stale_basis_refs"]
    )


def test_strategy_enforces_account_scope_and_real_sequence(tmp_path):
    lifecycle, strategy, _evidence, _paths = _repositories(tmp_path)
    project = lifecycle.begin_project(
        user_id="default", account_id="acct-1", business_goal="测试账号"
    )
    with pytest.raises(ValueError, match="selected market route"):
        lifecycle.draft_audience_hypothesis(
            user_id="default", account_id="acct-1", project_id=project["id"],
            segments=[{"label": "任意人群"}],
        )
    with pytest.raises(KeyError, match="account scope"):
        strategy.get_project(
            user_id="default", account_id="acct-2", project_id=project["id"]
        )


def test_sessiondb_reconciles_old_lifecycle_and_benchmark_tables(tmp_path):
    state_path = tmp_path / "state.db"
    db = sqlite3.connect(state_path)
    try:
        db.execute(
            """CREATE TABLE benchmark_accounts (
            id TEXT PRIMARY KEY,user_id TEXT NOT NULL,target_account_id TEXT NOT NULL,
            selection_status TEXT NOT NULL DEFAULT 'candidate')"""
        )
        db.execute(
            """CREATE TABLE audience_hypotheses (
            id TEXT PRIMARY KEY,project_id TEXT NOT NULL,user_id TEXT NOT NULL,
            account_id TEXT NOT NULL,version INTEGER NOT NULL,segments_json TEXT NOT NULL,
            pains_json TEXT NOT NULL,scenarios_json TEXT NOT NULL,exclusions_json TEXT NOT NULL,
            data_gaps_json TEXT NOT NULL,status TEXT NOT NULL,created_at TEXT NOT NULL)"""
        )
        db.execute(
            """CREATE TABLE content_production_plans (
            id TEXT PRIMARY KEY,user_id TEXT NOT NULL,account_id TEXT NOT NULL,
            kind TEXT NOT NULL,objective TEXT NOT NULL,platforms_json TEXT NOT NULL,
            plan_json TEXT NOT NULL,status TEXT NOT NULL,created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL)"""
        )
        db.execute(
            """CREATE TABLE marketing_receipt_refs (
            id TEXT PRIMARY KEY,source_kind TEXT NOT NULL,source_id TEXT NOT NULL,
            receipt_type TEXT NOT NULL,user_id TEXT NOT NULL,account_id TEXT NOT NULL,
            platform TEXT,plan_id TEXT,preflight_id TEXT,session_id TEXT NOT NULL,
            summary_json TEXT NOT NULL,created_at TEXT NOT NULL)"""
        )
        db.commit()
    finally:
        db.close()

    SessionDB(db_path=state_path).close()
    db = sqlite3.connect(state_path)
    try:
        benchmark_columns = {
            row[1] for row in db.execute("PRAGMA table_info(benchmark_accounts)")
        }
        audience_columns = {
            row[1] for row in db.execute("PRAGMA table_info(audience_hypotheses)")
        }
        indexes = {
            row[1] for row in db.execute("PRAGMA index_list(benchmark_accounts)")
        }
        plan_columns = {
            row[1] for row in db.execute("PRAGMA table_info(content_production_plans)")
        }
        receipt_columns = {
            row[1] for row in db.execute("PRAGMA table_info(marketing_receipt_refs)")
        }
    finally:
        db.close()

    assert {"project_id", "role", "match_dimensions_json", "evidence_refs_json"} <= (
        benchmark_columns
    )
    assert {"jobs_json", "trust_barriers_json", "behavior_signals_json"} <= audience_columns
    assert "idx_benchmark_account_scope" in indexes
    assert "experiment_id" in plan_columns
    assert "experiment_id" in receipt_columns
