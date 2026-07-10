import pytest
import shutil
import subprocess
from pathlib import Path

from agent_core import AccountLifecycleService, AgentCoreStore
from agent_core.article_soft_production import build_soft_article_asset_payload, create_soft_article_asset
from agent_core.content_production import build_content_production_plan, infer_content_kind
from agent_core.experiment_driven_production import (
    build_content_request_from_experiment,
    create_content_from_experiment,
)
from agent_core.content_skill_registry import recommended_skills_for_lane, verify_skill_mounts
from agent_core.faceless_video_production import (
    build_faceless_video_asset_payload,
    create_faceless_video_asset,
    fill_faceless_image_materials,
    prepare_faceless_render,
    render_faceless_animatic,
    render_faceless_final,
)
from agent_core.hermes_adapter import HermesAgentService
from agent_core.models import CapabilityLevel
from agent_core.tool_manifest import tool_by_name


def test_infers_article_lane_for_zhihu_and_official_account():
    assert infer_content_kind({
        "objective": "写一篇新能源汽车行业软文",
        "platforms": ["zhihu", "wechat_official"],
    }) == "article_soft"

    plan = build_content_production_plan({
        "objective": "写一篇新能源汽车行业软文",
        "platforms": ["zhihu", "wechat_official"],
    })

    assert plan["kind"] == "article_soft"
    assert plan["content_asset_type"] == "script"
    assert plan["target_platforms"] == ["zhihu", "wechat_official"]
    assert "marketing_research_web_search" in plan["tool_sequence"]
    assert "marketing_draft_soft_article_create" in plan["tool_sequence"]
    assert any(gate["name"] == "事实证据门" for gate in plan["gates"])
    assert plan["capability_pool"]["model"] == "shared_capability_pool"
    assert plan["lane_contract"]["is_silo"] is False
    assert "stock_material" in plan["capability_pool"]["optional"]
    assert "generated_image" in plan["capability_pool"]["optional"]
    assert "visual_brief" in plan["outputs"]["asset_content_shape"]
    assert plan["material_policy"]["requires_license_check"] is True


def test_faceless_video_lane_requires_material_provenance_without_paid_video_api():
    plan = build_content_production_plan({
        "objective": "做一条不露脸素材拼接视频，讲 AI 教育",
        "platforms": ["douyin"],
    })

    assert plan["kind"] == "faceless_video"
    assert plan["content_asset_type"] == "video"
    assert plan["cost_policy"]["paid_api_required"] is False
    assert plan["material_policy"]["requires_license_check"] is True
    assert "material_queries" in plan["outputs"]["asset_content_shape"]
    assert "generated_asset_requests" in plan["outputs"]["asset_content_shape"]
    assert "marketing_draft_faceless_video_create" in plan["tool_sequence"]
    assert "generated_video" in plan["capability_pool"]["optional"]
    assert "stock_material" in plan["capability_pool"]["required"]
    assert any(gate["name"] == "版权/来源门" for gate in plan["gates"])


def test_premium_human_video_lane_is_blocked_until_provider_calibration():
    plan = build_content_production_plan({
        "objective": "做一条真人数字人高质量视频",
        "platforms": ["douyin", "bilibili"],
    })

    assert plan["kind"] == "premium_human_video"
    assert plan["status"] == "blocked_on_provider_calibration"
    assert plan["cost_policy"]["paid_api_required"] is True
    assert plan["fallback"]["if_provider_unavailable"].startswith("降级为 faceless_video")
    assert "stock_material" in plan["capability_pool"]["optional"]
    assert "reference_assets" in plan["outputs"]["asset_content_shape"]
    assert any(gate["name"] == "Provider 校准门" for gate in plan["gates"])


def test_content_lanes_share_capabilities_instead_of_three_silos():
    article = build_content_production_plan({"objective": "写一篇公众号软文"})
    faceless = build_content_production_plan({"objective": "做一条不露脸素材视频"})
    premium = build_content_production_plan({"objective": "做一条数字人高质量视频"})

    assert article["lane_contract"]["shared_flow"] == faceless["lane_contract"]["shared_flow"]
    assert faceless["lane_contract"]["shared_flow"] == premium["lane_contract"]["shared_flow"]
    assert faceless["lane_contract"]["shared_editing_engine"]["module"] == "engine.video_core.editing_engine"
    assert premium["lane_contract"]["shared_editing_engine"]["single_source_of_truth"] == "EDL"
    assert article["capability_pool"]["capabilities"]["stock_material"]["maturity"] == "partial"
    assert faceless["capability_pool"]["capabilities"]["generated_video"]["approval"] == "cost_and_rights"
    assert premium["capability_pool"]["capabilities"]["stock_material"]["approval"] == "license_check"


def test_content_plans_expose_auditable_recommended_skills():
    article = build_content_production_plan({"objective": "写一篇公众号软文"})
    faceless = build_content_production_plan({"objective": "做一条不露脸素材视频"})
    premium = build_content_production_plan({"objective": "做一条数字人视频"})

    article_ids = {item["id"] for item in article["recommended_skills"]}
    faceless_ids = {item["id"] for item in faceless["recommended_skills"]}
    premium_ids = {item["id"] for item in premium["recommended_skills"]}

    assert "content.platform_adapter" in article_ids
    assert "creative.humanizer" in article_ids
    assert "video.director_pipeline" in faceless_ids
    assert "video.short_video_script" not in faceless_ids
    assert "content.short_video_script" in faceless_ids
    assert "creative.baoyu_infographic" in premium_ids
    assert all(item["path"].endswith("SKILL.md") for item in faceless["recommended_skills"])


