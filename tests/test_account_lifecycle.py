import sqlite3

import pytest

from agent_core import AccountLifecycleService, AgentCoreStore
from agent_core.migrations import get_migration_status


def service(tmp_path):
    return AccountLifecycleService(AgentCoreStore(tmp_path / "core.db"))


def test_lifecycle_schema_and_version(tmp_path):
    db_path = tmp_path / "core.db"
    AgentCoreStore(db_path)
    from agent_core.migrations import MIGRATIONS
    assert get_migration_status(db_path)["version"] == MIGRATIONS[-1].version
    with sqlite3.connect(db_path) as db:
        names = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"account_strategy_projects", "audience_hypotheses", "audience_snapshots",
                "positioning_versions", "account_experiments", "strategy_candidates",
                "benchmark_observations"} <= names
        columns = {row[1] for row in db.execute("PRAGMA table_info(benchmark_accounts)")}
        assert {"project_id", "target_account_id", "relation", "selection_reason", "source_ref"} <= columns


def test_project_is_account_scoped_and_only_one_active(tmp_path):
    lifecycle = service(tmp_path)
    first = lifecycle.create_project(user_id="u1", account_id="a1", business_goal="获客")
    lifecycle.create_project(user_id="u1", account_id="a2", business_goal="品牌")
    with pytest.raises(ValueError, match="active strategy"):
        lifecycle.create_project(user_id="u1", account_id="a1", business_goal="重复")
    with pytest.raises(KeyError):
        lifecycle.get_project(user_id="u1", account_id="a2", project_id=first["id"])
    with pytest.raises(KeyError):
        lifecycle.get_project(user_id="u2", account_id="a1", project_id=first["id"])


def test_read_unstarted_account_has_no_write_side_effect(tmp_path):
    lifecycle = service(tmp_path)
    status = lifecycle.read_account_status(user_id="u", account_id="empty")
    assert status["stage"] == "not_started"
    assert status["next_action"] == "draft_audience_hypothesis"
    assert lifecycle.get_active_project(user_id="u", account_id="empty") is None


def test_prospect_project_binding_moves_scoped_lifecycle_atomically(tmp_path):
    lifecycle = service(tmp_path)
    prospect = "prospect_u"
    project = lifecycle.create_project(
        user_id="u", account_id=prospect, business_goal="找到适合长期经营的方向",
    )
    draft = lifecycle.draft_audience_hypothesis(
        user_id="u", account_id=prospect, project_id=project["id"],
        segments=[{"label": "刚开始做内容的普通人"}],
    )
    lifecycle.confirm_audience_hypothesis(
        user_id="u", account_id=prospect, project_id=project["id"], hypothesis_id=draft["id"],
    )
    benchmark = lifecycle.add_benchmark_account(
        user_id="u", account_id=prospect, project_id=project["id"], platform="douyin",
        account_handle="peer", account_name="参考账号", relation="direct",
        selection_reason="相同起步条件", source_ref="https://example.com/peer",
    )
    observation = lifecycle.add_benchmark_observation(
        user_id="u", account_id=prospect, project_id=project["id"],
        benchmark_account_id=benchmark["id"], dimension="audience",
        value={"finding": "普通人起号"}, provenance={
            "source_kind": "public_web", "source_ref": "https://example.com/peer/videos",
            "captured_at": "2026-07-04T10:00:00Z",
        }, confidence=0.8,
    )

    result = lifecycle.bind_prospect_project(
        user_id="u", prospect_account_id=prospect,
        target_account_id="acct_real", project_id=project["id"],
    )

    assert result["status"] == "bound"
    assert result["lifecycle"]["audience_hypothesis"]["id"] == draft["id"]
    assert lifecycle.get_active_project(user_id="u", account_id=prospect) is None
    assert lifecycle.get_active_project(user_id="u", account_id="acct_real")["id"] == project["id"]
    assert lifecycle.get_benchmark_observation(
        user_id="u", account_id="acct_real", project_id=project["id"],
        observation_id=observation["id"],
    )["id"] == observation["id"]
    with pytest.raises(KeyError):
        lifecycle.get_benchmark_account(
            user_id="u", account_id=prospect, project_id=project["id"],
            benchmark_account_id=benchmark["id"],
        )


def test_prospect_project_binding_is_idempotent_by_project_id(tmp_path):
    lifecycle = service(tmp_path)
    project = lifecycle.create_project(user_id="u", account_id="prospect_u", business_goal="起号")
    first = lifecycle.bind_prospect_project(
        user_id="u", prospect_account_id="prospect_u",
        target_account_id="acct_real", project_id=project["id"],
    )
    retry = lifecycle.bind_prospect_project(
        user_id="u", prospect_account_id="prospect_u",
        target_account_id="acct_real", project_id=project["id"],
    )
    assert first["status"] == "bound"
    assert retry["status"] == "already_bound"
    assert retry["project_id"] == project["id"]


