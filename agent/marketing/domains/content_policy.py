"""Hermes-native content production planning for Marketing OS.

The planner is deterministic and side-effect free. It selects one delivery
lane while keeping research, writing, media, audio and rendering as a shared
capability pool so article and video production can borrow from each other.
"""

from __future__ import annotations

import re
from typing import Any

from agent.marketing.domains.article_drafts import article_stylebooks
from agent.marketing.platform_catalog import (
    PLATFORM_PROFILES,
    content_lane_for_platform,
    normalize_platforms,
    platform_content_blueprints,
)


CONTENT_KINDS = {"article_soft", "faceless_video", "cross_platform_campaign"}
EXTERNAL_CONTENT_KINDS = {"premium_human_video"}
ARTICLE_BUNDLE_PLATFORMS = {"zhihu", "wechat_official"}
# Compatibility exports for collectors/publishers whose provider support is
# necessarily finite. Content planning itself uses the extensible catalog and
# accepts safe unknown platform IDs with an explicit research gap.
ARTICLE_PLATFORMS = {
    platform
    for platform in PLATFORM_PROFILES
    if content_lane_for_platform(platform) == "article_soft"
}
VIDEO_PLATFORMS = set(PLATFORM_PROFILES) - ARTICLE_PLATFORMS
VALID_PLATFORMS = ARTICLE_PLATFORMS | VIDEO_PLATFORMS

SHARED_CAPABILITIES = {
    "account_context": {
        "purpose": "读取会话绑定账号的受众、定位、禁区和历史反馈。",
        "native_tools": ["marketing_read_account_context"],
        "maturity": "ready",
    },
    "evidence_research": {
        "purpose": "使用可回链来源核对事实、热点和案例，禁止模型补造数据。",
        "native_tools": ["web_search", "web_extract", "marketing_read_evidence_pack"],
        "maturity": "ready",
    },
    "copywriting": {
        "purpose": "生产父稿、平台变体、旁白、标题和 CTA。",
        "native_tools": ["marketing_draft_article_create", "marketing_draft_content_create"],
        "maturity": "ready",
    },
    "stock_material": {
        "purpose": "检索有来源、有授权信息的图片、视频、音频和引用素材。",
        "native_tools": ["web_search", "web_extract"],
        "maturity": "partial",
    },
    "generated_visual": {
        "purpose": "授权素材不足时补充封面、信息图、代码视觉或缺口镜头。",
        "native_tools": ["image_generate", "execute_code"],
        "maturity": "partial",
    },
    "audio": {
        "purpose": "把 BGM、原声、配音和音效作为传播变量组织；先读真实平台声音趋势，再决定声音角色和混音。",
        "native_tools": ["marketing_read_sound_trends", "text_to_speech"],
        "maturity": "partial",
    },
    "editing_render": {
        "purpose": "把镜头、素材、字幕和音轨组织为可恢复时间线并渲染。",
        "native_tools": ["terminal", "process"],
        "maturity": "partial",
    },
}

LANE_CONFIG = {
    "article_soft": {
        "label": "知乎/公众号软文",
        "default_platforms": ["zhihu", "wechat_official"],
        "asset_type": "script",
        "capabilities": [
            "account_context",
            "evidence_research",
            "copywriting",
            "stock_material",
            "generated_visual",
        ],
        "skills": ["humanizer", "baoyu-infographic"],
        "deliverables": ["parent_draft", "platform_variants", "cover_brief", "inline_visual_plan"],
    },
    "faceless_video": {
        "label": "授权素材不露脸视频",
        "default_platforms": ["douyin", "wechat_channels", "bilibili"],
        "asset_type": "video",
        "capabilities": [
            "account_context",
            "evidence_research",
            "copywriting",
            "stock_material",
            "generated_visual",
            "audio",
            "editing_render",
        ],
        "skills": ["humanizer", "baoyu-infographic", "manim-video", "p5js", "ascii-video"],
        "deliverables": ["voiceover_script", "shot_list", "material_manifest", "sound_plan", "timeline", "final_video"],
    },
    "cross_platform_campaign": {
        "label": "跨平台内容 campaign",
        "default_platforms": [],
        "asset_type": "script",
        "capabilities": [
            "account_context",
            "evidence_research",
            "copywriting",
            "stock_material",
            "generated_visual",
            "audio",
            "editing_render",
        ],
        "skills": ["humanizer", "baoyu-infographic"],
        "deliverables": [
            "content_kernel",
            "platform_blueprints",
            "platform_native_variants",
            "shared_evidence_pack",
            "shared_visual_material_pack",
        ],
    },
}


