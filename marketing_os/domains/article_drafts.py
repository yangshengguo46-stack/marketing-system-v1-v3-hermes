"""Deterministic validation for Agent-authored long-form article bundles."""

from __future__ import annotations

import re
from copy import deepcopy
from difflib import SequenceMatcher
from typing import Any


ARTICLE_STYLEBOOK_VERSION = "2026-07-10.hermes-native-v1"

ARTICLE_STYLEBOOKS: dict[str, dict[str, Any]] = {
    "wechat_official": {
        "platform": "wechat_official",
        "display_name": "微信公众号",
        "version": ARTICLE_STYLEBOOK_VERSION,
        "guidance_status": "operational_guidance_requires_account_calibration",
        "typography": {
            "editor_mode": "rich_text_html",
            "body_font_size_px": [15, 16],
            "heading_font_size_px": [18, 20],
            "caption_font_size_px": [12, 13],
            "line_height": [1.75, 2.0],
            "paragraph_spacing_px": [12, 18],
            "body_color": "#3f3f3f",
            "accent_policy": "one restrained accent color",
            "disclaimer": "这些是移动端可读性建议，不是微信官方硬限制；最终以编辑器预览为准。",
        },
        "cover": {
            "required": True,
            "primary_ratio": "2.35:1",
            "fallback_ratios": ["16:9", "1:1 share-safe crop"],
            "safe_area": "关键文字和主体位于中心 70% 区域",
            "text_overlay": "不超过 12 个中文大字",
        },
        "structure": {
            "opening": "前 120 字说明读者处境、冲突和阅读承诺",
            "sections": ["问题", "证据", "判断框架", "行动步骤", "轻 CTA"],
            "paragraph_policy": "短段落优先，单段通常 80-160 字",
            "cta_policy": "低压转化，不在正文中过早硬广",
        },
        "review": [
            "标题是否克制且承诺清楚",
            "证据是否能回链",
            "图片是否有来源或生成记录",
            "是否存在夸大收益、虚假背书或诱导焦虑",
        ],
    },
    "zhihu": {
        "platform": "zhihu",
        "display_name": "知乎",
        "version": ARTICLE_STYLEBOOK_VERSION,
        "guidance_status": "operational_guidance_requires_account_calibration",
        "typography": {
            "editor_mode": "platform_default_markdown_rich_text",
            "body_font_size_px": "platform_controlled",
            "heading_policy": "用 H2/H3 表达论证层级，避免标题堆叠",
            "paragraph_policy": "每段只讲一个判断，通常 2-4 句",
            "quote_policy": "引用块只用于有来源的引用或反方观点",
            "disclaimer": "字体和行高由知乎编辑器控制，产品只约束结构、证据和可读性。",
        },
        "cover": {
            "required": False,
            "primary_ratio": "16:9",
            "fallback_ratios": ["4:3", "1:1"],
            "safe_area": "文章封面核心信息居中；回答场景不强制封面",
            "text_overlay": "少字，避免营销海报感",
        },
        "structure": {
            "opening": "先给结论与边界，避免一上来销售",
            "sections": ["结论", "依据", "反方观点", "适用边界", "行动建议"],
            "paragraph_policy": "论证密度优先，每段只讲一个判断",
            "cta_policy": "讨论型 CTA，弱化私域引导",
        },
        "review": [
            "开头是否先给清楚结论",
            "核心判断是否有证据链",
            "是否写明适用边界和反方观点",
            "是否像认真回答而不是广告软文",
        ],
    },
}


def article_stylebooks(platforms: list[str]) -> dict[str, dict[str, Any]]:
    return {
        platform: deepcopy(ARTICLE_STYLEBOOKS[platform])
        for platform in platforms
        if platform in ARTICLE_STYLEBOOKS
    }


