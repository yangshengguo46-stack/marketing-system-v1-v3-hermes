"""Platform-level publishing stylebook for article/image-text production.

The content matrix knows *what* form a platform prefers: long article, short
video, tags, CTA, etc.  This module is one layer lower and more practical: it
describes the editor-facing publishing pack required to make a draft feel
native on a platform.

Important distinction:

- ``hard_rules`` are stable platform/API constraints or compliance boundaries.
- ``best_practices`` are operational editing conventions.  They should guide
  generation and review, but must not be presented as official platform law.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


STYLEBOOK_VERSION = "2026-07-09.article-v1"


PLATFORM_STYLE_PROFILES: dict[str, dict[str, Any]] = {
    "wechat_official": {
        "platform": "wechat_official",
        "display_name": "微信公众号",
        "content_kind": "long_article",
        "version": STYLEBOOK_VERSION,
        "confidence": "medium",
        "source_policy": {
            "hard_rules": "微信公众平台/服务号发布、草稿箱、素材管理接口与平台规范",
            "best_practices": "公众号编辑排版经验；需随账号行业和历史数据继续校准",
        },
        "hard_rules": [
            "发布前必须具备封面素材、正文和标题；走官方发布/草稿接口时应保留素材 media_id 或可追溯素材记录。",
            "正文引用数据、案例和第三方材料时必须保留来源；图片素材必须有授权来源或生成参数。",
            "营销软文必须避免绝对化收益承诺、虚假背书、夸大疗效/财富结果等高风险表达。",
        ],
        "typography": {
            "editor_mode": "rich_text_html",
            "body_font_family": "system_sans",
            "body_font_size_px": [15, 16],
            "heading_font_size_px": [18, 20],
            "caption_font_size_px": [12, 13],
            "line_height": [1.75, 2.0],
            "paragraph_spacing_px": [12, 18],
            "text_color": "#3f3f3f",
            "muted_text_color": "#888888",
            "emphasis_color_policy": "1 accent color only; avoid rainbow formatting",
            "note": "字号、行距属于排版建议，不是官方硬限制；最终以公众号编辑器预览为准。",
        },
        "visual": {
            "cover": {
                "required": True,
                "primary_ratio": "2.35:1",
                "fallback_ratios": ["16:9", "1:1 share-safe crop"],
                "safe_area": "关键文字和人物脸部放在中心 70% 区域，避免列表页/分享页裁切。",
                "text_overlay": "不超过 12 个中文大字；优先问题感/结论感，不堆关键词。",
                "style": "editorial illustration or clean data/scene composite",
            },
            "inline_images": {
                "recommended_count": [1, 4],
                "width_policy": "full-width readable image; keep original source/license/hash",
                "preferred_slots": ["opening_context", "framework_diagram", "case_or_data"],
            },
        },
        "structure": {
            "opening": "前 120 字交代读者处境、冲突和本文承诺。",
            "sections": ["问题", "证据", "判断框架", "行动步骤", "轻 CTA"],
            "paragraph_policy": "单段 80-160 字，避免大段墙。",
            "cta_policy": "收藏/转发/私信咨询等低压转化；不要在正文中过早硬广。",
        },
        "review_checklist": [
            "标题是否克制且承诺清楚",
            "封面是否在移动端列表里一眼能懂",
            "正文是否有证据 URL 或可追溯来源",
            "是否有授权图片/生成参数记录",
            "是否存在夸大收益或诱导焦虑",
        ],
    },
    "zhihu": {
        "platform": "zhihu",
        "display_name": "知乎",
        "content_kind": "long_text",
        "version": STYLEBOOK_VERSION,
        "confidence": "medium",
        "source_policy": {
            "hard_rules": "知乎社区规范、内容治理和编辑器能力",
            "best_practices": "知乎长文/回答运营经验；需按话题和账号权重继续校准",
        },
        "hard_rules": [
            "不要伪造经历、数据、来源或专家身份；事实性判断必须能回链。",
            "避免低质营销、引流灌水、标题党和与问题无关的硬广。",
            "知乎回答/文章优先尊重平台编辑器默认样式，不依赖自定义字体 CSS。",
        ],
        "typography": {
            "editor_mode": "platform_default_markdown_rich_text",
            "body_font_family": "platform_default",
            "body_font_size_px": "platform_controlled",
            "heading_level_policy": "use H2/H3 sparingly for logical sections",
            "line_height": "platform_controlled",
            "paragraph_spacing_policy": "short paragraphs; 2-4 sentences each",
            "quote_policy": "use blockquote only for sourced quotes or反方观点",
            "note": "知乎字体和行高主要由平台编辑器控制；我们的重点是结构、证据和可读性。",
        },
        "visual": {
            "cover": {
                "required": False,
                "primary_ratio": "16:9",
                "fallback_ratios": ["4:3", "1:1"],
                "safe_area": "如果作为文章封面使用，核心信息居中；回答场景可不强制封面。",
                "text_overlay": "尽量少字；知乎用户更反感营销海报感。",
                "style": "evidence chart, clean diagram, or understated editorial image",
            },
            "inline_images": {
                "recommended_count": [0, 3],
                "width_policy": "only use images that strengthen evidence or explanation",
                "preferred_slots": ["data_chart", "framework_diagram", "source_screenshot_if_allowed"],
            },
        },
        "structure": {
            "opening": "先给结论，再说明边界；避免一上来卖课/卖服务。",
            "sections": ["结论", "依据", "反方观点", "适用边界", "行动建议"],
            "paragraph_policy": "论证密度优先；每段只讲一个判断。",
            "cta_policy": "讨论型 CTA；弱化私域引导，避免硬广感。",
        },
        "review_checklist": [
            "开头是否先给清楚结论",
            "核心判断是否有证据链",
            "是否写了适用边界和反方观点",
            "是否像广告软文而不是认真回答",
            "图片是否真的辅助论证",
        ],
    },
}


def get_platform_style_profile(platform: str) -> dict[str, Any] | None:
    """Return a deep-copied style profile for a platform."""

    profile = PLATFORM_STYLE_PROFILES.get(str(platform or "").strip().lower())
    return deepcopy(profile) if profile else None


def build_article_publish_pack(platform: str) -> dict[str, Any] | None:
    """Build a compact publish pack consumed by content assets and review UI."""

    profile = get_platform_style_profile(platform)
    if profile is None:
        return None
    visual = profile["visual"]
    cover = visual["cover"]
    typography = profile["typography"]
    return {
        "platform": profile["platform"],
        "display_name": profile["display_name"],
        "stylebook_version": profile["version"],
        "content_kind": profile["content_kind"],
        "cover_spec": {
            "required": cover["required"],
            "primary_ratio": cover["primary_ratio"],
            "fallback_ratios": cover["fallback_ratios"],
            "safe_area": cover["safe_area"],
            "text_overlay": cover["text_overlay"],
            "style": cover["style"],
        },
        "typography_spec": typography,
        "structure_spec": profile["structure"],
        "review_checklist": profile["review_checklist"],
        "source_policy": profile["source_policy"],
    }


def article_platform_publish_packs(platforms: list[str]) -> dict[str, dict[str, Any]]:
    """Return publish packs for known article platforms, preserving order."""

    packs: dict[str, dict[str, Any]] = {}
    for platform in platforms:
        pack = build_article_publish_pack(platform)
        if pack:
            packs[pack["platform"]] = pack
    return packs
