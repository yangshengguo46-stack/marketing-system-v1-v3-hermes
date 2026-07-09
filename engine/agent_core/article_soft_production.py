"""Soft-article production chain for Zhihu and WeChat Official Account.

This module is intentionally deterministic.  It does not call an LLM, scrape
the web, or download images.  Its job is to turn already-collected context into
a durable, reviewable ``content_assets`` draft with:

- a parent long-form article draft;
- platform variants for Zhihu and WeChat Official Account;
- evidence and visual requirements;
- a pre-publish scoring/prediction packet.

The Hermes agent can still do higher-level creative writing around it, but this
module gives the product a reliable closure point: content production no longer
ends at a plan.
"""

from __future__ import annotations

import re
from typing import Any, TYPE_CHECKING

from .content_lane_gate import (
    attach_asset_to_requested_experiment,
    attach_content_lane_gate,
    attach_experiment_context,
    gate_result_status,
    requested_experiment_context,
    run_content_lane_gate,
)
from .content_matrix import adapt_cta, adapt_tags, adapt_title
from .content_production import build_content_production_plan
from .learning_pipeline import review_content_asset
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
            "id": f"ev_{index:02d}",
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


def _build_body(*, topic: str, objective: str, evidence: list[dict[str, Any]], audience: dict[str, Any]) -> str:
    target_reader = audience["target_reader"]
    pains = audience["pain_points"] or ["不知道该不该入局", "看见机会但缺少判断框架", "担心被流量带偏"]
    promise = audience["promise"]
    evidence_lines = [
        f"- {item['title']}" + (f"（{item['url']}）" if item.get("url") else "（待补 URL）")
        for item in evidence
    ] or ["- 暂无可回链证据：本文只能作为观点草稿，不能进入发布审核。"]

    return "\n\n".join([
        f"## 开头：先把问题说清楚\n{target_reader}在看『{topic}』时，最容易被两个东西带偏：一个是短期热度，一个是别人包装好的确定性。真正值得先做的，不是马上跟风，而是确认这件事和自己的目标、资源、风险承受能力有没有关系。",
        f"## 为什么现在值得讨论\n用户原始目标：{objective}\n\n这篇内容的承诺是：{promise}。如果这个承诺还没有被账号定位确认，发布前必须先补定位或把语气改成探索。",
        "## 已有证据\n" + "\n".join(evidence_lines),
        "## 读者最可能卡住的地方\n" + "\n".join(f"{index}. {pain}" for index, pain in enumerate(pains, start=1)),
        f"## 一个更稳的判断框架\n第一，看它解决的是不是长期问题，而不是只看今天的热搜。\n第二，看你能不能连续输出 30 天相关内容，而不是只蹭一次流量。\n第三，看它能不能和你的真实经历、技能、服务对象连接起来。\n\n放到『{topic}』上，如果这三点都回答不上来，就先不要急着把它当账号主线；可以做成一次内容实验，用真实反馈来判断。",
        "## 可以怎么行动\n1. 先把目标用户写成一句话。\n2. 再选 3 个对标账号，拆他们解决的具体问题。\n3. 最后只做一条内容验证一个假设：标题、开头、证据、CTA 都只服务这个假设。",
        f"## 结尾与 CTA\n如果你也在判断『{topic}』是不是适合自己，先别急着套模板。把你的行业、目标用户和现有资源列出来，我们可以继续把它拆成一个可验证的账号方向。",
    ])


def _build_variants(*, title: str, body: str, topic_terms: list[str], platforms: list[str], cta: str) -> dict[str, dict[str, Any]]:
    variants: dict[str, dict[str, Any]] = {}
    for platform in platforms:
        tags = adapt_tags(topic_terms[:4], platform)
        publish_pack = build_article_publish_pack(platform) or {}
        variants[platform] = {
            "platform": platform,
            "title": adapt_title(title, platform),
            "summary": _text(body.replace("#", "").replace("\n", " "), limit=180),
            "body": body,
            "tags": tags,
            "cta": adapt_cta(platform, cta),
            "format_notes": "知乎更重论证与反驳；公众号更重信任、步骤和转化。" if platform == "wechat_official" else "知乎版需要保留证据链和反方观点，避免硬广。",
            "style_profile": get_platform_style_profile(platform),
            "publish_pack": publish_pack,
        }
    return variants


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


