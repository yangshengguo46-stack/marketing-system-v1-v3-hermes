"""Versioned, extensible platform operating profiles for Marketing OS.

The catalog describes content behaviour, not login/browser support.  A user may
plan content for a new or overseas platform before Marketing OS has a native
account connector for it.  Unknown safe platform IDs therefore receive an
explicit generic profile with a research gap instead of being rejected or
silently treated as one of the built-ins.
"""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any


PLATFORM_PROFILE_VERSION = "marketing.platform-profile.v1"
_SAFE_PLATFORM_ID = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,79}$")

PLATFORM_ALIASES = {
    "b站": "bilibili",
    "哔哩哔哩": "bilibili",
    "公众号": "wechat_official",
    "微信公众号": "wechat_official",
    "视频号": "wechat_channels",
    "小红书": "xiaohongshu",
    "抖音": "douyin",
    "快手": "kuaishou",
    "知乎": "zhihu",
    "推特": "x",
    "twitter": "x",
    "领英": "linkedin",
    "油管": "youtube",
}


def _profile(
    *,
    label: str,
    region: str,
    formats: list[str],
    discovery: str,
    audience_intent: str,
    opening: str,
    structure: str,
    interaction: str,
    cta: str,
    visual: str,
) -> dict[str, Any]:
    return {
        "version": PLATFORM_PROFILE_VERSION,
        "label": label,
        "region": region,
        "formats": formats,
        "discovery_mode": discovery,
        "audience_intent": audience_intent,
        "opening_contract": opening,
        "structure_contract": structure,
        "interaction_contract": interaction,
        "cta_contract": cta,
        "visual_contract": visual,
        "guidance_status": "built_in_requires_account_calibration",
    }


