"""Unified PreflightDecision for Marketing OS.

``InfluenceOS Score`` answers "how strong is this content/action likely to be".
``PreflightDecision`` answers "what should the product do next".

The decision object is intentionally plain JSON so the Agent loop, task
checkpoints, tool results and product surfaces consume the same contract.
"""

from __future__ import annotations

from typing import Any

from .influence_score import build_influence_score


PREFLIGHT_DECISION_VERSION = "preflight-decision-v0.1"

VALID_STAGES = {
    "production_draft",
    "render_prepare",
    "publish_review",
    "launch",
}

READY_BY_STAGE = {
    "production_draft": ("ready_for_asset_draft", "produce_asset"),
    "render_prepare": ("ready_for_render_prepare", "prepare_render"),
    "publish_review": ("ready_for_publish_review", "prepare_publish_review"),
    "launch": ("ready_for_action", "execute_action"),
}

WATCH_METRIC_BY_COMPONENT = {
    "PlatformReachPotential": "曝光/初始播放",
    "HumanAttentionKernel": "前 3 秒停留",
    "RetentionDesign": "完播率/平均观看时长",
    "PersuasionScore": "收藏/评论质量/信任表达",
    "SocialPropagation": "分享/转发/二次传播",
    "AccountFit": "目标受众匹配/粉丝转化",
    "BusinessValue": "关注/点击/线索/转化",
    "RiskPenalty": "不感兴趣/举报/取关/版权风险",
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _risk_value(influence_score: dict[str, Any]) -> float:
    try:
        return float(((influence_score.get("components") or {}).get("RiskPenalty") or {}).get("value") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _score_value(influence_score: dict[str, Any]) -> float:
    try:
        return float(influence_score.get("score") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _selected_lane(context: dict[str, Any]) -> str | None:
    return _text(context.get("selected_lane") or context.get("kind") or context.get("content_kind")) or None


def _reason_from_status(status: str, influence_score: dict[str, Any], blockers: list[str]) -> str:
    if status == "needs_audience_context":
        return "当前缺少目标受众或账号定位，直接生产容易变成泛泛内容。"
    if status == "needs_evidence":
        return "当前缺少可追溯证据或来源，先补证据再生产更稳。"
    if status == "replace_or_license_materials":
        return "当前素材授权或素材完整性不足，先换素材或补授权。"
    if status == "blocked_by_risk":
        return "风险扣分过高，继续生产/发布可能伤账号或触发合规问题。"
    if status == "needs_revision":
        return "内容可以继续，但需要先改结构、证据、行动路径或风险点。"
    if status == "do_not_open_or_publish_yet":
        return "综合分和可观测依据不足，现在不建议开机或发布。"
    if status.startswith("ready_"):
        return "当前分数、风险和硬性条件允许进入下一步。"
    if blockers:
        return f"存在阻断项：{', '.join(blockers[:4])}。"
    return str(influence_score.get("formula_note") or "基于 InfluenceOS Score 和硬性门槛生成决策。")


def _next_steps(status: str, blockers: list[str], lane: str | None, stage: str) -> list[str]:
    steps: list[str] = []
    if "audience_context_missing" in blockers:
        steps.append("通过账号生命周期或自然对话补齐目标受众、痛点和商业目标。")
    if "url_evidence_missing" in blockers:
        steps.append("补充至少 1-3 条带 URL/来源的事实证据。")
    if "material_license_check_required" in blockers or status == "replace_or_license_materials":
        steps.append("检查素材来源、授权、版权和可商用范围。")
    if "provider_calibration_required" in blockers:
        steps.append("先完成视频/语音/渲染提供商校准，再开机。")
    if status == "blocked_by_risk":
        steps.append("降低标题党、争议过载、版权、平台违规或负反馈风险。")
    if status == "needs_revision":
        steps.append("优先重写开头钩子、中段结构、证据链和结尾行动路径。")
    if not steps and status.startswith("ready_"):
        if stage == "publish_review":
            steps.append("进入发布审批，并确认标题、封面、时间和指标回收计划。")
        elif stage == "render_prepare":
            steps.append("进入素材/渲染准备，先检查素材授权、字幕和音频来源。")
        elif lane == "faceless_video":
            steps.append("进入素材清单、脚本拆镜和低成本样片。")
        else:
            steps.append("进入草稿生产，并保留发布前预测和回执计划。")
    if not steps:
        steps.append("先补齐缺失依据，再重新运行预演。")
    return list(dict.fromkeys(steps))


def _watch_metrics(influence_score: dict[str, Any], stage: str) -> list[str]:
    components = influence_score.get("components") or {}
    ordered = [
        WATCH_METRIC_BY_COMPONENT[key]
        for key in (
            "PlatformReachPotential",
            "HumanAttentionKernel",
            "RetentionDesign",
            "PersuasionScore",
            "SocialPropagation",
            "AccountFit",
            "BusinessValue",
            "RiskPenalty",
        )
        if key in components
    ]
    if stage == "publish_review":
        ordered.extend(["1h/6h/24h/3d/7d 指标回收", "prediction vs actual 复盘"])
    return list(dict.fromkeys(ordered))


def build_preflight_decision(
    influence_score: dict[str, Any],
    *,
    stage: str = "production_draft",
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Translate score + hard gates into one product decision object."""

    context = dict(context or {})
    if stage not in VALID_STAGES:
        stage = "production_draft"
    blockers = [
        str(item) for item in (context.get("blockers") or [])
        if str(item).strip()
    ]
    warnings = [
        str(item) for item in (context.get("warnings") or [])
        if str(item).strip()
    ]
    lane = _selected_lane(context)
    score = _score_value(influence_score)
    risk = _risk_value(influence_score)
    score_decision = str(influence_score.get("decision") or "")

    if "audience_context_missing" in blockers:
        status = "needs_audience_context"
        go = False
        action = "collect_context"
    elif "url_evidence_missing" in blockers or "evidence_missing" in blockers:
        status = "needs_evidence"
        go = False
        action = "collect_evidence"
    elif "material_license_check_required" in blockers or "material_missing" in blockers:
        status = "replace_or_license_materials"
        go = False
        action = "fix_materials"
    elif risk >= 0.72:
        status = "blocked_by_risk"
        go = False
        action = "reduce_risk"
    elif score_decision == "do_not_open_or_publish_yet" or score < 38:
        status = "do_not_open_or_publish_yet"
        go = False
        action = "stop"
    elif score_decision == "revise_before_action" or score < 58:
        status = "needs_revision"
        go = False
        action = "revise"
    else:
        status, action = READY_BY_STAGE[stage]
        go = True
        if score_decision == "go_with_watchpoints":
            warnings.append("watchpoints_required")

    if context.get("status_override") and blockers:
        status = str(context["status_override"])

    primary_reason = _reason_from_status(status, influence_score, blockers)
    required_next_steps = _next_steps(status, blockers, lane, stage)
    ready_label = {
        "ready_for_asset_draft": "可进入生产",
        "ready_for_render_prepare": "可准备渲染",
        "ready_for_publish_review": "可进入发布审批",
        "ready_for_action": "可执行",
    }.get(status, "需要处理")

    return {
        "version": PREFLIGHT_DECISION_VERSION,
        "stage": stage,
        "status": status,
        "go": go,
        "action": action,
        "selected_lane": lane,
        "score": score,
        "score_decision": score_decision,
        "risk_value": risk,
        "confidence": influence_score.get("confidence", 0),
        "primary_reason": primary_reason,
        "next_action": required_next_steps[0],
        "required_next_steps": required_next_steps,
        "blockers": blockers,
        "warnings": list(dict.fromkeys(warnings)),
        "watch_metrics": _watch_metrics(influence_score, stage),
        "missing_score_dimensions": influence_score.get("missing_dimensions") or [],
        "ui": {
            "label": ready_label,
            "tone": "positive" if go else ("danger" if status in {"blocked_by_risk", "do_not_open_or_publish_yet"} else "warning"),
            "cta": required_next_steps[0],
        },
    }


def build_score_preflight_decision(
    params: dict[str, Any] | None = None,
    *,
    stage: str = "production_draft",
) -> dict[str, Any]:
    """Build a decision from supplied feature groups without reading state."""

    params = dict(params or {})
    score = build_influence_score({
        "metric_labels": params.get("metric_labels") if isinstance(params.get("metric_labels"), dict) else {},
        "content_score": params.get("content_score") if isinstance(params.get("content_score"), dict) else {},
        "preflight_scores": params.get("preflight_scores") if isinstance(params.get("preflight_scores"), dict) else {},
    })
    decision = build_preflight_decision(
        score,
        stage=stage,
        context=params.get("context") if isinstance(params.get("context"), dict) else {},
    )
    return {
        "influence_score": score,
        "preflight_decision": decision,
    }