def test_prospect_project_binding_refuses_target_conflict_without_partial_move(tmp_path):
    lifecycle = service(tmp_path)
    prospect = lifecycle.create_project(
        user_id="u", account_id="prospect_u", business_goal="探索方向",
    )
    lifecycle.create_project(user_id="u", account_id="acct_real", business_goal="已有定位")
    with pytest.raises(ValueError, match="explicit merge"):
        lifecycle.bind_prospect_project(
            user_id="u", prospect_account_id="prospect_u",
            target_account_id="acct_real", project_id=prospect["id"],
        )
    assert lifecycle.get_active_project(user_id="u", account_id="prospect_u")["id"] == prospect["id"]


def test_prospect_project_binding_rejects_non_prospect_source(tmp_path):
    lifecycle = service(tmp_path)
    project = lifecycle.create_project(user_id="u", account_id="acct_a", business_goal="起号")
    with pytest.raises(ValueError, match="prospect workspace"):
        lifecycle.bind_prospect_project(
            user_id="u", prospect_account_id="acct_a",
            target_account_id="acct_b", project_id=project["id"],
        )


def test_audience_versions_are_immutable_and_status_advances(tmp_path):
    lifecycle = service(tmp_path)
    project = lifecycle.create_project(user_id="u1", account_id="a1", business_goal="找到首批客户")
    initial = lifecycle.read_status(user_id="u1", account_id="a1", project_id=project["id"])
    assert initial["next_action"] == "draft_audience_hypothesis"

    v1 = lifecycle.draft_audience_hypothesis(
        user_id="u1", account_id="a1", project_id=project["id"],
        segments=[{"label": "小微企业主"}], pains=["没有稳定获客"],
        data_gaps=["occupation_unavailable"],
    )
    assert v1["version"] == 1 and v1["status"] == "draft"
    assert lifecycle.read_status(user_id="u1", account_id="a1", project_id=project["id"])["stage"] == "goal_defined"
    lifecycle.confirm_audience_hypothesis(
        user_id="u1", account_id="a1", project_id=project["id"], hypothesis_id=v1["id"]
    )
    status = lifecycle.read_status(user_id="u1", account_id="a1", project_id=project["id"])
    assert status["stage"] == "audience_hypothesis_ready"
    assert status["data_gaps"] == ["occupation_unavailable"]

    v2 = lifecycle.draft_audience_hypothesis(
        user_id="u1", account_id="a1", project_id=project["id"],
        segments=[{"label": "本地门店老板"}],
    )
    assert v2["version"] == 2
    confirmed_v1 = lifecycle._get_hypothesis("u1", "a1", project["id"], v1["id"])
    assert confirmed_v1["segments"] == [{"label": "小微企业主"}]
    lifecycle.confirm_audience_hypothesis(
        user_id="u1", account_id="a1", project_id=project["id"], hypothesis_id=v2["id"]
    )
    assert lifecycle._get_hypothesis("u1", "a1", project["id"], v1["id"])["status"] == "superseded"


def test_hypothesis_cannot_cross_account_scope(tmp_path):
    lifecycle = service(tmp_path)
    p1 = lifecycle.create_project(user_id="u", account_id="a1", business_goal="g1")
    lifecycle.create_project(user_id="u", account_id="a2", business_goal="g2")
    draft = lifecycle.draft_audience_hypothesis(
        user_id="u", account_id="a1", project_id=p1["id"], segments=[{"label": "x"}]
    )
    with pytest.raises(KeyError):
        lifecycle.confirm_audience_hypothesis(
            user_id="u", account_id="a2", project_id=p1["id"], hypothesis_id=draft["id"]
        )


def test_restart_preserves_stage_and_next_action(tmp_path):
    db_path = tmp_path / "core.db"
    first = AccountLifecycleService(AgentCoreStore(db_path))
    project = first.create_project(user_id="u", account_id="a", business_goal="长期经营")
    draft = first.draft_audience_hypothesis(
        user_id="u", account_id="a", project_id=project["id"], segments=[{"label": "创作者"}]
    )
    first.confirm_audience_hypothesis(
        user_id="u", account_id="a", project_id=project["id"], hypothesis_id=draft["id"]
    )
    second = AccountLifecycleService(AgentCoreStore(db_path))
    status = second.read_status(user_id="u", account_id="a", project_id=project["id"])
    assert status["stage"] == "audience_hypothesis_ready"
    assert status["next_action"] == "research_benchmark_accounts"