class ContentProductionPolicy:
    def plan(
        self,
        *,
        objective: str,
        kind: str = "auto",
        platforms: Any = None,
        audience: str = "",
        evidence_refs: list[str] | None = None,
        constraints: dict[str, Any] | None = None,
        account_context: dict[str, Any] | None = None,
        experiment_id: str = "",
    ) -> dict[str, Any]:
        objective_value = _bounded_text(objective, "objective", 2_000)
        kind_value = infer_content_kind(objective_value, kind=kind, platforms=platforms)
        config = LANE_CONFIG[kind_value]
        platform_values = normalize_platforms(platforms) or list(config["default_platforms"])
        if not platform_values:
            raise ValueError(
                "cross-platform content planning requires at least one target platform"
            )
        if kind_value == "article_soft" and not set(platform_values) <= ARTICLE_BUNDLE_PLATFORMS:
            raise ValueError(
                "article_soft currently owns only the validated zhihu/wechat_official bundle; "
                "use cross_platform_campaign for other domestic or overseas article platforms"
            )
        evidence = _bounded_refs(evidence_refs or [], "evidence_refs")
        constraints_value = constraints or {}
        if not isinstance(constraints_value, dict):
            raise ValueError("constraints must be an object")

        context = account_context or {}
        lifecycle = context.get("lifecycle") if isinstance(context.get("lifecycle"), dict) else {}
        alignment = (
            lifecycle.get("strategy_alignment")
            if isinstance(lifecycle.get("strategy_alignment"), dict)
            else {}
        )
        account_ready = bool(
            str(audience or "").strip()
            or lifecycle.get("audience_hypothesis")
            or (context.get("account_dna") or {}).get("audience_summary")
        )
        strategy_ready = bool(
            lifecycle.get("positioning")
            and lifecycle.get("content_system")
            and alignment.get("positioning_current") is True
            and alignment.get("content_system_current") is True
        )
        gates = [
            {
                "id": "audience",
                "status": "ready" if account_ready else "needs_input",
                "rule": "有明确目标受众、真实受众证据或用户确认的受众假设。",
            },
            {
                "id": "strategy",
                "status": "ready" if strategy_ready else "exploration_only",
                "rule": (
                    "正式经营内容必须绑定当前版本的已批准定位与内容系统；"
                    "缺失或过期时只允许可逆探索草稿。"
                ),
            },
            {
                "id": "evidence",
                "status": "verified_evidence_ready" if evidence else "needs_research",
                "rule": "事实性主张必须绑定当前账号由 Hermes 真实采集的 EvidencePack ID；创意表达不能冒充事实。",
            },
            {
                "id": "rights",
                "status": "required" if kind_value != "article_soft" else "conditional",
                "rule": "外部图片、视频、音乐、声音和肖像必须记录来源与授权。",
            },
            {
                "id": "cost",
                "status": "local_first",
                "rule": "优先本地和免费能力；付费生成必须在调用前展示成本并获批。",
            },
        ]
        if not account_ready:
            next_action = "通过自然对话补齐目标用户、内容承诺和明确禁区"
        elif not strategy_ready:
            next_action = "先完成或修订账号定位与内容系统；当前仅生成探索草稿"
        elif not evidence:
            next_action = "检索并核对支撑本选题的证据，再开始写父稿"
        else:
            next_action = "使用已固化的 EvidencePack 生成父稿，再保存为可恢复草稿"

        result = {
            "status": "planned",
            "architecture": "hermes-native-shared-capability-pool",
            "kind": kind_value,
            "kind_label": config["label"],
            "objective": objective_value,
            "target_platforms": platform_values,
            "platform_blueprints": platform_content_blueprints(platform_values),
            "asset_type": config["asset_type"],
            "account_scope": {
                "account_id": context.get("account_id"),
                "connected": context.get("connected", False),
                "lifecycle_stage": lifecycle.get("stage", "not_started"),
                "positioning_id": lifecycle.get("positioning_id"),
                "content_system_id": lifecycle.get("content_system_id"),
            },
            "audience_model": _audience_model(
                lifecycle.get("audience_hypothesis"), explicit_audience=audience
            ),
            "operating_mode": "strategy_aligned" if strategy_ready else "exploratory_draft",
            "experiment_id": str(experiment_id or "").strip() or None,
            "capabilities": {
                name: SHARED_CAPABILITIES[name] for name in config["capabilities"]
            },
            "recommended_skills": list(config["skills"]),
            "gates": gates,
            "deliverables": list(config["deliverables"]),
            "constraints": constraints_value,
            "recommended_next_action": next_action,
            "execution_order": [
                "read_account_context",
                "fill_audience_gap",
                "research_evidence",
                "draft_parent_content",
                "adapt_platform_variants",
                "source_or_generate_media",
                "select_and_verify_sound",
                "preflight_review",
                "save_content_asset",
            ],
            "fallback": _fallback(kind_value),
        }
        if kind_value == "article_soft":
            result["platform_stylebooks"] = article_stylebooks(platform_values)
        return result