def test_content_skill_registry_can_verify_local_mounts_without_loading_runtime():
    skills = recommended_skills_for_lane("faceless_video")
    assert any(item["role"] == "code_visual" for item in skills)

    result = verify_skill_mounts(Path(__file__).resolve().parents[1])
    assert result["total"] >= len(skills)
    assert "content.short_video_script" in result["present"] + result["missing"]


def _ready_experiment(store: AgentCoreStore) -> tuple[AccountLifecycleService, dict, dict]:
    lifecycle = AccountLifecycleService(store)
    project = lifecycle.create_project(user_id="u", account_id="acct_exp", business_goal="验证内容策略")
    audience = lifecycle.draft_audience_hypothesis(
        user_id="u", account_id="acct_exp", project_id=project["id"],
        segments=[{"label": "准备做 AI 工具内容的普通创作者"}],
    )
    lifecycle.confirm_audience_hypothesis(
        user_id="u", account_id="acct_exp", project_id=project["id"],
        hypothesis_id=audience["id"],
    )
    benchmarks = []
    for handle, relation in (("peer-good", "direct"), ("peer-bad", "negative")):
        benchmark = lifecycle.add_benchmark_account(
            user_id="u", account_id="acct_exp", project_id=project["id"],
            platform="douyin", account_handle=handle, account_name=handle,
            relation=relation, selection_reason="测试内容实验绑定",
            source_ref=f"https://example.com/{handle}",
        )
        benchmarks.append(benchmark)
        for index in range(5):
            lifecycle.add_benchmark_sample(
                user_id="u", account_id="acct_exp", project_id=project["id"],
                benchmark_account_id=benchmark["id"], video_id=f"{handle}-{index}",
                title=f"{handle}-{index}", transcript=None, metrics={},
                provenance={
                    "source_kind": "public_web",
                    "source_ref": f"https://example.com/{handle}/{index}",
                    "captured_at": "2026-07-09T10:00:00Z",
                },
            )
    observations = []
    for dimension in ("audience", "positioning", "content_pillar", "format", "engagement"):
        observations.append(lifecycle.add_benchmark_observation(
            user_id="u", account_id="acct_exp", project_id=project["id"],
            benchmark_account_id=benchmarks[0]["id"], dimension=dimension,
            value={"finding": dimension},
            provenance={
                "source_kind": "public_web",
                "source_ref": f"https://example.com/obs/{dimension}",
                "captured_at": "2026-07-09T10:00:00Z",
            },
            confidence=0.8,
        ))
    positioning = lifecycle.draft_positioning(
        user_id="u", account_id="acct_exp", project_id=project["id"],
        positioning={
            "promise": "帮普通创作者看懂 AI 工具内容机会",
            "differentiation": "用真实案例和证据做判断",
            "persona": "内容增长陪练",
            "content_pillars": ["工具拆解", "案例复盘"],
            "tone": ["清晰", "克制"],
            "taboos": ["夸大收益"],
        },
        evidence_refs=[item["id"] for item in observations],
    )
    lifecycle.approve_positioning(
        user_id="u", account_id="acct_exp", project_id=project["id"],
        positioning_id=positioning["id"],
    )
    experiment = lifecycle.create_experiment(
        user_id="u", account_id="acct_exp", project_id=project["id"],
        hypothesis="带具体案例的软文能提升信任互动",
        variable={"type": "article_soft", "source_strategy_candidate_id": "strategy_1"},
        prediction={"primary_metric": "trust"},
        success_criteria={"primary_metric": "trust", "requires_blind_prediction": True},
    )
    return lifecycle, project, experiment


def _agent_article_drafts(topic: str = "AI 工具内容") -> dict:
    parent = f"""# {topic}：先把判断方法说清楚

## 为什么现在值得重新判断
很多人看到一个行业热词，就在乐观和悲观之间来回摇摆。真正影响普通人决策的，不是某一天的热搜，而是需求是否持续、竞争是否改变、个人能力能否形成可验证的价值。公开资料显示，这个领域仍在结构调整之中 [ev_01]。这句话只能说明变化仍在发生，不能直接推出人人都能获得结果。

## 先区分事实、推断和个人选择
事实层只保留可以回到来源核验的信息，包括公开数据、规则说明和真实案例。推断层要写清前提：如果需求持续、平台分发没有剧烈变化，那么具备具体经验的人更容易建立信任。个人选择层则要看时间、能力、风险承受力和愿不愿意长期表达。把三层混在一起，文章就会从分析滑向鼓动。

## 一个可以执行的判断框架
第一步，列出自己能连续讲二十次的真实问题，不写空泛赛道名。第二步，找三个正向样本和两个反向样本，观察它们解决了谁的问题，而不是只看粉丝量。第三步，用一周做三种表达实验，每次只改变标题、案例或结构中的一个变量。第四步，记录阅读、停留、收藏和评论里真正出现的问题，再决定是否加码。

## 什么情况下不建议马上投入
如果素材主要来自转述、无法说明证据来源，先停止发布；如果只能模仿爆款语气，却没有自己的经历或验证过程，也不适合急着扩量。短期热度可以带来曝光，但长期信任来自持续兑现同一种价值承诺。一个稳妥的起点，是先完成最小实验，再让真实反馈修正判断。

## 下一步怎么做
今天先写下一条你亲自经历过、能够提供细节的问题，再为它补一条可回链资料 [ev_01]。发布后不要急着用播放量给自己定性，先看读者是否理解、是否追问、是否愿意保存。这个过程不会承诺快速收益，但能让下一次创作比这一次更有依据。
"""
    zhihu = f"""# {topic}到底值不值得做？

知乎读者更需要的是论证，而不是一句结论。先给边界：公开资料只能证明行业仍在变化 [ev_01]，不能证明每个新账号都有机会。判断时可以拆成三问：用户的问题是否反复出现，你是否拥有可验证的经验，这种经验能否连续表达。

## 为什么只看热度会误判
热度描述的是注意力，不等于信任，更不等于转化。一个话题很热，可能意味着竞争已经拥挤；一个话题不在热榜，也可能存在稳定而明确的需求。因此要同时查看正向样本、失败样本和评论中的具体问题。

## 我的建议
先做一周小实验：三篇内容只改变一个变量，保留证据链接，记录收藏、追问和反对意见。若读者开始提出更具体的问题，再继续深化；若反馈始终停留在泛泛点赞，就回到受众和承诺重新定位。这个结论是方法建议，不是收益保证。
"""
    wechat = f"""# 别急着追风口，先做一次小验证

打开后台看到某个话题突然变热，最容易做的决定是立刻跟上，最难的决定是先问一句：这和我的读者有什么关系？公开资料可以帮助我们确认变化存在 [ev_01]，但真正决定内容价值的，是读者能不能把信息用于自己的选择。

## 今天只做四步
先写清你服务的是谁；再列出他此刻最具体的困惑；然后找一条能够回链的证据；最后用自己的经历解释这条证据意味着什么。不要堆术语，也不要许诺结果。

## 把反馈留给下一篇
发布后记录读者收藏了哪一段、追问了什么、在哪句话离开。数据不是成绩单，而是下一次创作的输入。只要每一轮都保留来源、假设和结果，账号就会逐步形成自己的判断能力。你也可以把当前方向和可投入时间告诉我，我们继续把第一次实验缩小到今天能完成的程度。
"""
    assert len(parent.replace("\n", "")) >= 600
    assert len(zhihu.replace("\n", "")) >= 300
    assert len(wechat.replace("\n", "")) >= 300
    return {
        "body_markdown": parent,
        "platform_variants": {
            "zhihu": {"title": f"{topic}到底值不值得做？", "body_markdown": zhihu},
            "wechat_official": {"title": "别急着追风口，先做一次小验证", "body_markdown": wechat},
        },
    }