def test_upgrade_columns_preserve_existing_benchmark_data(tmp_path):
    db_path = tmp_path / "core.db"
    store = AgentCoreStore(db_path)
    legacy = store.add_benchmark_account(
        user_id="legacy-user", platform="douyin", account_handle="legacy-handle",
        account_name="历史对标账号", metadata={"reason": "old-data"},
    )
    reopened = AgentCoreStore(db_path)
    restored = reopened.get_benchmark_account(legacy["id"])
    assert restored["account_name"] == "历史对标账号"
    assert restored["metadata"] == {"reason": "old-data"}
    assert restored["project_id"] is None
    assert restored["target_account_id"] is None


def test_scoped_benchmark_requires_evidence_before_stage_advances(tmp_path):
    lifecycle = service(tmp_path)
    project = lifecycle.create_project(user_id="u", account_id="target", business_goal="获客")
    draft = lifecycle.draft_audience_hypothesis(
        user_id="u", account_id="target", project_id=project["id"],
        segments=[{"label": "本地商家"}],
    )
    lifecycle.confirm_audience_hypothesis(
        user_id="u", account_id="target", project_id=project["id"], hypothesis_id=draft["id"],
    )
    benchmark = lifecycle.add_benchmark_account(
        user_id="u", account_id="target", project_id=project["id"],
        platform="douyin", account_handle="peer-1", account_name="同类账号",
        relation="direct", selection_reason="同地区同客群", source_ref="https://example.com/peer-1",
    )
    status = lifecycle.read_status(user_id="u", account_id="target", project_id=project["id"])
    assert status["benchmark_count"] == 1
    assert status["benchmark_observation_count"] == 0
    assert status["next_action"] == "complete_benchmark_evidence"

    observation = lifecycle.add_benchmark_observation(
        user_id="u", account_id="target", project_id=project["id"],
        benchmark_account_id=benchmark["id"], dimension="content_pillar",
        value={"label": "门店获客案例", "sample_size": 12},
        provenance={
            "source_kind": "public_web", "source_ref": "https://example.com/peer-1/videos",
            "captured_at": "2026-07-03T10:00:00Z", "data_gaps": ["conversion_unavailable"],
        }, confidence=0.8,
    )
    assert observation["value"]["sample_size"] == 12
    status = lifecycle.read_status(user_id="u", account_id="target", project_id=project["id"])
    assert status["stage"] == "audience_hypothesis_ready"
    assert status["next_action"] == "complete_benchmark_evidence"
    assert set(status["benchmark_readiness"]["missing"]) >= {
        "selected_accounts", "sample_depth", "dimension_coverage", "negative_benchmark",
    }


def test_benchmark_readiness_requires_depth_coverage_and_negative_example(tmp_path):
    lifecycle = service(tmp_path)
    project = lifecycle.create_project(user_id="u", account_id="target", business_goal="获客")
    draft = lifecycle.draft_audience_hypothesis(
        user_id="u", account_id="target", project_id=project["id"],
        segments=[{"label": "本地商家"}],
    )
    lifecycle.confirm_audience_hypothesis(
        user_id="u", account_id="target", project_id=project["id"], hypothesis_id=draft["id"],
    )
    benchmarks = []
    for handle, relation in (("good-peer", "direct"), ("avoid-peer", "negative")):
        benchmark = lifecycle.add_benchmark_account(
            user_id="u", account_id="target", project_id=project["id"], platform="douyin",
            account_handle=handle, account_name=handle, relation=relation,
            selection_reason="正反例校准", source_ref=f"https://example.com/{handle}",
        )
        benchmarks.append(benchmark)
        for index in range(5):
            lifecycle.add_benchmark_sample(
                user_id="u", account_id="target", project_id=project["id"],
                benchmark_account_id=benchmark["id"], video_id=f"{handle}-{index}",
                title=f"样本 {index}", transcript=None, metrics={}, provenance={
                    "source_kind": "public_web",
                    "source_ref": f"https://example.com/{handle}/{index}",
                    "captured_at": "2026-07-03T12:00:00Z",
                },
            )
    for dimension in ("audience", "positioning", "content_pillar", "format", "engagement"):
        lifecycle.add_benchmark_observation(
            user_id="u", account_id="target", project_id=project["id"],
            benchmark_account_id=benchmarks[0]["id"], dimension=dimension,
            value={"finding": dimension}, provenance={
                "source_kind": "public_web", "source_ref": f"https://example.com/evidence/{dimension}",
                "captured_at": "2026-07-03T12:00:00Z",
            }, confidence=0.8,
        )
    status = lifecycle.read_status(user_id="u", account_id="target", project_id=project["id"])
    assert status["benchmark_readiness"]["ready"] is True
    assert status["stage"] == "benchmark_evidence_ready"
    assert status["next_action"] == "draft_account_positioning"