def _audience_model(value: Any, *, explicit_audience: str) -> dict[str, Any]:
    if isinstance(value, dict) and value:
        return value
    audience = str(explicit_audience or "").strip()
    if not audience:
        return {}
    return {
        "status": "user_supplied_for_plan",
        "segments": [audience[:500]],
        "pains": [],
        "scenarios": [],
        "jobs": [],
        "trust_barriers": [],
        "desired_outcomes": [],
        "behavior_signals": [],
        "data_gaps": ["audience_details_require_confirmation"],
    }


def infer_content_kind(objective: str, *, kind: str = "auto", platforms: Any = None) -> str:
    requested = str(kind or "auto").strip().lower()
    aliases = {
        "article": "article_soft",
        "soft_article": "article_soft",
        "faceless": "faceless_video",
        "premium": "premium_human_video",
        "human_video": "premium_human_video",
        "digital_human": "premium_human_video",
    }
    requested = aliases.get(requested, requested)
    if requested in EXTERNAL_CONTENT_KINDS:
        raise ValueError(
            "premium_human_video belongs to the standalone video-studio product, "
            "not the Marketing OS content-production runtime"
        )
    if requested in CONTENT_KINDS:
        return requested
    normalized_platforms = normalize_platforms(platforms)
    lanes = {content_lane_for_platform(item) for item in normalized_platforms}
    if len(normalized_platforms) > 1 and len(lanes) > 1:
        return "cross_platform_campaign"
    if normalized_platforms and lanes == {"article_soft"}:
        return (
            "article_soft"
            if set(normalized_platforms) <= ARTICLE_BUNDLE_PLATFORMS
            else "cross_platform_campaign"
        )
    text = str(objective or "").lower()
    if any(word in text for word in ("全平台", "跨平台", "各平台", "每个平台", "多平台")):
        return "cross_platform_campaign"
    if any(word in text for word in ("知乎", "公众号", "软文", "长文", "文章")):
        return "article_soft"
    if any(word in text for word in ("数字人", "真人", "ai人", "ai 人", "口播", "高质量视频")):
        raise ValueError(
            "high-end human, digital-human, and AI film production belongs to "
            "the standalone video-studio product"
        )
    if any(word in text for word in ("不露脸", "素材拼接", "混剪", "空镜", "素材视频")):
        return "faceless_video"
    if normalized_platforms and lanes == {"faceless_video"}:
        return "faceless_video"
    return "article_soft"


def _fallback(kind: str) -> dict[str, str]:
    if kind == "cross_platform_campaign":
        return {
            "if_platform_guidance_missing": (
                "保留内容内核和证据包，为未知平台输出通用可重排素材及明确研究缺口，"
                "不得冒充已经完成平台适配。"
            )
        }
    if kind == "faceless_video":
        return {
            "if_materials_insufficient": "交付旁白脚本、分镜和素材缺口清单，不伪造最终视频。"
        }
    return {"if_visuals_unavailable": "先交付有证据的纯文本草稿和明确配图位。"}


def _bounded_text(value: Any, field: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text:
        raise ValueError(f"{field} is required")
    if len(text) > limit:
        raise ValueError(f"{field} exceeds {limit} characters")
    return text


def _bounded_refs(value: Any, field: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    result = [str(item).strip() for item in value if str(item).strip()]
    if len(result) > 50 or any(len(item) > 500 for item in result):
        raise ValueError(f"{field} exceeds limits")
    return result