def test_content_production_tool_is_read_only_and_registered():
    tool = tool_by_name("marketing_plan_content_production")
    assert tool is not None
    assert tool.level == CapabilityLevel.READ_ONLY
    assert "不调用付费视频 API" in tool.description

    article_tool = tool_by_name("marketing_draft_soft_article_create")
    assert article_tool is not None
    assert article_tool.level == CapabilityLevel.REVERSIBLE_WRITE
    assert "不替 Agent 套模板写正文" in article_tool.description
    assert "body_markdown" in article_tool.schema["properties"]

    faceless_tool = tool_by_name("marketing_draft_faceless_video_create")
    assert faceless_tool is not None
    assert faceless_tool.level == CapabilityLevel.REVERSIBLE_WRITE
    assert "不渲染成片" in faceless_tool.description

    experiment_tool = tool_by_name("marketing_draft_content_from_experiment")
    assert experiment_tool is not None
    assert experiment_tool.level == CapabilityLevel.REVERSIBLE_WRITE
    assert "挂回 experiment" in experiment_tool.description

    render_tool = tool_by_name("marketing_prepare_faceless_render")
    assert render_tool is not None
    assert render_tool.level == CapabilityLevel.READ_ONLY
    assert "不执行渲染" in render_tool.description

    preflight_tool = tool_by_name("marketing_draft_content_preflight")
    assert preflight_tool is not None
    assert preflight_tool.level == CapabilityLevel.REVERSIBLE_WRITE
    assert "独立片子预演" in preflight_tool.description


