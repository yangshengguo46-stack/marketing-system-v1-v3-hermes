"""Soft-article production chain for Zhihu and WeChat Official Account.

This module is intentionally deterministic, but it is not the writer.  Hermes
supplies the actual parent draft and platform rewrites; this module validates
and persists them.  It never calls an LLM, scrapes the web, or downloads images.
Its job is to turn already-collected context and Agent-authored prose into a
durable ``content_assets`` draft with:

- a parent long-form article draft;
- platform variants for Zhihu and WeChat Official Account;
- evidence and visual requirements;
- an explicit readiness statement that refuses to invent performance numbers.

If authored prose is missing, it stores an explicit writing scaffold and keeps
the asset blocked.  A deterministic template must never masquerade as finished
creative work.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any, TYPE_CHECKING

from .content_lane_gate import (
    attach_asset_to_requested_experiment,
    attach_content_lane_gate,
    attach_experiment_context,
    requested_experiment_context,
    run_content_lane_gate,
)
from .content_feature_snapshot import build_content_feature_snapshot
from .content_matrix import adapt_cta, adapt_tags, adapt_title
from .content_production import build_content_production_plan
from .platform_stylebook import (
    article_platform_publish_packs,
    build_article_publish_pack,
    get_platform_style_profile,
)

if TYPE_CHECKING:
    from .store import AgentCoreStore


ARTICLE_PLATFORMS = ("zhihu", "wechat_official")


def _text(value: Any, *, limit: int | None = None) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit] if limit is not None else text


def _markdown(value: Any, *, limit: int = 40_000) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text[:limit]


def _normalise_platforms(value: Any) -> list[str]:
    if isinstance(value, str):
        raw = re.split(r"[,，、/\s]+", value)
    elif isinstance(value, (list, tuple, set)):
        raw = [str(item) for item in value]
    else:
        raw = []

    alias = {
        "知乎": "zhihu",
        "公众号": "wechat_official",
        "微信公众号": "wechat_official",
        "微信公号": "wechat_official",
    }
    result: list[str] = []
    for item in raw:
        platform = alias.get(item.strip(), item.strip().lower())
        if platform in ARTICLE_PLATFORMS and platform not in result:
            result.append(platform)
    return result or list(ARTICLE_PLATFORMS)


def _topic_terms(objective: str) -> list[str]:
    terms: list[str] = []
    for token in re.findall(r"[A-Za-z][A-Za-z0-9+\-.]{1,24}|[\u4e00-\u9fff]{2,12}", objective):
        if token not in terms and token not in {"帮我", "生成", "制作", "内容", "视频", "文章", "一个", "一条", "软文"}:
            terms.append(token)
    return terms[:6] or ["账号经营", "行业问题", "用户决策"]


def _normalise_evidence(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        for key in ("evidence", "items", "results", "data"):
            nested = value.get(key)
            if isinstance(nested, list):
                value = nested
                break
        else:
            value = [value]
    if not isinstance(value, list):
        value = []

    evidence: list[dict[str, Any]] = []
    for index, item in enumerate(value, start=1):
        if isinstance(item, str):
            title = _text(item, limit=160)
            url = ""
            summary = title
        elif isinstance(item, dict):
            title = _text(item.get("title") or item.get("name") or item.get("headline"), limit=160)
            url = _text(item.get("url") or item.get("source_url") or item.get("link"), limit=1000)
            summary = _text(item.get("summary") or item.get("snippet") or item.get("description") or title, limit=500)
        else:
            continue
        if not title and not summary:
            continue
        evidence.append({
            "id": _text(item.get("id"), limit=80) if isinstance(item, dict) and item.get("id") else f"ev_{index:02d}",
            "title": title or f"证据 {index}",
            "summary": summary or title,
            "url": url,
            "has_url": bool(url),
        })
    return evidence[:12]


def _audience_context(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {
            "target_reader": "尚未确认目标读者",
            "pain_points": [],
            "promise": "待确认内容承诺",
            "cta": "",
            "source": "missing",
        }
    pains = value.get("pain_points") or value.get("pains") or []
    if isinstance(pains, str):
        pains = [pains]
    return {
        "target_reader": _text(value.get("target_reader") or value.get("audience") or value.get("persona") or "尚未确认目标读者", limit=180),
        "pain_points": [_text(item, limit=120) for item in pains if _text(item)][:6],
        "promise": _text(value.get("promise") or value.get("value_promise") or value.get("goal") or "待确认内容承诺", limit=180),
        "cta": _text(value.get("cta") or value.get("conversion_action") or "", limit=180),
        "source": _text(value.get("source") or "user_or_agent_context", limit=80),
    }


def _article_title(topic: str, objective: str) -> str:
    if "？" in objective or "?" in objective:
        return adapt_title(objective.rstrip("？?") + "？", "wechat_official")
    return adapt_title(f"{topic}这件事，普通人真正该先看懂什么", "wechat_official")


def _build_scaffold(*, topic: str, objective: str, evidence: list[dict[str, Any]], audience: dict[str, Any]) -> str:
    target_reader = audience["target_reader"]
    pains = audience["pain_points"] or ["不知道该不该入局", "看见机会但缺少判断框架", "担心被流量带偏"]
    promise = audience["promise"]
    evidence_lines = [
        f"- {item['title']}" + (f"（{item['url']}）" if item.get("url") else "（待补 URL）")
        for item in evidence
    ] or ["- 暂无可回链证据：本文只能作为观点草稿，不能进入发布审核。"]

    return "\n\n".join([
        "# 待 Agent 完成的父稿",
        f"> 目标：{objective}",
        f"> 读者：{target_reader}",
        f"> 内容承诺：{promise}",
        "## 开头钩子\n[用一个可验证的矛盾、具体场景或读者问题开场，禁止虚构数字。]",
        "## 核心判断\n[明确本文主张、适用边界和反方观点。]",
        "## 证据与论证\n" + "\n".join(evidence_lines) + "\n\n[引用证据时使用 [ev_01] 形式，并区分事实与推断。]",
        "## 读者问题\n" + "\n".join(f"{index}. {pain}" for index, pain in enumerate(pains, start=1)),
        f"## 行动建议\n[围绕『{topic}』给出能执行、能验证、不过度承诺的下一步。]",
        "## 结尾与 CTA\n[结合账号目标写自然 CTA，不使用诱导分享或虚假稀缺。]",
    ])


def _authored_variant_map(value: Any) -> dict[str, dict[str, Any]]:
    if isinstance(value, list):
        value = {
            str(item.get("platform") or ""): item
            for item in value if isinstance(item, dict) and item.get("platform")
        }
    return value if isinstance(value, dict) else {}


def _build_variants(
    *, title: str, body: str, topic_terms: list[str], platforms: list[str], cta: str,
    authored_variants: Any = None,
) -> dict[str, dict[str, Any]]:
    supplied = _authored_variant_map(authored_variants)
    variants: dict[str, dict[str, Any]] = {}
    for platform in platforms:
        authored = supplied.get(platform) if isinstance(supplied.get(platform), dict) else {}
        variant_body = _markdown(authored.get("body_markdown") or authored.get("body")) or body
        variant_title = _text(authored.get("title") or title, limit=120)
        origin = "agent_authored" if _markdown(authored.get("body_markdown") or authored.get("body")) else "parent_fallback"
        tags = authored.get("tags") if isinstance(authored.get("tags"), list) else adapt_tags(topic_terms[:4], platform)
        publish_pack = build_article_publish_pack(platform) or {}
        variants[platform] = {
            "platform": platform,
            "title": adapt_title(variant_title, platform),
            "summary": _text(authored.get("summary") or variant_body.replace("#", " "), limit=180),
            "body": variant_body,
            "tags": tags,
            "cta": adapt_cta(platform, _text(authored.get("cta") or cta, limit=180)),
            "draft_origin": origin,
            "format_notes": "知乎更重论证与反驳；公众号更重信任、步骤和转化。" if platform == "wechat_official" else "知乎版需要保留证据链和反方观点，避免硬广。",
            "style_profile": get_platform_style_profile(platform),
            "publish_pack": publish_pack,
        }
    return variants


def _draft_validation(
    *, body: str, evidence: list[dict[str, Any]], variants: dict[str, dict[str, Any]],
    platforms: list[str], authored: bool,
) -> dict[str, Any]:
    body_chars = len(re.sub(r"\s+", "", body))
    heading_count = len(re.findall(r"^#{1,3}\s+", body, flags=re.MULTILINE))
    known_refs = {str(item.get("id")) for item in evidence if item.get("id")}
    cited_refs = set(re.findall(r"\[([A-Za-z0-9_.:-]+)\]", body)) & known_refs
    evidence_requires_citation = any(item.get("has_url") for item in evidence)
    parent_ready = authored and body_chars >= 600 and heading_count >= 3
    citation_ready = not evidence_requires_citation or bool(cited_refs)
    missing_variants = [
        platform for platform in platforms
        if variants.get(platform, {}).get("draft_origin") != "agent_authored"
        or len(re.sub(r"\s+", "", str(variants.get(platform, {}).get("body") or ""))) < 300
    ]
    normalised_parent = re.sub(r"\s+", "", body)
    copied_variants = []
    uncited_variants = []
    normalised_variants: dict[str, str] = {}
    for platform in platforms:
        variant_body = str(variants.get(platform, {}).get("body") or "")
        normalised_variant = re.sub(r"\s+", "", variant_body)
        normalised_variants[platform] = normalised_variant
        if not normalised_variant or not normalised_parent:
            continue
        similarity = SequenceMatcher(None, normalised_parent, normalised_variant).ratio()
        if similarity >= 0.985:
            copied_variants.append(platform)
        variant_refs = set(re.findall(r"\[([A-Za-z0-9_.:-]+)\]", variant_body)) & known_refs
        if evidence_requires_citation and not variant_refs:
            uncited_variants.append(platform)
    duplicate_variant_pairs = []
    for index, platform in enumerate(platforms):
        left = normalised_variants.get(platform, "")
        if not left:
            continue
        for other in platforms[index + 1:]:
            right = normalised_variants.get(other, "")
            if right and SequenceMatcher(None, left, right).ratio() >= 0.985:
                duplicate_variant_pairs.append([platform, other])
    issues: list[str] = []
    if not authored:
        issues.append("agent_parent_draft_missing")
    elif body_chars < 600:
        issues.append("parent_draft_too_short")
    if heading_count < 3:
        issues.append("parent_draft_structure_incomplete")
    if not citation_ready:
        issues.append("evidence_citation_missing")
    if missing_variants:
        issues.append("agent_platform_variants_missing")
    if copied_variants:
        issues.append("platform_variants_copy_parent")
    if duplicate_variant_pairs:
        issues.append("platform_variants_not_distinct")
    if uncited_variants:
        issues.append("platform_evidence_citation_missing")
    return {
        "version": "article-draft-validation-v1",
        "ready": (
            parent_ready
            and citation_ready
            and not missing_variants
            and not copied_variants
            and not duplicate_variant_pairs
            and not uncited_variants
        ),
        "parent_authored": authored,
        "body_char_count": body_chars,
        "heading_count": heading_count,
        "known_evidence_refs": sorted(known_refs),
        "cited_evidence_refs": sorted(cited_refs),
        "missing_platform_variants": missing_variants,
        "copied_platform_variants": copied_variants,
        "duplicate_platform_variant_pairs": duplicate_variant_pairs,
        "uncited_platform_variants": uncited_variants,
        "issues": issues,
    }


def _visual_requirements(topic: str, topic_terms: list[str], evidence_ready: bool, platforms: list[str]) -> list[dict[str, Any]]:
    query = " ".join(topic_terms[:3] or [topic])
    requirements: list[dict[str, Any]] = []
    for platform in platforms:
        pack = build_article_publish_pack(platform) or {}
        cover = pack.get("cover_spec") or {}
        display_name = pack.get("display_name") or platform
        requirements.append({
            "slot": "cover",
            "platform": platform,
            "display_name": display_name,
            "purpose": f"{display_name}封面图，表达主题和问题感，不使用夸张收益承诺",
            "preferred_source": "stock_material",
            "fallback_source": "generated_image",
            "query": f"{query} editorial illustration cover",
            "aspect_ratio": cover.get("primary_ratio"),
            "fallback_ratios": cover.get("fallback_ratios", []),
            "safe_area": cover.get("safe_area"),
            "text_overlay": cover.get("text_overlay"),
            "license_required": True,
            "status": "pending" if evidence_ready else "blocked_until_evidence_ready",
        })
    requirements.append({
            "slot": "inline_framework",
            "platform": "shared",
            "purpose": "正文中的方法框架图，可后续由生图或前端图表生成",
            "preferred_source": "generated_image",
            "fallback_source": "none",
            "query": f"{topic} 判断框架 信息图",
            "license_required": False,
            "status": "optional",
        })
    return requirements


def _prediction(evidence_ready: bool, draft_ready: bool, platforms: list[str], evidence_count: int) -> dict[str, Any]:
    """Return an honest readiness statement, not an invented traffic range."""
    return {
        "prediction_version": "uncalibrated-readiness-v1",
        "calibration_status": "uncalibrated",
        "confidence": "none",
        "expected_outcome": (
            "可进入人工审稿" if evidence_ready and draft_ready
            else "草稿或证据尚未达标，不能进入发布审核"
        ),
        "platforms": platforms,
        "readiness": {
            "evidence_ready": evidence_ready,
            "draft_ready": draft_ready,
            "url_evidence_count": evidence_count,
        },
        "basis": [
            f"evidence_with_url={evidence_count}",
            f"draft_ready={str(draft_ready).lower()}",
            "soft_article_lane",
            "performance_prior_missing",
            "no_publish_without_human_review",
        ],
        "note": "没有该账号、平台和内容类型的真实历史 prior；不输出播放/阅读/互动区间。",
    }


def build_soft_article_asset_payload(params: dict[str, Any] | None = None) -> dict[str, Any]:
    params = dict(params or {})
    objective = _text(params.get("objective") or params.get("brief") or params.get("topic") or "写一篇可审稿软文")
    platforms = _normalise_platforms(params.get("platforms") or params.get("platform"))
    evidence = _normalise_evidence(params.get("evidence") or params.get("evidence_pack"))
    evidence_with_url = [item for item in evidence if item.get("has_url")]
    evidence_ready = bool(evidence_with_url)
    audience = _audience_context(params.get("audience_context") or params.get("account_context"))
    topic_terms = _topic_terms(objective)
    topic = _text(params.get("topic") or topic_terms[0], limit=80)
    title = _text(params.get("title") or _article_title(topic, objective), limit=120)
    authored_body = _markdown(params.get("body_markdown") or params.get("body"))
    body = authored_body or _build_scaffold(
        topic=topic, objective=objective, evidence=evidence, audience=audience,
    )
    cta = audience.get("cta") or "欢迎把你的情况发来，我们可以继续拆解适合你的方案"
    variants = _build_variants(
        title=title, body=body, topic_terms=topic_terms, platforms=platforms, cta=cta,
        authored_variants=params.get("platform_variants"),
    )
    draft_validation = _draft_validation(
        body=body, evidence=evidence, variants=variants, platforms=platforms,
        authored=bool(authored_body),
    )
    draft_ready = bool(draft_validation["ready"])
    if not authored_body:
        article_status = "needs_agent_draft"
    elif not evidence_ready:
        article_status = "needs_evidence"
    elif (
        draft_validation["missing_platform_variants"]
        or draft_validation["copied_platform_variants"]
        or draft_validation["duplicate_platform_variant_pairs"]
    ):
        article_status = "needs_platform_variants"
    elif not draft_ready:
        article_status = "needs_draft_revision"
    else:
        article_status = "ready_for_review"
    hook = _text(params.get("hook") or f"{topic}真正该先看懂什么", limit=120)
    publish_packs = article_platform_publish_packs(platforms)
    visual_requirements = _visual_requirements(topic, topic_terms, evidence_ready, platforms)
    plan = build_content_production_plan({
        "objective": objective,
        "kind": "article_soft",
        "platforms": platforms,
        "account_id": params.get("account_id"),
    })
    prediction = _prediction(evidence_ready, draft_ready, platforms, len(evidence_with_url))
    feature_snapshot = build_content_feature_snapshot(
        kind="article_soft",
        objective=objective,
        title=title,
        topic=topic,
        hook=hook,
        account_id=params.get("account_id"),
        platforms=platforms,
        audience_context=audience,
        evidence=evidence,
        structure={
            "format": "long_form_article",
            "section_count": len(re.findall(r"^## ", body, flags=re.MULTILINE)),
            "sections": re.findall(r"^##\s+(.+)$", body, flags=re.MULTILINE),
            "body_char_count": len(body),
            "variant_count": len(variants),
            "draft_origin": "agent_authored" if authored_body else "writing_scaffold",
            "draft_ready": draft_ready,
            "visual_requirement_count": len(visual_requirements),
            "platform_variant_titles": {
                platform: variant.get("title")
                for platform, variant in variants.items()
            },
        },
        platform_context={
            "publish_pack_platforms": list(publish_packs),
            "primary_platform": platforms[0] if platforms else None,
        },
        scores={},
        prediction=prediction,
        risks=[
            *([] if evidence_ready else ["needs_url_evidence"]),
            *draft_validation["issues"],
            "manual_review_required",
            "visual_license_pending",
        ],
    )

    return {
        "status": article_status,
        "title": title,
        "topic": topic,
        "hook": hook,
        "platform": platforms[0] if len(platforms) == 1 else "multi_article",
        "type": "script",
        "content": {
            "production_kind": "article_soft",
            "objective": objective,
            "target_platforms": platforms,
            "article_status": article_status,
            "evidence_status": {
                "ready": evidence_ready,
                "required": True,
                "with_url": len(evidence_with_url),
                "total": len(evidence),
                "message": "证据可进入审稿" if evidence_ready else "缺少带 URL 的证据，发布前必须补齐",
            },
            "audience_context": audience,
            "parent_draft": {
                "title": title,
                "body": body,
                "draft_origin": "agent_authored" if authored_body else "writing_scaffold",
                "tags": topic_terms,
                "cta": cta,
            },
            "draft_validation": draft_validation,
            "platform_variants": variants,
            "platform_publish_packs": publish_packs,
            "evidence_refs": evidence,
            "visual_requirements": visual_requirements,
            "quality_gates": [
                {"name": "事实证据门", "status": "pass" if evidence_ready else "blocked"},
                {"name": "Agent 父稿门", "status": "pass" if authored_body else "blocked"},
                {
                    "name": "证据引用门",
                    "status": "pass" if not evidence_ready or (
                        draft_validation["cited_evidence_refs"]
                        and not draft_validation["uncited_platform_variants"]
                    ) else "blocked",
                },
                {
                    "name": "平台改写门",
                    "status": "pass" if not (
                        draft_validation["missing_platform_variants"]
                        or draft_validation["copied_platform_variants"]
                        or draft_validation["duplicate_platform_variant_pairs"]
                    ) else "blocked",
                },
                {"name": "平台语气门", "status": "pending_human_review"},
                {"name": "配图授权门", "status": "pending_when_visual_attached"},
                {"name": "记忆边界门", "status": "pass", "note": "完整草稿只保存到 content_assets"},
            ],
            "production_plan": plan,
            "pre_review_scores": {},
            "pre_publish_prediction": prediction,
            "feature_snapshot": feature_snapshot,
        },
        "scores": {},
        "prediction": prediction,
    }


def create_soft_article_asset(store: "AgentCoreStore", params: dict[str, Any] | None = None) -> dict[str, Any]:
    params = dict(params or {})
    experiment_context = requested_experiment_context(store, params)
    gate = run_content_lane_gate(store, params, kind="article_soft")
    payload = build_soft_article_asset_payload(params)
    draft_status = payload["status"]
    payload["content"] = attach_content_lane_gate(payload["content"], gate)
    payload["content"] = attach_experiment_context(payload["content"], experiment_context)
    if not gate["go"]:
        payload["status"] = gate["status"]
        payload["content"]["article_status"] = gate["status"]
    payload["content"]["draft_status"] = draft_status
    asset = store.create_content_asset(
        title=payload["title"],
        type=payload["type"],
        user_id=str(params.get("__user_id", "default")),
        account_id=params.get("account_id"),
        platform=payload["platform"],
        content=payload["content"],
        topic=payload["topic"],
        hook=payload["hook"],
    )
    experiment_link = attach_asset_to_requested_experiment(
        store, experiment_context, asset_id=asset["id"],
    )
    ready_for_review = gate["go"] and draft_status == "ready_for_review"
    return {
        "status": "ok" if ready_for_review else "blocked",
        "asset_id": asset["id"],
        "title": asset["title"],
        "article_status": payload["status"],
        "draft_status": draft_status,
        "preflight_id": gate["preflight_id"],
        "production_gate": gate,
        "target_platforms": payload["content"]["target_platforms"],
        "evidence_status": payload["content"]["evidence_status"],
        "variant_count": len(payload["content"]["platform_variants"]),
        "visual_requirements": payload["content"]["visual_requirements"],
        "experiment_link": experiment_link,
        "review": None,
        "review_status": "human_review_required" if ready_for_review else "blocked_until_draft_ready",
        "prediction_status": "not_created_before_human_review",
    }
