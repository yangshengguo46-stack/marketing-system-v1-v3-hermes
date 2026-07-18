from agent.marketing.domains import ContentProductionPolicy
from agent.marketing.intelligence import build_content_production_preflight
from agent.marketing.platform_catalog import platform_content_blueprints


def _ready_account_context():
    return {
        "account_id": "acct-main",
        "connected": True,
        "lifecycle": {
            "stage": "operating",
            "positioning": {"promise": "用证据解释 AI 产业变化"},
            "content_system": {"pillars": ["AI 判断"]},
            "strategy_alignment": {
                "positioning_current": True,
                "content_system_current": True,
            },
            "audience_hypothesis": {"segments": ["关注 AI 的知识工作者"]},
        },
    }


def test_cross_platform_plan_is_not_limited_to_a_fixed_domestic_pair():
    platforms = [
        "douyin",
        "wechat_official",
        "youtube",
        "linkedin",
        "mastodon",
    ]
    plan = ContentProductionPolicy().plan(
        objective="当前的 AI 是泡沫吗？为每个平台制作原生内容",
        platforms=platforms,
        audience="关注 AI 产业变化的知识工作者",
        evidence_refs=["evidence_report"],
        account_context=_ready_account_context(),
    )

    assert plan["kind"] == "cross_platform_campaign"
    assert plan["target_platforms"] == platforms
    assert set(plan["platform_blueprints"]) == set(platforms)
    assert plan["platform_blueprints"]["douyin"]["opening_contract"] != plan[
        "platform_blueprints"
    ]["wechat_official"]["opening_contract"]
    assert plan["platform_blueprints"]["mastodon"]["guidance_status"] == (
        "generic_unverified_requires_platform_research"
    )


def test_unknown_platform_degrades_honestly_and_preflight_keeps_per_platform_evidence():
    plan = ContentProductionPolicy().plan(
        objective="同一选题跨平台制作",
        kind="cross_platform_campaign",
        platforms=["xiaohongshu", "instagram", "future_social"],
        audience="正在评估 AI 工具的独立创作者",
        evidence_refs=["evidence_report"],
        account_context=_ready_account_context(),
    )
    preflight = build_content_production_preflight(
        {"plan": plan, "evidence_refs": ["evidence_report"]}
    )

    assert set(preflight["platform_assessments"]) == {
        "xiaohongshu",
        "instagram",
        "future_social",
    }
    assert "platform_guidance_unverified:future_social" in preflight[
        "preflight_decision"
    ]["warnings"]
    assert preflight["platform_assessments"]["future_social"]["fit"] < preflight[
        "platform_assessments"
    ]["instagram"]["fit"]


def test_platform_blueprints_accept_chinese_aliases_and_overseas_targets():
    blueprints = platform_content_blueprints(["抖音", "公众号", "twitter", "youtube"])

    assert set(blueprints) == {"douyin", "wechat_official", "x", "youtube"}


def test_a_single_overseas_article_platform_uses_the_extensible_campaign_contract():
    plan = ContentProductionPolicy().plan(
        objective="为 LinkedIn 写一篇关于 AI 泡沫的职业判断",
        platforms=["linkedin"],
        audience="企业 AI 决策者",
        evidence_refs=["evidence_report"],
        account_context=_ready_account_context(),
    )

    assert plan["kind"] == "cross_platform_campaign"
    assert plan["target_platforms"] == ["linkedin"]