def test_soft_article_builder_creates_reviewable_asset_with_variants(tmp_path):
    store = AgentCoreStore(tmp_path / "soft-article.db")
    result = create_soft_article_asset(store, {
        **_agent_article_drafts("新能源汽车行业"),
        "objective": "写一篇新能源汽车行业适合公众号和知乎的软文",
        "platforms": ["zhihu", "wechat_official"],
        "account_id": "acct_ev",
        "audience_context": {
            "target_reader": "正在寻找转型机会的普通职场人",
            "pain_points": ["不知道行业是否还有机会", "担心被营销号割韭菜"],
            "promise": "给出一个不夸张的判断框架",
        },
        "evidence": [
            {
                "title": "新能源汽车产业公开数据",
                "summary": "行业仍处于长期竞争和结构调整阶段",
                "url": "https://example.com/ev-report",
            }
        ],
    })

    assert result["status"] == "ok"
    assert result["article_status"] == "ready_for_review"
    assert result["production_gate"]["status"] == "ready_for_asset_draft"
    assert result["production_gate"]["go"] is True
    assert result["preflight_id"].startswith("preflight_")
    assert result["variant_count"] == 2
    assert result["review"] is None
    assert result["review_status"] == "human_review_required"
    assert result["prediction_status"] == "not_created_before_human_review"

    asset = store.get_content_asset(result["asset_id"])
    assert asset["type"] == "script"
    assert asset["platform"] == "multi_article"
    assert asset["account_id"] == "acct_ev"
    assert asset["content"]["production_kind"] == "article_soft"
    assert asset["content"]["preflight_gate"]["preflight_id"] == result["preflight_id"]
    assert asset["content"]["quality_gates"][-1]["name"] == "总预演门"
    assert asset["content"]["quality_gates"][-1]["status"] == "pass"
    assert asset["content"]["evidence_status"]["ready"] is True
    assert asset["content"]["parent_draft"]["draft_origin"] == "agent_authored"
    assert asset["content"]["draft_validation"]["ready"] is True
    assert asset["content"]["draft_validation"]["cited_evidence_refs"] == ["ev_01"]
    assert asset["content"]["draft_validation"]["copied_platform_variants"] == []
    assert asset["content"]["draft_validation"]["uncited_platform_variants"] == []
    assert asset["content"]["draft_validation"]["duplicate_platform_variant_pairs"] == []
    assert "zhihu" in asset["content"]["platform_variants"]
    assert "wechat_official" in asset["content"]["platform_variants"]
    wechat_variant = asset["content"]["platform_variants"]["wechat_official"]
    zhihu_variant = asset["content"]["platform_variants"]["zhihu"]
    assert wechat_variant["publish_pack"]["cover_spec"]["primary_ratio"] == "2.35:1"
    assert wechat_variant["publish_pack"]["typography_spec"]["body_font_size_px"] == [15, 16]
    assert zhihu_variant["publish_pack"]["typography_spec"]["body_font_size_px"] == "platform_controlled"
    assert "wechat_official" in asset["content"]["platform_publish_packs"]
    assert "zhihu" in asset["content"]["platform_publish_packs"]
    assert asset["content"]["visual_requirements"][0]["preferred_source"] == "stock_material"
    cover_requirements = [
        item for item in asset["content"]["visual_requirements"]
        if item["slot"] == "cover"
    ]
    assert {item["platform"] for item in cover_requirements} == {"zhihu", "wechat_official"}
    assert {
        item["platform"]: item["aspect_ratio"] for item in cover_requirements
    }["wechat_official"] == "2.35:1"
    assert {
        item["platform"]: item["aspect_ratio"] for item in cover_requirements
    }["zhihu"] == "16:9"
    feature_snapshot = asset["content"]["feature_snapshot"]
    assert feature_snapshot["id"].startswith("cfs_")
    assert feature_snapshot["version"] == "content-feature-snapshot-v0.1"
    assert feature_snapshot["protocol"] == "content_feature_snapshots"
    assert feature_snapshot["kind"] == "article_soft"
    assert feature_snapshot["identity"]["account_id"] == "acct_ev"
    assert feature_snapshot["identity"]["platforms"] == ["zhihu", "wechat_official"]
    assert feature_snapshot["evidence"]["with_url"] == 1
    assert feature_snapshot["structure"]["variant_count"] == 2
    assert feature_snapshot["structure"]["visual_requirement_count"] == len(asset["content"]["visual_requirements"])
    assert feature_snapshot["prediction_ref"]["prediction_version"] == "uncalibrated-readiness-v1"
    assert feature_snapshot["prediction_ref"]["dimension_names"] == []
    assert asset["content"]["pre_review_scores"] == {}
    assert asset["content"]["pre_publish_prediction"]["confidence"] == "none"
    assert "expected_views" not in asset["content"]["pre_publish_prediction"]
    assert store.list_content_scores() == []
    assert store.list_predictions() == []


def test_soft_article_asset_can_bind_back_to_account_experiment(tmp_path):
    store = AgentCoreStore(tmp_path / "soft-article-experiment.db")
    lifecycle, project, experiment = _ready_experiment(store)

    result = create_soft_article_asset(store, {
        **_agent_article_drafts(),
        "__user_id": "u",
        "account_id": "acct_exp",
        "project_id": project["id"],
        "experiment_id": experiment["id"],
        "objective": "写一篇 AI 工具内容机会的公众号软文",
        "platforms": ["wechat_official", "zhihu"],
        "audience_context": {
            "target_reader": "准备做 AI 工具内容的普通创作者",
            "promise": "给出不夸大的判断框架",
        },
        "evidence": [
            {"title": "AI 工具内容案例", "url": "https://example.com/ai-tools"}
        ],
    })

    assert result["status"] == "ok"
    assert result["experiment_link"]["experiment_id"] == experiment["id"]
    assert result["experiment_link"]["status"] == "running"
    asset = store.get_content_asset(result["asset_id"])
    assert asset["experiment_id"] == experiment["id"]
    assert asset["content"]["experiment_binding"]["experiment_id"] == experiment["id"]
    linked = lifecycle.get_experiment(
        user_id="u", account_id="acct_exp", project_id=project["id"],
        experiment_id=experiment["id"],
    )
    assert linked["status"] == "running"
    assert result["asset_id"] in linked["asset_ids"]


def test_experiment_driven_production_creates_soft_article_from_lifecycle_context(tmp_path):
    store = AgentCoreStore(tmp_path / "experiment-soft-article.db")
    lifecycle, project, experiment = _ready_experiment(store)

    built = build_content_request_from_experiment(store, {
        **_agent_article_drafts(),
        "__user_id": "u",
        "account_id": "acct_exp",
        "project_id": project["id"],
        "experiment_id": experiment["id"],
        "kind": "auto",
        "evidence": [
            {"title": "AI 工具公开案例", "url": "https://example.com/ai-tool-case"}
        ],
    })
    assert built["kind"] == "article_soft"
    assert built["production_request"]["audience_context"]["source"] == "account_lifecycle"
    assert built["production_request"]["experiment_id"] == experiment["id"]

    result = create_content_from_experiment(store, {
        **_agent_article_drafts(),
        "__user_id": "u",
        "account_id": "acct_exp",
        "project_id": project["id"],
        "experiment_id": experiment["id"],
        "kind": "auto",
        "evidence": [
            {"title": "AI 工具公开案例", "url": "https://example.com/ai-tool-case"}
        ],
    })

    assert result["status"] == "ok"
    assert result["kind"] == "article_soft"
    assert result["asset_id"]
    assert result["experiment_link"]["status"] == "running"
    asset = store.get_content_asset(result["asset_id"])
    assert asset["content"]["experiment_binding"]["primary_metric"] == "trust"
    timeline = lifecycle.experiment_timeline(
        user_id="u", account_id="acct_exp", project_id=project["id"],
        experiment_id=experiment["id"],
    )
    assert timeline["assets"][0]["id"] == result["asset_id"]