class ArticleDraftValidator:
    def build_bundle(
        self,
        *,
        title: str,
        parent_body_markdown: str,
        target_platforms: list[str],
        variants: Any,
        evidence_records: list[dict[str, Any]],
        topic: str = "",
        hook: str = "",
    ) -> dict[str, Any]:
        title_value = _text(title, 300, required=True)
        parent_body = _markdown(parent_body_markdown, 100_000)
        if not parent_body:
            raise ValueError("parent_body_markdown is required")
        platforms = [item for item in target_platforms if item in ARTICLE_STYLEBOOKS]
        if not platforms or len(platforms) != len(target_platforms):
            raise ValueError("article plan contains unsupported platforms")
        supplied = variants if isinstance(variants, dict) else {}
        unsupported_variants = sorted(set(supplied) - set(platforms))
        if unsupported_variants:
            raise ValueError(
                "platform_variants contains platforms outside the production plan: "
                + ", ".join(unsupported_variants)
            )
        evidence_ids = [str(item["id"]) for item in evidence_records]
        known_evidence = set(evidence_ids)

        normalized_variants: dict[str, dict[str, Any]] = {}
        for platform in platforms:
            raw = supplied.get(platform) if isinstance(supplied.get(platform), dict) else {}
            body = _markdown(raw.get("body_markdown") or raw.get("body"), 100_000)
            normalized_variants[platform] = {
                "platform": platform,
                "title": _text(raw.get("title") or title_value, 300, required=True),
                "summary": _text(raw.get("summary"), 500),
                "body_markdown": body,
                "tags": _string_list(raw.get("tags"), 12, 80),
                "cta": _text(raw.get("cta"), 500),
                "stylebook_version": ARTICLE_STYLEBOOK_VERSION,
            }

        validation = _validate_bundle(
            parent_body=parent_body,
            variants=normalized_variants,
            platforms=platforms,
            known_evidence=known_evidence,
        )
        stylebooks = article_stylebooks(platforms)
        visual_requirements = [
            {
                "slot": "cover",
                "platform": platform,
                "status": "required" if stylebooks[platform]["cover"]["required"] else "optional",
                "spec": deepcopy(stylebooks[platform]["cover"]),
                "provenance_required": True,
            }
            for platform in platforms
        ]
        visual_requirements.append(
            {
                "slot": "inline_framework",
                "platform": "shared",
                "status": "optional",
                "purpose": "只在能增强解释或证据时加入框架图/数据图",
                "provenance_required": True,
            }
        )
        return {
            "schema": "marketing.article_bundle.v1",
            "review_status": "ready_for_human_review" if validation["ready"] else "needs_revision",
            "topic": _text(topic, 300),
            "hook": _text(hook, 500),
            "parent_draft": {
                "title": title_value,
                "body_markdown": parent_body,
                "draft_origin": "agent_authored",
            },
            "platform_variants": normalized_variants,
            "evidence_pack": [
                {
                    "evidence_id": item["id"],
                    "title": item.get("title") or "",
                    "canonical_url": item.get("canonical_url") or "",
                    "captured_at": item.get("captured_at") or "",
                    "content_sha256": item.get("content_sha256") or "",
                    "verification_level": item.get("verification_level") or "",
                }
                for item in evidence_records
            ],
            "validation": validation,
            "platform_stylebooks": stylebooks,
            "visual_requirements": visual_requirements,
            "prediction": {
                "calibration_status": "uncalibrated",
                "expected_outcome": (
                    "可进入人工审稿" if validation["ready"] else "需要修改后再审稿"
                ),
                "traffic_range": None,
                "note": "没有账号级真实先验时不输出阅读量、互动率或转化区间。",
            },
        }