def test_benchmark_and_observation_cannot_cross_account_scope(tmp_path):
    lifecycle = service(tmp_path)
    p1 = lifecycle.create_project(user_id="u", account_id="a1", business_goal="g1")
    lifecycle.create_project(user_id="u", account_id="a2", business_goal="g2")
    benchmark = lifecycle.add_benchmark_account(
        user_id="u", account_id="a1", project_id=p1["id"], platform="douyin",
        account_handle="peer", account_name=None, relation="negative",
        selection_reason="明确不做的方向", source_ref="user://selected",
    )
    with pytest.raises(KeyError):
        lifecycle.get_benchmark_account(
            user_id="u", account_id="a2", project_id=p1["id"],
            benchmark_account_id=benchmark["id"],
        )
    with pytest.raises(ValueError, match="provenance"):
        lifecycle.add_benchmark_observation(
            user_id="u", account_id="a1", project_id=p1["id"],
            benchmark_account_id=benchmark["id"], dimension="audience",
            value={"claim": "年轻人"}, provenance={"source_kind": "model_inference"},
            confidence=0.2,
        )


def test_candidate_benchmark_cannot_be_evidence_until_selected(tmp_path):
    lifecycle = service(tmp_path)
    project = lifecycle.create_project(user_id="u", account_id="a", business_goal="g")
    candidate = lifecycle.add_benchmark_account(
        user_id="u", account_id="a", project_id=project["id"], platform="douyin",
        account_handle="candidate", account_name=None, relation="adjacent",
        selection_reason="候选客群相近", source_ref="https://example.com/candidate",
        selection_status="candidate",
    )
    provenance = {
        "source_kind": "public_web", "source_ref": "https://example.com/candidate/videos",
        "captured_at": "2026-07-03T12:00:00Z",
    }
    sample = lifecycle.add_benchmark_sample(
        user_id="u", account_id="a", project_id=project["id"],
        benchmark_account_id=candidate["id"], video_id="candidate-video",
        title="候选阶段的可追溯样本", transcript=None, metrics={"views": 100},
        provenance=provenance,
    )
    assert sample["benchmark_account_id"] == candidate["id"]
    with pytest.raises(ValueError, match="must be selected"):
        lifecycle.add_benchmark_observation(
            user_id="u", account_id="a", project_id=project["id"],
            benchmark_account_id=candidate["id"], dimension="format",
            value={"format": "口播"}, provenance=provenance, confidence=0.6,
        )
    selected = lifecycle.decide_benchmark_account(
        user_id="u", account_id="a", project_id=project["id"],
        benchmark_account_id=candidate["id"], decision="selected", relation="negative",
    )
    assert selected["selection_status"] == "selected"
    assert selected["relation"] == "negative"
    with pytest.raises(ValueError, match="only be changed when selecting"):
        lifecycle.decide_benchmark_account(
            user_id="u", account_id="a", project_id=project["id"],
            benchmark_account_id=candidate["id"], decision="rejected", relation="direct",
        )


def _make_positioning_ready(lifecycle):
    project = lifecycle.create_project(user_id="u", account_id="a", business_goal="稳定获客")
    audience = lifecycle.draft_audience_hypothesis(
        user_id="u", account_id="a", project_id=project["id"],
        segments=[{
            "label": "本地门店经营者",
            "dimensions": {
                "age": {"31-40": 0.6, "24-30": 0.4},
                "interests": {"门店经营": 0.7, "短视频获客": 0.3},
            },
        }],
    )
    lifecycle.confirm_audience_hypothesis(
        user_id="u", account_id="a", project_id=project["id"], hypothesis_id=audience["id"],
    )
    benchmarks = []
    for handle, relation in (("good", "direct"), ("bad", "negative")):
        benchmark = lifecycle.add_benchmark_account(
            user_id="u", account_id="a", project_id=project["id"], platform="douyin",
            account_handle=handle, account_name=handle, relation=relation,
            selection_reason="正反校准", source_ref=f"https://example.com/{handle}",
        )
        benchmarks.append(benchmark)
        for index in range(5):
            lifecycle.add_benchmark_sample(
                user_id="u", account_id="a", project_id=project["id"],
                benchmark_account_id=benchmark["id"], video_id=f"{handle}-{index}",
                title=f"sample-{index}", transcript=None, metrics={}, provenance={
                    "source_kind": "public_web", "source_ref": f"https://example.com/{handle}/{index}",
                    "captured_at": "2026-07-03T12:00:00Z",
                },
            )
    observations = []
    for dimension in ("audience", "positioning", "content_pillar", "format", "engagement"):
        observations.append(lifecycle.add_benchmark_observation(
            user_id="u", account_id="a", project_id=project["id"],
            benchmark_account_id=benchmarks[0]["id"], dimension=dimension,
            value={"finding": dimension}, provenance={
                "source_kind": "public_web", "source_ref": f"https://example.com/e/{dimension}",
                "captured_at": "2026-07-03T12:00:00Z",
            }, confidence=0.8,
        ))
    return project, observations