def test_soft_article_builder_blocks_publish_when_evidence_has_no_url():
    payload = build_soft_article_asset_payload({
        **_agent_article_drafts("AI 教育"),
        "objective": "写一篇 AI 教育软文",
        "evidence": [{"title": "只有一句传闻", "summary": "没有 URL"}],
    })

    assert payload["status"] == "needs_evidence"
    assert payload["content"]["evidence_status"]["ready"] is False
    assert payload["content"]["quality_gates"][0]["status"] == "blocked"
    assert payload["content"]["visual_requirements"][0]["status"] == "blocked_until_evidence_ready"


def test_soft_article_create_saves_scaffold_but_blocks_when_agent_body_is_missing(tmp_path):
    store = AgentCoreStore(tmp_path / "soft-article-missing-body.db")
    result = create_soft_article_asset(store, {
        "objective": "写一篇 AI 教育软文",
        "platforms": ["zhihu", "wechat_official"],
        "audience_context": {
            "target_reader": "准备了解 AI 教育的家长",
            "promise": "给出可验证的判断方法",
        },
        "evidence": [{"title": "AI 教育公开资料", "url": "https://example.com/ai-edu"}],
    })

    assert result["status"] == "blocked"
    assert result["draft_status"] == "needs_agent_draft"
    assert result["production_gate"]["go"] is True
    asset = store.get_content_asset(result["asset_id"])
    assert asset["content"]["parent_draft"]["draft_origin"] == "writing_scaffold"
    assert asset["content"]["draft_validation"]["issues"][0] == "agent_parent_draft_missing"
    assert "[用一个可验证的矛盾" in asset["content"]["parent_draft"]["body"]
    assert store.list_content_scores() == []
    assert store.list_predictions() == []


def test_soft_article_builder_blocks_platform_copy_instead_of_calling_it_rewrite():
    drafts = _agent_article_drafts("AI 教育")
    parent = drafts["body_markdown"]
    payload = build_soft_article_asset_payload({
        "objective": "写一篇 AI 教育软文",
        "body_markdown": parent,
        "platforms": ["zhihu", "wechat_official"],
        "platform_variants": {
            "zhihu": {"body_markdown": parent},
            "wechat_official": {"body_markdown": parent},
        },
        "audience_context": {"target_reader": "普通家长", "promise": "解释判断方法"},
        "evidence": [{"title": "AI 教育公开资料", "url": "https://example.com/ai-edu"}],
    })

    assert payload["status"] == "needs_platform_variants"
    assert payload["content"]["draft_validation"]["copied_platform_variants"] == [
        "zhihu", "wechat_official",
    ]
    assert "platform_variants_copy_parent" in payload["content"]["draft_validation"]["issues"]
    assert payload["content"]["quality_gates"][3]["status"] == "blocked"


def test_soft_article_builder_requires_evidence_lineage_in_each_platform_rewrite():
    drafts = _agent_article_drafts("AI 教育")
    drafts["platform_variants"]["zhihu"]["body_markdown"] = (
        drafts["platform_variants"]["zhihu"]["body_markdown"].replace(" [ev_01]", "")
    )
    payload = build_soft_article_asset_payload({
        "objective": "写一篇 AI 教育软文",
        **drafts,
        "audience_context": {"target_reader": "普通家长", "promise": "解释判断方法"},
        "evidence": [{"title": "AI 教育公开资料", "url": "https://example.com/ai-edu"}],
    })

    assert payload["status"] == "needs_draft_revision"
    assert payload["content"]["draft_validation"]["uncited_platform_variants"] == ["zhihu"]
    assert payload["content"]["quality_gates"][2]["status"] == "blocked"


def test_soft_article_create_blocks_before_review_when_preflight_missing_context(tmp_path):
    store = AgentCoreStore(tmp_path / "soft-article-blocked.db")
    result = create_soft_article_asset(store, {
        **_agent_article_drafts("AI 教育"),
        "objective": "写一篇 AI 教育软文",
        "platforms": ["zhihu"],
        "evidence": [{"title": "AI 教育公开资料", "url": "https://example.com/ai-edu"}],
    })

    assert result["status"] == "blocked"
    assert result["article_status"] == "needs_audience_context"
    assert result["review"] is None
    assert result["production_gate"]["go"] is False
    assert result["production_gate"]["status"] == "needs_audience_context"
    assert "audience_context_missing" in result["production_gate"]["blockers"]

    asset = store.get_content_asset(result["asset_id"])
    assert asset["content"]["article_status"] == "needs_audience_context"
    assert asset["content"]["preflight_gate"]["status"] == "needs_audience_context"
    assert asset["content"]["quality_gates"][-1]["status"] == "blocked"
    assert store.list_content_scores() == []
    assert store.list_predictions() == []