def _validate_bundle(
    *,
    parent_body: str,
    variants: dict[str, dict[str, Any]],
    platforms: list[str],
    known_evidence: set[str],
) -> dict[str, Any]:
    issues: list[str] = []
    parent_chars = _content_chars(parent_body)
    parent_headings = len(re.findall(r"^#{1,3}\s+", parent_body, flags=re.MULTILINE))
    parent_citations = _citations(parent_body)
    unknown_parent_citations = sorted(parent_citations - known_evidence)
    uncited_provenance = sorted(known_evidence - parent_citations)
    if parent_chars < 800:
        issues.append("parent_draft_too_short")
    if parent_headings < 3:
        issues.append("parent_draft_structure_incomplete")
    if not parent_citations:
        issues.append("parent_evidence_citation_missing")
    if unknown_parent_citations:
        issues.append("parent_contains_unknown_evidence")
    if uncited_provenance:
        issues.append("parent_has_uncited_evidence_refs")

    missing_variants: list[str] = []
    short_variants: list[str] = []
    uncited_variants: list[str] = []
    unknown_variant_citations: dict[str, list[str]] = {}
    copied_parent: list[str] = []
    normalized_parent = _similarity_text(parent_body)
    normalized_bodies: dict[str, str] = {}
    for platform in platforms:
        body = str(variants.get(platform, {}).get("body_markdown") or "")
        normalized = _similarity_text(body)
        normalized_bodies[platform] = normalized
        if not body:
            missing_variants.append(platform)
            continue
        if _content_chars(body) < 500:
            short_variants.append(platform)
        citations = _citations(body)
        if not citations:
            uncited_variants.append(platform)
        unknown = sorted(citations - known_evidence)
        if unknown:
            unknown_variant_citations[platform] = unknown
        if normalized_parent and SequenceMatcher(None, normalized_parent, normalized).ratio() >= 0.97:
            copied_parent.append(platform)

    duplicate_pairs: list[list[str]] = []
    for index, platform in enumerate(platforms):
        left = normalized_bodies.get(platform) or ""
        if not left:
            continue
        for other in platforms[index + 1 :]:
            right = normalized_bodies.get(other) or ""
            if right and SequenceMatcher(None, left, right).ratio() >= 0.97:
                duplicate_pairs.append([platform, other])
    if missing_variants:
        issues.append("platform_variants_missing")
    if short_variants:
        issues.append("platform_variants_too_short")
    if uncited_variants:
        issues.append("platform_evidence_citation_missing")
    if unknown_variant_citations:
        issues.append("platform_contains_unknown_evidence")
    if copied_parent:
        issues.append("platform_variants_copy_parent")
    if duplicate_pairs:
        issues.append("platform_variants_not_distinct")

    return {
        "version": "marketing.article_validation.v1",
        "ready": not issues,
        "issues": issues,
        "parent_char_count": parent_chars,
        "parent_heading_count": parent_headings,
        "known_evidence_refs": sorted(known_evidence),
        "parent_cited_evidence_refs": sorted(parent_citations & known_evidence),
        "unknown_parent_citations": unknown_parent_citations,
        "uncited_provenance_refs": uncited_provenance,
        "missing_platform_variants": missing_variants,
        "short_platform_variants": short_variants,
        "uncited_platform_variants": uncited_variants,
        "unknown_platform_citations": unknown_variant_citations,
        "copied_parent_variants": copied_parent,
        "duplicate_platform_variant_pairs": duplicate_pairs,
        "pending_human_checks": [
            "platform tone and account fit",
            "claim meaning matches cited evidence",
            "visual rights and preview",
            "compliance and sensitive-domain review",
        ],
    }


def _citations(value: str) -> set[str]:
    return set(re.findall(r"\[(evidence_[0-9a-f]{28})\]", value))


def _content_chars(value: str) -> int:
    return len(re.sub(r"[\s#*_>`~-]+", "", value))


def _similarity_text(value: str) -> str:
    return re.sub(r"\s+", "", value).lower()


def _markdown(value: Any, limit: int) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    if len(text.encode("utf-8")) > limit:
        raise ValueError(f"markdown exceeds {limit} bytes")
    return text


def _text(value: Any, limit: int, *, required: bool = False) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if required and not text:
        raise ValueError("required text is missing")
    if len(text) > limit:
        raise ValueError(f"text exceeds {limit} characters")
    return text


def _string_list(value: Any, count_limit: int, item_limit: int) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("tags must be a list")
    result: list[str] = []
    for item in value:
        text = _text(item, item_limit)
        if text and text not in result:
            result.append(text)
    if len(result) > count_limit:
        raise ValueError(f"tags exceeds {count_limit} items")
    return result
