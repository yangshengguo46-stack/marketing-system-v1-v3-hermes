import pytest

from agent.marketing.intelligence.audience_reaction_simulation import (
    build_social_reaction_simulation,
    compare_social_reaction_simulation,
    normalize_social_reaction_observation,
)


def _scenarios(evidence_id="evidence_one"):
    return [
        {
            "cohort": "正在尝试 AI 工作流的职场新人",
            "cohort_relation": "target",
            "stance": "experience_sharing",
            "need_projection": "belonging",
            "cognitive_projection": "Fe",
            "existence_strategy": "confirm",
            "likelihood_band": "high",
            "trigger": "文章描述了从重复任务开始的方法",
            "rationale": "读者可能通过分享自己的实践确认经验和群体身份",
            "likely_comment_themes": ["自己的第一次尝试", "工作流对比"],
            "synthetic_comment_examples": ["我也是从周报开始试的，最难的是保留人工复核。"],
            "response_opportunity": "追问具体任务并收集可复用案例",
            "risk": "成功样本可能造成幸存者偏差",
            "evidence_basis": [evidence_id],
            "disconfirming_signals": ["真实评论没有经验分享主题"],
        },
        {
            "cohort": "担心 AI 夸大宣传的谨慎读者",
            "cohort_relation": "adjacent",
            "stance": "skeptical",
            "need_projection": "safety",
            "cognitive_projection": "Ti",
            "existence_strategy": "preserve",
            "likelihood_band": "medium",
            "trigger": "标题承诺改变工作方式",
            "rationale": "读者可能优先检查成本、错误率和适用边界",
            "likely_comment_themes": ["有没有真实数据", "失败成本"],
            "synthetic_comment_examples": ["方法听起来不错，但错误率和复核时间怎么算？"],
            "response_opportunity": "补充证据边界并承认未知",
            "risk": "如果正文没有边界，质疑会转为不信任",
            "evidence_basis": [evidence_id],
            "disconfirming_signals": ["真实评论几乎没有证据或成本质疑"],
        },
        {
            "cohort": "希望马上落地的行动型读者",
            "cohort_relation": "target",
            "stance": "action_seeking",
            "need_projection": "self_actualization",
            "cognitive_projection": "Te",
            "existence_strategy": "expand",
            "likelihood_band": "medium",
            "trigger": "结尾提供了一周小实验",
            "rationale": "读者可能寻找模板、步骤和工具入口",
            "likely_comment_themes": ["从哪个任务开始", "有没有模板"],
            "synthetic_comment_examples": ["如果只选一个任务开始，你建议先记录哪些字段？"],
            "response_opportunity": "提供低成本第一步而不是直接销售",
            "risk": "行动路径太泛会带来失望",
            "evidence_basis": [evidence_id],
            "disconfirming_signals": ["真实评论没有行动问题或下一步请求"],
        },
    ]


def test_social_reaction_simulation_is_anonymous_and_replayable():
    result = build_social_reaction_simulation(
        scenarios=_scenarios(),
        audience_context={
            "id": "audience_1",
            "version": 2,
            "status": "confirmed",
            "segments": ["AI 入门职场人"],
            "pains": ["重复工作多"],
            "scenarios": ["希望先从低风险任务试用"],
            "jobs": ["减少重复劳动"],
            "trust_barriers": ["担心夸大效果"],
            "desired_outcomes": ["获得可控的工作流"],
            "data_gaps": [],
        },
        content_context={
            "title": "普通人如何把 AI 变成工作搭档",
            "topic": "AI 工作流",
            "hook": "不是多学一个工具，而是重做工作方式",
            "objective": "形成一篇可执行的公众号文章",
        },
        platforms=["wechat_official"],
        evidence_refs=["evidence_one"],
    )

    assert result["version"] == "social-reaction-simulation-v0.3"
    assert result["status"] == "audience_hypothesis_backed"
    assert result["scope"] == "anonymous_cohort_scenarios_not_individual_prediction"
    assert result["simulation_id"].startswith("srs_")
    assert len(result["scenarios"]) == 3
    assert all(item["synthetic"] is True for item in result["scenarios"])
    assert {item["stance"] for item in result["scenarios"]} >= {
        "experience_sharing", "skeptical", "action_seeking"
    }
    assert result["retro_contract"]["mutable"] is False


def test_social_reaction_simulation_rejects_identity_and_fake_precision():
    scenarios = _scenarios()
    scenarios[0]["handle"] = "real-person"
    with pytest.raises(ValueError, match="cannot identify a person"):
        build_social_reaction_simulation(
            scenarios=scenarios,
            audience_context={},
            content_context={"title": "test"},
            platforms=["douyin"],
            evidence_refs=["evidence_one"],
        )

    scenarios = _scenarios()
    scenarios[0]["likelihood_band"] = "73%"
    with pytest.raises(ValueError, match="unsupported likelihood_band"):
        build_social_reaction_simulation(
            scenarios=scenarios,
            audience_context={},
            content_context={"title": "test"},
            platforms=["douyin"],
            evidence_refs=["evidence_one"],
        )