def test_faceless_video_builder_creates_video_asset_with_edl_and_material_queries(tmp_path):
    store = AgentCoreStore(tmp_path / "faceless.db")
    result = create_faceless_video_asset(store, {
        "objective": "做一条不露脸素材拼接视频，讲 AI 教育",
        "platforms": ["douyin", "bilibili"],
        "account_id": "acct_ai",
        "evidence": [
            {
                "title": "AI 教育公开研究",
                "summary": "AI 工具正在改变学习和内容生产流程",
                "url": "https://example.com/ai-edu",
            }
        ],
    })

    assert result["status"] == "ok"
    assert result["video_status"] == "ready_for_materials"
    assert result["production_gate"]["status"] == "ready_for_asset_draft"
    assert result["production_gate"]["go"] is True
    assert result["preflight_id"].startswith("preflight_")
    assert result["render_status"] == "not_rendered"
    assert result["shot_count"] >= 5
    assert result["material_query_count"] == result["shot_count"]
    assert result["generated_request_count"] >= 1

    asset = store.get_content_asset(result["asset_id"])
    assert asset["type"] == "video"
    assert asset["platform"] == "multi_video"
    assert asset["content"]["production_kind"] == "faceless_video"
    assert asset["content"]["preflight_gate"]["preflight_id"] == result["preflight_id"]
    assert asset["content"]["render_status"] == "not_rendered"
    assert asset["content"]["edl"]["clips"] == []
    assert len(asset["content"]["edl"]["unfilled_slots"]) == len(asset["content"]["shot_list"])
    assert asset["content"]["quality_gates"][3]["name"] == "渲染诚实门"
    assert asset["content"]["quality_gates"][-1]["name"] == "总预演门"
    assert asset["content"]["quality_gates"][-1]["status"] == "pass"
    feature_snapshot = asset["content"]["feature_snapshot"]
    assert feature_snapshot["id"].startswith("cfs_")
    assert feature_snapshot["version"] == "content-feature-snapshot-v0.1"
    assert feature_snapshot["protocol"] == "content_feature_snapshots"
    assert feature_snapshot["kind"] == "faceless_video"
    assert feature_snapshot["identity"]["account_id"] == "acct_ai"
    assert feature_snapshot["identity"]["platforms"] == ["douyin", "bilibili"]
    assert feature_snapshot["evidence"]["with_url"] == 1
    assert feature_snapshot["structure"]["shot_count"] == result["shot_count"]
    assert feature_snapshot["structure"]["render_status"] == "not_rendered"
    assert feature_snapshot["material_context"]["material_query_count"] == result["material_query_count"]
    assert feature_snapshot["material_context"]["generated_request_count"] == result["generated_request_count"]
    assert feature_snapshot["prediction_ref"]["prediction_version"] == "prepublish-prediction-v2.0"
    assert store.list_content_scores()[0]["asset_id"] == asset["id"]
    prediction = store.list_predictions()[0]
    assert prediction["asset_id"] == asset["id"]
    stored_prediction = prediction["prediction"]
    assert stored_prediction["prediction_version"] == "prepublish-prediction-v2.0"
    assert stored_prediction["expected_views"]["mid"] == 800
    assert stored_prediction["expected_completion_rate"]["mid"] == 0.32
    assert stored_prediction["prediction_dimensions"]["dimensions"]["retention"]["expected_metric"] == "completion_rate"
    assert stored_prediction["prediction_dimensions"]["dimensions"]["trust"]["expected_metric"] == "engagement_rate"


def test_faceless_video_asset_can_bind_back_to_account_experiment(tmp_path):
    store = AgentCoreStore(tmp_path / "faceless-experiment.db")
    lifecycle, project, experiment = _ready_experiment(store)

    result = create_faceless_video_asset(store, {
        "__user_id": "u",
        "account_id": "acct_exp",
        "project_id": project["id"],
        "experiment_id": experiment["id"],
        "objective": "做一条不露脸素材视频，讲 AI 工具内容机会",
        "platforms": ["douyin"],
        "evidence": [
            {"title": "AI 工具内容案例", "url": "https://example.com/ai-tools-video"}
        ],
    })

    assert result["status"] == "ok"
    assert result["experiment_link"]["experiment_id"] == experiment["id"]
    assert result["experiment_link"]["status"] == "running"
    asset = store.get_content_asset(result["asset_id"])
    assert asset["experiment_id"] == experiment["id"]
    assert asset["content"]["experiment_binding"]["experiment_id"] == experiment["id"]
    linked = lifecycle.get_experiment(
        user_id="u", account_id="acct_exp", project_id=project["id"],
        experiment_id=experiment["id"],
    )
    assert linked["status"] == "running"
    assert result["asset_id"] in linked["asset_ids"]


def test_experiment_driven_production_auto_routes_retention_to_faceless_video(tmp_path):
    store = AgentCoreStore(tmp_path / "experiment-faceless.db")
    lifecycle, project, _ = _ready_experiment(store)
    experiment = lifecycle.create_experiment(
        user_id="u", account_id="acct_exp", project_id=project["id"],
        hypothesis="加强前 5 秒后的留存设计能提升完播",
        variable={
            "type": "weight_calibration_experiment",
            "component": "RetentionDesign",
            "direction": "increase",
            "source_strategy_candidate_id": "strategy_retention",
        },
        prediction={"primary_metric": "retention"},
        success_criteria={"primary_metric": "retention", "requires_blind_prediction": True},
    )

    result = create_content_from_experiment(store, {
        "__user_id": "u",
        "account_id": "acct_exp",
        "project_id": project["id"],
        "experiment_id": experiment["id"],
        "kind": "auto",
        "evidence": [
            {"title": "短视频留存公开案例", "url": "https://example.com/retention-case"}
        ],
    })

    assert result["status"] == "ok"
    assert result["kind"] == "faceless_video"
    assert result["asset_result"]["video_status"] == "ready_for_materials"
    asset = store.get_content_asset(result["asset_id"])
    assert asset["type"] == "video"
    assert asset["experiment_id"] == experiment["id"]
    assert asset["content"]["experiment_binding"]["primary_metric"] == "retention"