def _scores(evidence_ready: bool) -> dict[str, int]:
    if evidence_ready:
        return {
            "hook": 7,
            "topic": 7,
            "emotion": 6,
            "density": 7,
            "pacing": 6,
            "viewpoint": 7,
            "cta": 6,
            "title_bait_risk": 2,
            "controversy_overload_risk": 2,
        }
    return {
        "hook": 5,
        "topic": 5,
        "emotion": 4,
        "density": 4,
        "pacing": 5,
        "viewpoint": 4,
        "cta": 5,
        "title_bait_risk": 2,
        "controversy_overload_risk": 2,
    }


def _prediction(evidence_ready: bool, platforms: list[str], evidence_count: int) -> dict[str, Any]:
    confidence = "medium" if evidence_ready and evidence_count >= 2 else "low"
    return {
        "confidence": confidence,
        "expected_outcome": "可进入人工审稿" if evidence_ready else "需要先补证据，暂不建议发布",
        "platforms": platforms,
        "expected_views": {"low": 50, "mid": 300, "high": 1200} if evidence_ready else {"low": 0, "mid": 50, "high": 150},
        "expected_save_or_share_rate": {"low": 0.01, "mid": 0.03, "high": 0.08} if evidence_ready else {"low": 0, "mid": 0.01, "high": 0.02},
        "basis": [
            f"evidence_with_url={evidence_count}",
            "soft_article_lane",
            "no_publish_without_human_review",
        ],
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
    body = _build_body(topic=topic, objective=objective, evidence=evidence, audience=audience)
    cta = audience.get("cta") or "欢迎把你的情况发来，我们可以继续拆解适合你的方案"
    variants = _build_variants(title=title, body=body, topic_terms=topic_terms, platforms=platforms, cta=cta)
    plan = build_content_production_plan({
        "objective": objective,
        "kind": "article_soft",
        "platforms": platforms,
        "account_id": params.get("account_id"),
    })
    scores = _scores(evidence_ready)
    prediction = _prediction(evidence_ready, platforms, len(evidence_with_url))

    return {
        "status": "ready_for_review" if evidence_ready else "needs_evidence",
        "title": title,
        "topic": topic,
        "hook": _text(params.get("hook") or f"{topic}真正该先看懂什么", limit=120),
        "platform": platforms[0] if len(platforms) == 1 else "multi_article",
        "type": "script",
        "content": {
            "production_kind": "article_soft",
            "objective": objective,
            "target_platforms": platforms,
            "article_status": "ready_for_review" if evidence_ready else "needs_evidence",
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
                "tags": topic_terms,
                "cta": cta,
            },
            "platform_variants": variants,
            "platform_publish_packs": article_platform_publish_packs(platforms),
            "evidence_refs": evidence,
            "visual_requirements": _visual_requirements(topic, topic_terms, evidence_ready, platforms),
            "quality_gates": [
                {"name": "事实证据门", "status": "pass" if evidence_ready else "blocked"},
                {"name": "平台语气门", "status": "pending_human_review"},
                {"name": "配图授权门", "status": "pending_when_visual_attached"},
                {"name": "记忆边界门", "status": "pass", "note": "完整草稿只保存到 content_assets"},
            ],
            "production_plan": plan,
            "pre_review_scores": scores,
            "pre_publish_prediction": prediction,
        },
        "scores": scores,
        "prediction": prediction,
    }


def create_soft_article_asset(store: "AgentCoreStore", params: dict[str, Any] | None = None) -> dict[str, Any]:
    params = dict(params or {})
    experiment_context = requested_experiment_context(store, params)
    gate = run_content_lane_gate(store, params, kind="article_soft")
    payload = build_soft_article_asset_payload(params)
    payload["content"] = attach_content_lane_gate(payload["content"], gate)
    payload["content"] = attach_experiment_context(payload["content"], experiment_context)
    if not gate["go"]:
        payload["status"] = gate["status"]
        payload["content"]["article_status"] = gate["status"]
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
    review = None
    if gate["go"]:
        review = review_content_asset(
            store,
            asset_id=asset["id"],
            scores=payload["scores"],
            prediction=payload["prediction"],
            task_id=str(params.get("__task_id", "")) or None,
            notes="CPF-06 soft article production pre-publish review",
        )
    return {
        "status": gate_result_status(gate),
        "asset_id": asset["id"],
        "title": asset["title"],
        "article_status": payload["status"],
        "preflight_id": gate["preflight_id"],
        "production_gate": gate,
        "target_platforms": payload["content"]["target_platforms"],
        "evidence_status": payload["content"]["evidence_status"],
        "variant_count": len(payload["content"]["platform_variants"]),
        "visual_requirements": payload["content"]["visual_requirements"],
        "experiment_link": experiment_link,
        "review": review,
    }