def test_social_reaction_simulation_rejects_real_user_contact_patterns():
    scenarios = _scenarios()
    scenarios[0]["synthetic_comment_examples"] = ["联系我 vx: abcdef123"]
    with pytest.raises(ValueError, match="contact details"):
        build_social_reaction_simulation(
            scenarios=scenarios,
            audience_context={},
            content_context={"title": "test"},
            platforms=["douyin"],
            evidence_refs=["evidence_one"],
        )


def test_social_reaction_retro_compares_only_anonymous_clusters():
    simulation = build_social_reaction_simulation(
        scenarios=_scenarios(),
        audience_context={"segments": ["AI 入门职场人"]},
        content_context={"title": "test"},
        platforms=["douyin"],
        evidence_refs=["evidence_one"],
    )
    observation = normalize_social_reaction_observation(
        {
            "sample_size": 12,
            "scenario_matches": [
                {
                    "scenario_id": simulation["scenarios"][0]["id"],
                    "count": 4,
                    "observed_themes": ["自己的尝试"],
                },
                {
                    "scenario_id": simulation["scenarios"][1]["id"],
                    "count": 2,
                    "observed_themes": ["复核成本"],
                },
            ],
            "unexpected_clusters": [
                {
                    "stance": "oppositional",
                    "need_projection": "safety",
                    "cognitive_projection": "Ni",
                    "existence_strategy": "preserve",
                    "collective_mechanism": "emotional_contagion",
                    "theme": "岗位替代焦虑",
                    "count": 3,
                }
            ],
            "question_patterns": ["如何核算人工复核"],
            "objection_patterns": ["没有展示长期样本"],
            "data_gaps": ["只采样高赞评论"],
        },
        simulation=simulation,
    )
    result = compare_social_reaction_simulation(simulation, observation)

    assert observation["aggregation"] == "anonymous_clusters_only"
    assert "privacy_notice" in observation
    assert result["status"] == "compared"
    assert result["coverage"] == pytest.approx(2 / 3, rel=1e-3)
    assert len(result["missed_scenario_ids"]) == 1
    assert result["unexpected_clusters"][0]["theme"] == "岗位替代焦虑"
    projection = result["projection_chain_retro"]
    strategy = projection["dimensions"]["existence_strategy"]
    assert strategy["predicted_scenario_counts"] == {
        "confirm": 1,
        "preserve": 1,
        "expand": 1,
    }
    assert strategy["matched_scenario_counts"] == {"confirm": 1, "preserve": 1}
    assert strategy["unexpected_cluster_counts"] == {"preserve": 3}
    assert strategy["scenario_coverage"]["expand"] == 0
    assert projection["dimensions"]["need_projection"]["scenario_coverage"] == {
        "belonging": 1.0,
        "safety": 1.0,
        "self_actualization": 0.0,
    }
    assert projection["dimensions"]["collective_mechanism"][
        "unexpected_cluster_counts"
    ] == {"emotional_contagion": 3}


def test_social_reaction_observation_rejects_raw_comments():
    simulation = build_social_reaction_simulation(
        scenarios=_scenarios(),
        audience_context={"segments": ["AI 入门职场人"]},
        content_context={"title": "test"},
        platforms=["douyin"],
        evidence_refs=["evidence_one"],
    )
    with pytest.raises(ValueError, match="anonymous aggregates"):
        normalize_social_reaction_observation(
            {"sample_size": 1, "comments": [{"nickname": "某人", "text": "原话"}]},
            simulation=simulation,
        )


def test_social_reaction_observation_rejects_identity_text_and_duplicate_matches():
    simulation = build_social_reaction_simulation(
        scenarios=_scenarios(),
        audience_context={"segments": ["AI 入门职场人"]},
        content_context={"title": "test"},
        platforms=["douyin"],
        evidence_refs=["evidence_one"],
    )
    scenario_id = simulation["scenarios"][0]["id"]

    with pytest.raises(ValueError, match="contact details"):
        normalize_social_reaction_observation(
            {
                "sample_size": 1,
                "scenario_matches": [
                    {
                        "scenario_id": scenario_id,
                        "count": 1,
                        "observed_themes": ["联系微信 abc12345"],
                    }
                ],
            },
            simulation=simulation,
        )

    with pytest.raises(ValueError, match="duplicate reaction scenario id"):
        normalize_social_reaction_observation(
            {
                "sample_size": 2,
                "scenario_matches": [
                    {"scenario_id": scenario_id, "count": 1},
                    {"scenario_id": scenario_id, "count": 1},
                ],
            },
            simulation=simulation,
        )