def test_experiment_driven_production_blocks_premium_until_film_preflight(tmp_path):
    store = AgentCoreStore(tmp_path / "experiment-premium.db")
    _, project, experiment = _ready_experiment(store)

    result = create_content_from_experiment(store, {
        "__user_id": "u",
        "account_id": "acct_exp",
        "project_id": project["id"],
        "experiment_id": experiment["id"],
        "kind": "premium_human_video",
        "evidence": [{"title": "案例", "url": "https://example.com/case"}],
    })

    assert result["status"] == "blocked"
    assert result["kind"] == "premium_human_video"
    assert result["reason"] == "premium_human_video_requires_video_previsualization_project"
    assert result["production_plan"]["kind"] == "premium_human_video"
    assert result["preflight_id"].startswith("preflight_")
    assert result["preflight_status"] == "delegate_to_video_previsualization"
    assert result["preflight_decision"]["selected_lane"] == "premium_human_video"
    assert result["video_previsualization"]["agent"] == "high_end_video_previsualization_agent"
    assert result["video_previsualization"]["required"] is True
    preflights = store.list_preflight_records(account_id="acct_exp")
    assert len(preflights) == 1
    stored = preflights[0]
    assert stored["id"] == result["preflight_id"]
    assert stored["input"]["kind"] == "premium_human_video"
    assert stored["decision"]["selected_lane"] == "premium_human_video"
    assert stored["decision"]["video_previsualization_status"] == "not_run"
    assert store.list_content_assets(account_id="acct_exp") == []


def test_faceless_video_builder_blocks_publish_without_url_evidence():
    payload = build_faceless_video_asset_payload({
        "objective": "做一条不露脸视频讲短视频运营",
        "evidence": [{"title": "没有来源的观点"}],
    })

    assert payload["status"] == "needs_evidence"
    assert payload["content"]["evidence_status"]["ready"] is False
    assert payload["content"]["quality_gates"][0]["status"] == "blocked"
    assert payload["content"]["render_status"] == "not_rendered"


def test_faceless_render_prepare_blocks_until_edl_clips_exist(tmp_path):
    store = AgentCoreStore(tmp_path / "render-blocked.db")
    result = create_faceless_video_asset(store, {
        "objective": "做一条不露脸素材视频",
        "evidence": [{"title": "证据", "url": "https://example.com"}],
    })

    prepared = prepare_faceless_render(store, {"asset_id": result["asset_id"], "project_dir": str(tmp_path)})

    assert prepared["status"] == "blocked"
    assert prepared["reason"] == "edl_clips_missing"
    assert prepared["missing_slots"]


def test_faceless_render_prepare_returns_command_when_inputs_exist(tmp_path):
    store = AgentCoreStore(tmp_path / "render-ready.db")
    project_dir = tmp_path / "project"
    (project_dir / "videos").mkdir(parents=True)
    (project_dir / "videos" / "shot-1.mp4").write_bytes(b"placeholder")
    asset = store.create_content_asset(
        title="可渲染草稿",
        type="video",
        platform="douyin",
        content={
            "production_kind": "faceless_video",
            "edl": {
                "version": 1,
                "fps": 30,
                "resolution": "1080x1920",
                "slots": [
                    {
                        "id": "slot-1",
                        "order": 1,
                        "duration_sec": 2.0,
                        "shot_id": "shot-1",
                        "narration": "测试字幕",
                    }
                ],
                "clips": [{"slot_id": "slot-1", "shot_id": "shot-1"}],
                "subtitles": [{"text": "测试字幕", "start_sec": 0, "end_sec": 2.0}],
            },
        },
    )

    prepared = prepare_faceless_render(store, {
        "asset_id": asset["id"],
        "project_dir": str(project_dir),
        "output_path": str(project_dir / "final" / "out.mp4"),
    })

    assert prepared["status"] == "ready"
    assert prepared["render_status"] == "command_ready_not_executed"
    assert prepared["command"][0] == "ffmpeg"
    assert str(project_dir / "videos" / "shot-1.mp4") in prepared["command"]
    assert prepared["output_path"].endswith("out.mp4")


def test_faceless_animatic_render_creates_local_mp4_and_updates_asset(tmp_path):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("ffmpeg/ffprobe not available")
    store = AgentCoreStore(tmp_path / "animatic.db")
    asset = store.create_content_asset(
        title="样片草稿",
        type="video",
        platform="douyin",
        content={
            "production_kind": "faceless_video",
            "render_status": "not_rendered",
            "edl": {
                "version": 1,
                "fps": 12,
                "resolution": "320x568",
                "slots": [
                    {
                        "id": "slot-1",
                        "order": 1,
                        "duration_sec": 0.5,
                        "shot_id": "shot-1",
                        "narration": "test narration",
                    }
                ],
                "clips": [],
                "subtitles": [{"text": "test narration", "start_sec": 0, "end_sec": 0.5}],
            },
        },
    )

    result = render_faceless_animatic(store, {
        "asset_id": asset["id"],
        "project_dir": str(tmp_path / "render-work"),
    })

    assert result["status"] == "ok"
    assert result["render_status"] == "animatic_rendered"
    assert result["frame_count"] == 1
    assert result["output_path"].endswith("_animatic.mp4")
    assert result["duration_sec"] > 0
    assert (tmp_path / "render-work" / "frames" / "shot-1.png").exists()
    assert (tmp_path / "render-work" / "final" / f"{asset['id']}_animatic.mp4").stat().st_size > 0

    updated = store.get_content_asset(asset["id"])
    assert updated["content"]["render_status"] == "animatic_rendered"
    assert updated["content"]["render_outputs"][0]["kind"] == "animatic"


