"""UPGRADE-04 (Q16): Content matrix decomposition — 1→N platform adaptation.

Inspired by HotGloo/ContentStudio's multi-platform content matrix:
  - One creative idea → N platform-specific variants
  - Each variant is adapted for the target platform's format constraints
  - Title length, tag style, content format, and CTA are adjusted per platform

This module provides the adaptation logic. The actual tool registration
happens in tool_manifest.py as a DRAFT_TOOLS entry (L1 reversible write).

Platform adaptation rules:
  douyin:      title ≤ 55 chars, 3-5 hashtags, vertical video, emotional CTA
  bilibili:    title ≤ 80 chars, 5-10 tags, horizontal video, community CTA
  xiaohongshu: title ≤ 20 chars, 5-8 tags, vertical image, lifestyle CTA
  kuaishou:    title ≤ 50 chars, 3-5 tags, vertical video, direct CTA
  zhihu:       title ≤ 100 chars, 0-2 tags, long-form text, analytical CTA
  wechat_official: title ≤ 64 chars, 0-3 tags, long article, trust-building CTA
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PlatformSpec:
    """Platform-specific content constraints and adaptation rules."""

    name: str
    title_max: int
    tag_range: tuple[int, int]  # min, max tags
    tag_prefix: str  # hashtag prefix
    video_orientation: str  # "vertical" | "horizontal" | "any"
    cta_style: str  # recommended CTA style
    content_format: str  # preferred content format
    description: str


PLATFORM_SPECS: dict[str, PlatformSpec] = {
    "douyin": PlatformSpec(
        name="douyin", title_max=55, tag_range=(3, 5), tag_prefix="#",
        video_orientation="vertical", cta_style="emotional",
        content_format="short_video",
        description="抖音：竖屏短视频，情绪驱动，3-5个话题标签",
    ),
    "bilibili": PlatformSpec(
        name="bilibili", title_max=80, tag_range=(5, 10), tag_prefix="",
        video_orientation="horizontal", cta_style="community",
        content_format="long_video",
        description="B站：横屏中长视频，知识/娱乐，5-10个标签",
    ),
    "xiaohongshu": PlatformSpec(
        name="xiaohongshu", title_max=20, tag_range=(5, 8), tag_prefix="#",
        video_orientation="vertical", cta_style="lifestyle",
        content_format="image_text",
        description="小红书：竖屏图文，生活方式，5-8个标签，标题简短",
    ),
    "kuaishou": PlatformSpec(
        name="kuaishou", title_max=50, tag_range=(3, 5), tag_prefix="#",
        video_orientation="vertical", cta_style="direct",
        content_format="short_video",
        description="快手：竖屏短视频，直接接地气，3-5个标签",
    ),
    "zhihu": PlatformSpec(
        name="zhihu", title_max=100, tag_range=(0, 2), tag_prefix="",
        video_orientation="any", cta_style="analytical",
        content_format="long_text",
        description="知乎：长文/视频，分析驱动，0-2个标签",
    ),
    "wechat_official": PlatformSpec(
        name="wechat_official", title_max=64, tag_range=(0, 3), tag_prefix="",
        video_orientation="any", cta_style="trust_conversion",
        content_format="long_article",
        description="微信公众号：长图文/软文，标题克制，结构清晰，强调信任与转化",
    ),
}

CTA_TEMPLATES: dict[str, list[str]] = {
    "emotional": [
        "你觉得呢？评论区告诉我",
        "认同的点赞，不认同的来辩",
        "关注我，带你看懂行业真相",
    ],
    "community": [
        "一键三连支持一下",
        "弹幕告诉我你的看法",
        "关注获取更多深度内容",
    ],
    "trending": [
        "转发让更多人看到",
        "你怎么看？评论区聊聊",
        "关注追踪最新动态",
    ],
    "lifestyle": [
        "收藏备用，下次不迷路",
        "你试过吗？评论区分享",
        "关注获取更多生活灵感",
    ],
    "direct": [
        "双击点赞支持",
        "评论说出你的故事",
        "关注看更多",
    ],
    "analytical": [
        "你怎么看？欢迎讨论",
        "点赞收藏，方便查阅",
        "关注获取更多分析",
    ],
    "trust_conversion": [
        "如果你也在遇到类似问题，可以先收藏这篇，回头按步骤检查",
        "欢迎把你的情况发来，我们可以继续拆解适合你的方案",
        "觉得有帮助的话，也可以转给正在做同类决策的朋友",
    ],
}


def adapt_title(title: str, platform: str) -> str:
    """Adapt title for platform constraints."""
    spec = PLATFORM_SPECS.get(platform)
    if spec is None:
        return title
    if len(title) <= spec.title_max:
        return title
    # Truncate with ellipsis, trying to break at a natural point
    truncated = title[:spec.title_max - 1]
    # Try to break at last space or punctuation
    for i in range(len(truncated) - 1, max(0, len(truncated) - 20), -1):
        if truncated[i] in " ，。！？、；：,!?;:":
            return truncated[:i] + "…"
    return truncated + "…"


def adapt_tags(tags: list[str], platform: str) -> list[str]:
    """Adapt tags for platform constraints."""
    spec = PLATFORM_SPECS.get(platform)
    if spec is None:
        return tags
    min_tags, max_tags = spec.tag_range
    # Ensure within range
    if len(tags) > max_tags:
        tags = tags[:max_tags]
    elif len(tags) < min_tags:
        # Pad with generic platform tags
        generic = {
            "douyin": ["#热门", "#推荐", "#上热门"],
            "bilibili": ["知识", "科普", "科技"],
            "xiaohongshu": ["#生活#", "#日常#", "#分享#"],
            "kuaishou": ["#热门#", "#推荐#"],
            "zhihu": [],
            "wechat_official": [],
        }
        padding = generic.get(platform, [])
        while len(tags) < min_tags and padding:
            tag = padding.pop(0)
            if tag not in tags:
                tags.append(tag)
    # Apply prefix
    if spec.tag_prefix and spec.tag_prefix != "#":
        tags = [t if t.startswith(spec.tag_prefix) else spec.tag_prefix + t for t in tags]
    elif spec.tag_prefix == "#":
        tags = [t if t.startswith("#") else f"#{t}#" if not t.endswith("#") else t for t in tags]
    return tags


def adapt_cta(platform: str, original_cta: str = "") -> str:
    """Generate platform-appropriate CTA."""
    spec = PLATFORM_SPECS.get(platform)
    if spec is None:
        return original_cta
    templates = CTA_TEMPLATES.get(spec.cta_style, [])
    if not templates:
        return original_cta
    # If original CTA is empty or generic, use platform template
    if not original_cta or len(original_cta) < 5:
        return templates[0]
    return original_cta


def decompose_content(
    parent: dict[str, Any],
    platforms: list[str],
) -> list[dict[str, Any]]:
    """Decompose one content asset into N platform-specific variants.

    Args:
        parent: The parent content asset dict with title, content, tags, etc.
        platforms: List of target platform names

    Returns:
        List of platform-adapted variant dicts, each with:
        - platform: target platform
        - parent_id: parent asset ID
        - title: adapted title
        - tags: adapted tags
        - cta: adapted CTA
        - content: original content (unchanged, adaptation is metadata-level)
        - adaptation_notes: what was changed
    """
    # Inline the valid platforms set to avoid cross-module import issues
    VALID_PLATFORMS = frozenset({"douyin", "bilibili", "xiaohongshu", "kuaishou", "zhihu", "wechat_official"})

    original_title = parent.get("title", "")
    original_tags = parent.get("tags", []) or parent.get("content", {}).get("tags", [])
    original_cta = parent.get("cta", "") or parent.get("content", {}).get("cta", "")
    parent_id = parent.get("id")

    variants: list[dict[str, Any]] = []
    seen: set[str] = set()

    for platform in platforms:
        platform = str(platform).strip().lower()
        if platform not in VALID_PLATFORMS:
            continue
        if platform in seen:
            continue
        seen.add(platform)

        spec = PLATFORM_SPECS[platform]
        adapted_title = adapt_title(original_title, platform)
        adapted_tags = adapt_tags(list(original_tags), platform)
        adapted_cta = adapt_cta(platform, original_cta)

        notes: list[str] = []
        if adapted_title != original_title:
            notes.append(f"title truncated to {spec.title_max} chars")
        if len(adapted_tags) != len(original_tags):
            notes.append(f"tags adjusted to {len(adapted_tags)} (range {spec.tag_range[0]}-{spec.tag_range[1]})")
        if adapted_cta != original_cta:
            notes.append(f"CTA adapted to {spec.cta_style} style")

        variant = {
            "platform": platform,
            "parent_id": parent_id,
            "title": adapted_title,
            "tags": adapted_tags,
            "cta": adapted_cta,
            "content": parent.get("content", {}),
            "type": parent.get("type", "script"),
            "adaptation_notes": "; ".join(notes) if notes else "no changes needed",
            "platform_spec": {
                "title_max": spec.title_max,
                "tag_range": list(spec.tag_range),
                "video_orientation": spec.video_orientation,
                "cta_style": spec.cta_style,
                "content_format": spec.content_format,
            },
        }
        variants.append(variant)

    return variants


def get_platform_spec(platform: str) -> PlatformSpec | None:
    """Get the platform specification for a given platform."""
    return PLATFORM_SPECS.get(platform)