def test_positioning_is_versioned_approved_projected_and_rolled_back(tmp_path):
    lifecycle = service(tmp_path)
    project, observations = _make_positioning_ready(lifecycle)
    base = {
        "promise": "帮助本地门店用短视频稳定获客",
        "differentiation": "只讲可复盘的真实门店案例",
        "persona": "懂经营的实战顾问",
        "audience_summary": "缺少稳定内容获客能力的本地门店经营者",
        "content_pillars": ["案例拆解", "经营避坑", "工具实操"],
        "tone": ["直接", "务实"], "taboos": ["虚构收益", "制造焦虑"],
    }
    v1 = lifecycle.draft_positioning(
        user_id="u", account_id="a", project_id=project["id"], positioning=base,
        evidence_refs=[item["id"] for item in observations],
    )
    assert v1["version"] == 1 and v1["status"] == "draft"
    assert v1["positioning"]["audience_hypothesis_id"]
    lifecycle.approve_positioning(
        user_id="u", account_id="a", project_id=project["id"], positioning_id=v1["id"],
    )
    dna = lifecycle.account_dna_projection(user_id="u", account_id="a", project_id=project["id"])
    assert dna["persona"] == "懂经营的实战顾问"
    assert dna["positioning_version"] == 1
    assert lifecycle.read_status(user_id="u", account_id="a", project_id=project["id"])["stage"] == "positioning_approved"

    changed = {**base, "persona": "本地生意增长陪练"}
    v2 = lifecycle.draft_positioning(
        user_id="u", account_id="a", project_id=project["id"], positioning=changed,
        evidence_refs=[item["id"] for item in observations],
    )
    lifecycle.approve_positioning(
        user_id="u", account_id="a", project_id=project["id"], positioning_id=v2["id"],
    )
    rolled = lifecycle.rollback_positioning(
        user_id="u", account_id="a", project_id=project["id"], target_positioning_id=v1["id"],
    )
    assert rolled["version"] == 3
    assert rolled["positioning"]["rollback_of"] == v1["id"]
    assert lifecycle.account_dna_projection(
        user_id="u", account_id="a", project_id=project["id"]
    )["persona"] == "懂经营的实战顾问"


def test_positioning_rejects_out_of_scope_evidence(tmp_path):
    lifecycle = service(tmp_path)
    project, _ = _make_positioning_ready(lifecycle)
    with pytest.raises(ValueError, match="out-of-scope"):
        lifecycle.draft_positioning(
            user_id="u", account_id="a", project_id=project["id"],
            positioning={
                "promise": "p", "differentiation": "d", "persona": "x",
                "content_pillars": [], "tone": [], "taboos": [],
            }, evidence_refs=["foreign-observation"],
        )


def test_actual_audience_snapshots_require_first_party_provenance_and_preserve_history(tmp_path):
    lifecycle = service(tmp_path)
    project = lifecycle.create_project(user_id="u", account_id="a", business_goal="了解真实受众")
    with pytest.raises(ValueError, match="official_api or creator_center_mcp"):
        lifecycle.add_audience_snapshot(
            user_id="u", account_id="a", project_id=project["id"], platform="douyin",
            dimensions={"age": {"18-23": 0.4}}, provenance={
                "source_kind": "model_inference", "source_ref": "model://guess",
                "captured_at": "2026-07-03T10:00:00Z",
            },
        )
    first = lifecycle.add_audience_snapshot(
        user_id="u", account_id="a", project_id=project["id"], platform="douyin",
        dimensions={
            "gender": {"female": 0.62, "male": 0.38},
            "age": {"24-30": 0.46, "31-40": 0.31},
            "region": [{"name": "广东", "ratio": 0.28}],
        }, provenance={
            "source_kind": "official_api", "source_ref": "douyin:fans.data",
            "captured_at": "2026-07-03T11:00:00Z",
            "data_gaps": ["occupation_unavailable", "income_unavailable"],
        }, window_start="2026-06-01T00:00:00Z", window_end="2026-06-30T23:59:59Z",
    )
    second = lifecycle.add_audience_snapshot(
        user_id="u", account_id="a", project_id=project["id"], platform="douyin",
        dimensions={"gender": {"female": 0.60, "male": 0.40}}, provenance={
            "source_kind": "creator_center_mcp", "source_ref": "creator-center://audience",
            "captured_at": "2026-07-03T12:00:00Z", "data_gaps": ["occupation_unavailable"],
        },
    )
    snapshots = lifecycle.list_audience_snapshots(
        user_id="u", account_id="a", project_id=project["id"], platform="douyin",
    )
    assert [item["id"] for item in snapshots] == [second["id"], first["id"]]
    assert snapshots[1]["provenance"]["data_gaps"] == [
        "occupation_unavailable", "income_unavailable",
    ]