def test_faceless_image_material_fill_creates_clip_and_unblocks_render(tmp_path):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("ffmpeg/ffprobe not available")
    store = AgentCoreStore(tmp_path / "fill-images.db")
    project_dir = tmp_path / "render-work"
    asset = store.create_content_asset(
        title="授权图片填坑草稿",
        type="video",
        platform="douyin",
        content={
            "production_kind": "faceless_video",
            "video_status": "ready_for_materials",
            "render_status": "not_rendered",
            "shot_list": [{"id": "shot-1", "status": "needs_material"}],
            "licensed_asset_requirements": [{"shot_id": "shot-1", "status": "pending"}],
            "quality_gates": [
                {"name": "事实证据门", "status": "pass"},
                {"name": "版权/来源门", "status": "blocked_until_assets_attached"},
                {"name": "素材适配门", "status": "pending_material_review"},
            ],
            "licensed_assets": [],
            "edl": {
                "version": 1,
                "fps": 12,
                "resolution": "320x568",
                "slots": [
                    {
                        "id": "slot-1",
                        "order": 1,
                        "duration_sec": 0.5,
                        "shot_id": "shot-1",
                        "narration": "test narration",
                    }
                ],
                "clips": [],
                "subtitles": [{"text": "test narration", "start_sec": 0, "end_sec": 0.5}],
                "unfilled_slots": ["slot-1"],
            },
        },
    )
    animatic = render_faceless_animatic(store, {
        "asset_id": asset["id"],
        "project_dir": str(project_dir),
    })
    assert animatic["status"] == "ok"
    source_image = project_dir / "frames" / "shot-1.png"

    filled = fill_faceless_image_materials(store, {
        "asset_id": asset["id"],
        "project_dir": str(project_dir),
        "materials": [
            {
                "slot_id": "slot-1",
                "shot_id": "shot-1",
                "local_path": str(source_image),
                "provider": "pexels",
                "source_url": "https://www.pexels.com/photo/test-image-123/",
                "author": "Pexels Creator",
                "license": "Pexels License",
            }
        ],
    })

    assert filled["status"] == "ok"
    assert filled["filled_count"] == 1
    assert filled["missing_slots"] == []
    assert filled["render_status"] == "clips_ready"
    assert (project_dir / "videos" / "shot-1.mp4").stat().st_size > 0

    updated = store.get_content_asset(asset["id"])
    assert updated["content"]["edl"]["clips"] == [
        {"slot_id": "slot-1", "shot_id": "shot-1", "source_in_sec": 0.0, "source_out_sec": 0.5}
    ]
    assert updated["content"]["edl"]["unfilled_slots"] == []
    assert updated["content"]["licensed_assets"][0]["provider"] == "pexels"
    assert updated["content"]["licensed_assets"][0]["license"] == "Pexels License"
    assert updated["content"]["licensed_asset_requirements"][0]["status"] == "filled"
    assert updated["content"]["shot_list"][0]["status"] == "material_filled"
    assert updated["content"]["quality_gates"][1]["status"] == "pass"

    prepared = prepare_faceless_render(store, {
        "asset_id": asset["id"],
        "project_dir": str(project_dir),
        "output_path": str(project_dir / "final" / "final.mp4"),
    })
    assert prepared["status"] == "ready"
    assert str(project_dir / "videos" / "shot-1.mp4") in prepared["command"]

    audio_dir = project_dir / "audio"
    audio_dir.mkdir(parents=True)
    voice_path = audio_dir / "voice.wav"
    bgm_path = audio_dir / "bgm.wav"
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=0.5",
        "-c:a", "pcm_s16le", str(voice_path),
    ], check=True, capture_output=True)
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=220:duration=0.5",
        "-c:a", "pcm_s16le", str(bgm_path),
    ], check=True, capture_output=True)

    rendered = render_faceless_final(store, {
        "asset_id": asset["id"],
        "project_dir": str(project_dir),
        "output_path": str(project_dir / "final" / "review-cut.mp4"),
        "voiceover_audio_path": str(voice_path),
        "bgm_audio_path": str(bgm_path),
        "voiceover_provenance": {"provider": "user_supplied", "license": "User supplied"},
        "bgm_provenance": {"provider": "pixabay", "source_url": "https://pixabay.com/music/test-bgm/", "license": "Pixabay Content License"},
        "bgm_volume": 0.12,
    })
    assert rendered["status"] == "ok"
    assert rendered["kind"] == "final_review_cut"
    assert rendered["render_status"] == "final_review_cut_rendered"
    assert rendered["subtitles_burned"] is False
    assert rendered["audio_track_count"] == 2
    assert "amix=inputs=2" in " ".join(rendered["command"])
    assert "-an" not in rendered["command"]
    assert (project_dir / "subtitles" / f"{asset['id']}.srt").read_text(encoding="utf-8").startswith("1\n00:00:00,000")
    assert (project_dir / "final" / "review-cut.mp4").stat().st_size > 0
    final_asset = store.get_content_asset(asset["id"])
    assert final_asset["content"]["render_outputs"][-1]["kind"] == "final_review_cut"
    assert final_asset["content"]["render_outputs"][-1]["audio_tracks"][1]["provider"] == "pixabay"
    assert final_asset["content"]["final_review_cut_path"].endswith("review-cut.mp4")


def test_content_production_server_endpoint_returns_work_order():
    pytest.importorskip("fastapi")
    from server import content_production_plan_endpoint

    result = content_production_plan_endpoint({
        "objective": "做一条不露脸视频",
        "platforms": ["douyin"],
    })
    assert result["kind"] == "faceless_video"
    assert result["recommended_next_action"]


def test_initial_plan_routes_content_production_to_work_order_first():
    steps = HermesAgentService._build_initial_plan("帮我写一篇公众号软文", None)
    assert steps[0]["tool_name"] == "marketing_plan_content_production"
    assert steps[1]["tool_name"] == "marketing_draft_content_preflight"
    assert any(step["tool_name"] == "marketing_read_content_list" for step in steps)


def test_initial_plan_routes_experiment_production_to_experiment_tool():
    steps = HermesAgentService._build_initial_plan("根据实验草案继续生产一条内容", None)
    tool_names = [step["tool_name"] for step in steps]
    assert tool_names[0] == "marketing_read_account_experiments"
    assert "marketing_draft_content_from_experiment" in tool_names
    assert tool_names.index("marketing_read_account_experiments") < tool_names.index("marketing_draft_content_from_experiment")