PLATFORM_PROFILES: dict[str, dict[str, Any]] = {
    "douyin": _profile(
        label="抖音", region="china", formats=["short_video"],
        discovery="interest_feed_and_completion_signals",
        audience_intent="低意图刷流中快速识别与即时情绪回报",
        opening="首屏直接给冲突、反常识结论或可见结果",
        structure="单一主张，口播与画面高频兑现，先结论后证据",
        interaction="用明确立场或可回答问题触发评论，不做空泛求赞",
        cta="低摩擦关注、评论或看下一条，不在开头硬转化",
        visual="竖屏、人物/证据主体清晰，字幕服务节奏而非堆字",
    ),
    "wechat_official": _profile(
        label="微信公众号", region="china", formats=["long_article"],
        discovery="subscription_relationship_and_social_sharing",
        audience_intent="关系型阅读、系统理解与转发给熟人",
        opening="前 120 字交代处境、冲突和阅读承诺",
        structure="问题—证据—判断框架—行动步骤，允许较深论证",
        interaction="在正文中提供可转述的判断和行动清单",
        cta="低压关注、在看、转发或进入下一篇",
        visual="移动端短段落，封面与关键框架图承担理解锚点",
    ),
    "wechat_channels": _profile(
        label="视频号", region="china", formats=["short_video", "live"],
        discovery="social_graph_plus_recommendation",
        audience_intent="熟人信任迁移与实用信息消费",
        opening="真实人物/场景先建立可信度，再给冲突",
        structure="克制节奏、完整表达、可被转发给具体关系人",
        interaction="邀请分享给需要的人，问题应贴近生活场景",
        cta="关注、转发或进入公众号/直播等关系链动作",
        visual="竖屏清晰、真人可信、避免过强网感包装",
    ),
    "zhihu": _profile(
        label="知乎", region="china", formats=["long_article", "video"],
        discovery="search_questions_and_topic_distribution",
        audience_intent="主动求解、比较观点与验证论证",
        opening="先给结论、适用边界和反方观点",
        structure="结论—依据—反方观点—边界—行动建议",
        interaction="提出可辩论但可证伪的问题，欢迎补充证据",
        cta="讨论型 CTA，弱化私域和销售感",
        visual="论证层级优先，图表只在增强证据时使用",
    ),
    "xiaohongshu": _profile(
        label="小红书", region="china", formats=["image_text", "short_video"],
        discovery="search_plus_interest_feed_and_saves",
        audience_intent="经验检索、身份投射、清单收藏与决策参考",
        opening="标题和首图同时给具体人群、结果或冲突",
        structure="场景—亲历/证据—步骤—避坑，信息可截图收藏",
        interaction="邀请用户补充经历或选择立场，避免模板化提问",
        cta="收藏、评论关键词或关注同系列内容",
        visual="封面信息层级强，图文卡片可独立理解",
    ),
    "bilibili": _profile(
        label="B站", region="china", formats=["video", "long_video"],
        discovery="interest_feed_search_and_community_following",
        audience_intent="主动学习、深度娱乐与系列追更",
        opening="快速证明视频会回答什么，同时展示内容密度",
        structure="章节化论证、案例和可视化演示，允许长铺垫但要兑现",
        interaction="引导弹幕节点、评论补充与系列议题讨论",
        cta="一键三连或关注系列，但先完成价值交付",
        visual="横屏优先，信息图、屏录、案例画面支撑理解",
    ),
    "kuaishou": _profile(
        label="快手", region="china", formats=["short_video", "live"],
        discovery="relationship_and_interest_feed",
        audience_intent="真实生活、稳定人设与关系互动",
        opening="真实场景和人物先行，直接进入生活问题",
        structure="朴素叙事、具体经历、明确结果，减少悬浮概念",
        interaction="围绕真实经验提问并持续回复评论",
        cta="关注后续实践、直播或评论交流",
        visual="真实质感优先，包装不能盖过人物和场景",
    ),
    "tiktok": _profile(
        label="TikTok", region="global", formats=["short_video"],
        discovery="interest_graph_and_fast_retention",
        audience_intent="快速娱乐、身份认同和即时实用价值",
        opening="第一秒可视化冲突或结果，尽量降低语言依赖",
        structure="单一承诺、模式中断、快速证明与循环结尾",
        interaction="用文化语境匹配的立场问题触发评论/二创",
        cta="关注系列、评论观点或观看下一条",
        visual="9:16、强动作和高可读字幕，注意本地化而非直译",
    ),
    "youtube": _profile(
        label="YouTube", region="global", formats=["long_video", "short_video"],
        discovery="search_recommendation_and_returning_viewers",
        audience_intent="主动检索、深度观看和订阅系列",
        opening="标题缩略图承诺必须在开头迅速兑现",
        structure="问题—路线图—证据/演示—反方—结论，重视留存章节",
        interaction="置顶问题、章节评论和社区延伸",
        cta="订阅明确系列、观看相关视频或下载可信资源",
        visual="16:9 长视频或 9:16 Shorts；缩略图只承诺一个信息",
    ),
    "instagram": _profile(
        label="Instagram", region="global", formats=["reel", "carousel", "image"],
        discovery="social_graph_interest_feed_and_saves",
        audience_intent="审美认同、身份表达、灵感收藏和关系互动",
        opening="Reel 首帧或轮播首卡提供鲜明视觉承诺",
        structure="视觉先行，轮播逐卡推进；正文补充语境而非重复画面",
        interaction="Story/评论问题与可分享模板促进关系互动",
        cta="保存、分享、关注系列或进入资料链接",
        visual="强一致视觉系统，兼顾无声观看与移动端安全区",
    ),
    "linkedin": _profile(
        label="LinkedIn", region="global", formats=["text", "document", "video", "article"],
        discovery="professional_graph_and_expertise_signals",
        audience_intent="职业判断、行业学习、信誉和合作机会",
        opening="从职业冲突、数据或亲历决策切入，避免空泛鸡汤",
        structure="观点—业务证据—方法—边界—可执行启发",
        interaction="邀请同行提供反例、实践数据或角色视角",
        cta="讨论、关注专业系列或联系合作，避免强销售",
        visual="文档轮播、简洁图表和真实工作场景优先",
    ),
    "x": _profile(
        label="X", region="global", formats=["short_text", "thread", "video"],
        discovery="follow_graph_reposts_and_realtime_topics",
        audience_intent="实时观点、信息差、公开讨论和网络传播",
        opening="第一句就是可独立传播的判断或新事实",
        structure="单帖单观点；线程逐条增加证据，不把结论藏到最后",
        interaction="引用反方、提问和回复形成公开论证链",
        cta="回复观点、转发或阅读完整线程/来源",
        visual="截图/短视频必须补充信息，不用装饰性海报",
    ),
}