def test_actual_audience_snapshot_rejects_unsupported_occupation_claim(tmp_path):
    lifecycle = service(tmp_path)
    project = lifecycle.create_project(user_id="u", account_id="a", business_goal="g")
    with pytest.raises(ValueError, match="unsupported actual audience dimensions"):
        lifecycle.add_audience_snapshot(
            user_id="u", account_id="a", project_id=project["id"], platform="douyin",
            dimensions={"occupation": {"老板": 0.9}}, provenance={
                "source_kind": "official_api", "source_ref": "douyin:fans.data",
                "captured_at": "2026-07-03T12:00:00Z",
            },
        )


def test_content_experiment_links_asset_prediction_publish_and_retro(tmp_path):
    store = AgentCoreStore(tmp_path / "core.db")
    lifecycle = AccountLifecycleService(store)
    project, observations = _make_positioning_ready(lifecycle)
    positioning = lifecycle.draft_positioning(
        user_id="u", account_id="a", project_id=project["id"], positioning={
            "promise": "帮助门店稳定获客", "differentiation": "真实案例",
            "persona": "经营陪练", "content_pillars": ["案例"],
            "tone": ["务实"], "taboos": ["虚构收益"],
        }, evidence_refs=[item["id"] for item in observations],
    )
    lifecycle.approve_positioning(
        user_id="u", account_id="a", project_id=project["id"],
        positioning_id=positioning["id"],
    )
    experiment = lifecycle.create_experiment(
        user_id="u", account_id="a", project_id=project["id"],
        hypothesis="真实门店案例比泛行业观点带来更多有效互动",
        variable={"content_pillar": "案例拆解"},
        prediction={"engagement_rate": {"low": 0.03, "mid": 0.06, "high": 0.1}},
        success_criteria={"engagement_rate_gte": 0.05},
    )
    asset = store.create_content_asset(
        user_id="u", account_id="a", platform="douyin", title="一家门店如何修复获客",
    )
    linked = lifecycle.attach_experiment_asset(
        user_id="u", account_id="a", project_id=project["id"],
        experiment_id=experiment["id"], asset_id=asset["id"],
    )
    assert linked["status"] == "running"
    assert store.get_content_asset(asset["id"])["experiment_id"] == experiment["id"]

    scores = {
        "hook": 8, "topic": 7, "emotion": 7, "density": 8, "pacing": 7,
        "viewpoint": 8, "cta": 6, "title_bait_risk": 1,
        "controversy_overload_risk": 1,
    }
    store.record_content_score(asset_id=asset["id"], scores=scores)
    store.create_prediction(
        asset_id=asset["id"], prediction={
            "expected_views": {"low": 1000, "mid": 3000, "high": 8000},
            "expected_engagement_rate": {"low": 0.03, "mid": 0.06, "high": 0.1},
        },
    )
    store.transition_content_asset(asset["id"], "review")
    store.transition_content_asset(asset["id"], "approved")
    publishing = store.create_publishing_task(asset_id=asset["id"], platform="douyin")
    store.complete_publishing_task(
        publishing["id"], effect_id="effect-1", receipt={"post_id": "post-1"},
    )
    collected = store.collect_metrics(
        publishing["id"], {"views": 4200, "engagement_rate": 0.07}
    )
    assert collected["learning"]["strategy_candidate_id"]
    timeline = lifecycle.experiment_timeline(
        user_id="u", account_id="a", project_id=project["id"],
        experiment_id=experiment["id"],
    )
    assert len(timeline["assets"]) == 1
    assert len(timeline["scores"]) == 1
    assert len(timeline["predictions"]) == 1
    assert timeline["publishing_tasks"][0]["receipt"]["post_id"] == "post-1"
    assert len(timeline["retrospectives"]) == 1
    assert timeline["experiment"]["status"] == "review_due"
    candidates = lifecycle.list_strategy_candidates(
        user_id="u", account_id="a", project_id=project["id"], status="pending",
    )
    assert candidates[0]["proposal"]["type"] == "review_experiment"


def test_strategy_candidate_rejection_requires_reason_and_preserves_decision(tmp_path):
    lifecycle = service(tmp_path)
    project = lifecycle.create_project(user_id="u", account_id="a", business_goal="g")
    candidate = lifecycle.create_strategy_candidate(
        user_id="u", account_id="a", project_id=project["id"], trigger="user_feedback",
        proposal={"type": "avoid_topic", "topic": "泛娱乐热点"},
        evidence_refs=["user_message:feedback-1"], confidence=0.9,
    )
    with pytest.raises(ValueError, match="rejection reason"):
        lifecycle.decide_strategy_candidate(
            user_id="u", account_id="a", project_id=project["id"],
            candidate_id=candidate["id"], decision="rejected", reason="",
        )
    rejected = lifecycle.decide_strategy_candidate(
        user_id="u", account_id="a", project_id=project["id"],
        candidate_id=candidate["id"], decision="rejected", reason="不符合账号专业定位",
    )
    assert rejected["status"] == "rejected"
    assert rejected["decision_reason"] == "不符合账号专业定位"
    with pytest.raises(ValueError, match="only pending"):
        lifecycle.decide_strategy_candidate(
            user_id="u", account_id="a", project_id=project["id"],
            candidate_id=candidate["id"], decision="accepted", reason="反悔",
        )


def test_accepted_weight_strategy_candidate_creates_draft_experiment(tmp_path):
    lifecycle = service(tmp_path)
    project, observations = _make_positioning_ready(lifecycle)
    positioning = lifecycle.draft_positioning(
        user_id="u", account_id="a", project_id=project["id"], positioning={
            "promise": "帮助本地门店用短视频稳定获客",
            "differentiation": "用真实案例和复盘拆解降低试错成本",
            "persona": "经营陪练",
            "content_pillars": ["案例拆解", "工具实操"],
            "tone": ["务实", "直接"],
            "taboos": ["虚构收益", "过度焦虑"],
        }, evidence_refs=[item["id"] for item in observations],
    )
    lifecycle.approve_positioning(
        user_id="u", account_id="a", project_id=project["id"],
        positioning_id=positioning["id"],
    )
    candidate = lifecycle.create_strategy_candidate(
        user_id="u", account_id="a", project_id=project["id"],
        trigger="weight_candidate_replay",
        proposal={
            "type": "calibrate_influence_weight",
            "source_weight_candidate_id": "learn_weight_1",
            "rule_key": "retention_gap_after_attention",
            "proposed_adjustment": {
                "component": "RetentionDesign",
                "direction": "increase",
                "amount": 0.08,
            },
            "recommendation": "加强前 5 秒后的留存设计",
            "replay_summary": {"status": "passed", "support_count": 4},
        },
        evidence_refs=["learning_candidate:learn_weight_1"], confidence=0.82,
    )

    accepted = lifecycle.decide_strategy_candidate(
        user_id="u", account_id="a", project_id=project["id"],
        candidate_id=candidate["id"], decision="accepted", reason="回放通过，进入下一轮验证",
    )

    assert accepted["status"] == "accepted"
    assert accepted["experiment_id"]
    assert accepted["materialization"]["status"] == "created"
    experiment = accepted["materialization"]["experiment"]
    assert experiment["status"] == "draft"
    assert experiment["variable"]["source_strategy_candidate_id"] == candidate["id"]
    assert experiment["variable"]["source_weight_candidate_id"] == "learn_weight_1"
    assert experiment["variable"]["component"] == "RetentionDesign"
    assert experiment["prediction"]["primary_metric"] == "retention"
    assert experiment["success_criteria"]["requires_blind_prediction"] is True
    assert "no durable strategy weight changed" in experiment["variable"]["guardrail"]