_GENERIC_PROFILE = _profile(
    label="未校准平台", region="unknown", formats=["text", "image", "video", "article"],
    discovery="unknown_requires_research",
    audience_intent="未知；需要平台知识或用户说明",
    opening="先给清楚价值承诺，具体节奏待平台证据校准",
    structure="保留内容内核、证据、边界和行动，格式待校准",
    interaction="只使用可回答且与内容相关的问题",
    cta="使用低风险通用 CTA，待平台规则和账号目标确认",
    visual="输出可重排的通用素材包，不假定尺寸或编辑器能力",
)
_GENERIC_PROFILE["guidance_status"] = "generic_unverified_requires_platform_research"


def normalize_platform_id(value: Any) -> str:
    raw = str(value or "").strip()
    platform = PLATFORM_ALIASES.get(raw, raw.lower().replace(" ", "_"))
    if not _SAFE_PLATFORM_ID.fullmatch(platform):
        raise ValueError(f"unsupported platform identifier: {raw or '<empty>'}")
    return platform


def normalize_platforms(value: Any, *, limit: int = 20) -> list[str]:
    if isinstance(value, str):
        raw = re.split(r"[,，、/\s]+", value)
    elif isinstance(value, (list, tuple, set)):
        raw = list(value)
    else:
        raw = []
    result: list[str] = []
    for item in raw:
        if not str(item or "").strip():
            continue
        platform = normalize_platform_id(item)
        if platform not in result:
            result.append(platform)
        if len(result) > limit:
            raise ValueError(f"platforms exceeds {limit} entries")
    return result


def platform_profile(platform: Any) -> dict[str, Any]:
    platform_id = normalize_platform_id(platform)
    value = deepcopy(PLATFORM_PROFILES.get(platform_id) or _GENERIC_PROFILE)
    value["id"] = platform_id
    if value["label"] == "未校准平台":
        value["label"] = platform_id
    return value


def platform_content_blueprints(platforms: Any) -> dict[str, dict[str, Any]]:
    """Return stable adaptation contracts for every requested platform."""

    result: dict[str, dict[str, Any]] = {}
    for platform in normalize_platforms(platforms):
        profile = platform_profile(platform)
        result[platform] = {
            "platform": platform,
            "profile_version": profile["version"],
            "guidance_status": profile["guidance_status"],
            "recommended_formats": profile["formats"],
            "discovery_mode": profile["discovery_mode"],
            "audience_intent": profile["audience_intent"],
            "opening_contract": profile["opening_contract"],
            "structure_contract": profile["structure_contract"],
            "interaction_contract": profile["interaction_contract"],
            "cta_contract": profile["cta_contract"],
            "visual_contract": profile["visual_contract"],
        }
    return result


def platform_profile_confidence(platform: Any) -> float:
    profile = platform_profile(platform)
    return 0.78 if profile["guidance_status"].startswith("built_in") else 0.38


def content_lane_for_platform(platform: Any) -> str:
    formats = set(platform_profile(platform)["formats"])
    if formats & {"long_article", "article", "text", "short_text", "thread", "document"}:
        return "article_soft"
    return "faceless_video"