def test_accepted_weight_strategy_candidate_blocks_experiment_without_positioning(tmp_path):
    lifecycle = service(tmp_path)
    project = lifecycle.create_project(user_id="u", account_id="a", business_goal="g")
    candidate = lifecycle.create_strategy_candidate(
        user_id="u", account_id="a", project_id=project["id"],
        trigger="weight_candidate_replay",
        proposal={
            "type": "calibrate_influence_weight",
            "source_weight_candidate_id": "learn_weight_2",
            "rule_key": "action_gap_after_attention",
            "proposed_adjustment": {
                "component": "BusinessValue",
                "direction": "increase",
                "amount": 0.05,
            },
            "replay_summary": {"status": "passed", "support_count": 3},
        },
        evidence_refs=["learning_candidate:learn_weight_2"], confidence=0.76,
    )

    accepted = lifecycle.decide_strategy_candidate(
        user_id="u", account_id="a", project_id=project["id"],
        candidate_id=candidate["id"], decision="accepted", reason="先记录策略接受",
    )

    assert accepted["status"] == "accepted"
    assert "experiment_id" not in accepted
    assert accepted["materialization"]["status"] == "blocked"
    assert accepted["materialization"]["reason"] == "approved_positioning_required"
    assert lifecycle.list_experiments(
        user_id="u", account_id="a", project_id=project["id"],
    ) == []


def test_experiment_rejects_cross_account_asset(tmp_path):
    store = AgentCoreStore(tmp_path / "core.db")
    lifecycle = AccountLifecycleService(store)
    project, observations = _make_positioning_ready(lifecycle)
    positioning = lifecycle.draft_positioning(
        user_id="u", account_id="a", project_id=project["id"], positioning={
            "promise": "p", "differentiation": "d", "persona": "x",
            "content_pillars": [], "tone": [], "taboos": [],
        }, evidence_refs=[item["id"] for item in observations],
    )
    lifecycle.approve_positioning(
        user_id="u", account_id="a", project_id=project["id"], positioning_id=positioning["id"],
    )
    experiment = lifecycle.create_experiment(
        user_id="u", account_id="a", project_id=project["id"], hypothesis="h",
        variable={"hook": "question"}, prediction={"views": 1000},
        success_criteria={"views_gte": 1000},
    )
    foreign = store.create_content_asset(user_id="u", account_id="other", title="foreign")
    with pytest.raises(ValueError, match="outside experiment account scope"):
        lifecycle.attach_experiment_asset(
            user_id="u", account_id="a", project_id=project["id"],
            experiment_id=experiment["id"], asset_id=foreign["id"],
        )


def test_audience_gap_keeps_fact_inference_and_unknown_separate(tmp_path):
    lifecycle = service(tmp_path)
    project, observations = _make_positioning_ready(lifecycle)
    audience_observation = next(item for item in observations if item["dimension"] == "audience")
    # Add a richer benchmark audience observation; the earlier observation remains valid evidence history.
    benchmark_id = audience_observation["benchmark_account_id"]
    rich_observation = lifecycle.add_benchmark_observation(
        user_id="u", account_id="a", project_id=project["id"],
        benchmark_account_id=benchmark_id, dimension="audience",
        value={"dimensions": {
            "age": {"24-30": 0.55},
            "interests": {"短视频获客": 0.8},
        }}, provenance={
            "source_kind": "public_web", "source_ref": "https://example.com/benchmark-audience",
            "captured_at": "2026-07-03T12:00:00Z",
        }, confidence=0.65,
    )
    lifecycle.add_audience_snapshot(
        user_id="u", account_id="a", project_id=project["id"], platform="douyin",
        dimensions={
            "age": {"24-30": 0.7, "18-23": 0.3},
            "interests": {"短视频获客": 0.6, "门店经营": 0.4},
            "region": {"广东": 0.5},
        }, provenance={
            "source_kind": "official_api", "source_ref": "douyin:fans.data",
            "captured_at": "2026-07-03T13:00:00Z", "data_gaps": ["occupation_unavailable"],
        },
    )
    gap = lifecycle.compare_audience_gap(
        user_id="u", account_id="a", project_id=project["id"],
    )
    assert gap["dimension_comparisons"]["age"]["status"] == "partial_overlap"
    assert gap["dimension_comparisons"]["interests"]["status"] == "aligned"
    assert gap["dimension_comparisons"]["region"]["status"] == "unknown"
    assert gap["dimension_comparisons"]["age"]["benchmark_evidence_refs"] == [rich_observation["id"]]
    assert gap["interpretation"]["mismatch_is_fact"] is False


def test_audience_gap_without_actual_snapshot_reports_unknown_not_mismatch(tmp_path):
    lifecycle = service(tmp_path)
    project, _ = _make_positioning_ready(lifecycle)
    gap = lifecycle.compare_audience_gap(
        user_id="u", account_id="a", project_id=project["id"],
    )
    assert gap["actual_audience_snapshot"] is None
    assert set(gap["unknown_dimensions"]) >= {"age", "interests"}
    assert all(
        item["status"] == "unknown" for item in gap["dimension_comparisons"].values()
    )
