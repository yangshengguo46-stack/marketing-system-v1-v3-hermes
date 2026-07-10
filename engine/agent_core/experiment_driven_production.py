"""Create content drafts from account experiments.

This module is the bridge between account lifecycle experiments and the content
factory.  It deliberately does not invent a new production lane; it reads an
existing ``account_experiments`` row, builds the safest content-production
request from the approved account context, then delegates to the existing soft
article or faceless-video creators.
"""

from __future__ import annotations

import re
from typing import Any

from .account_lifecycle import AccountLifecycleService
from .article_soft_production import create_soft_article_asset
from .content_production import build_content_production_plan
from .faceless_video_production import create_faceless_video_asset
from .production_preflight import create_content_production_preflight


VALID_EXPERIMENT_PRODUCTION_KINDS = {"auto", "article_soft", "faceless_video", "premium_human_video"}
VIDEO_METRICS = {"attention", "retention"}
VIDEO_COMPONENTS = {"PlatformReachPotential", "RetentionDesign"}
ARTICLE_PLATFORMS = {"zhihu", "wechat_official"}
VIDEO_PLATFORMS = {"douyin", "wechat_channels", "bilibili"}


def _text(value: Any, *, limit: int | None = None) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit] if limit is not None else text


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _normalise_kind(value: Any) -> str:
    kind = _text(value).lower()
    aliases = {
        "article": "article_soft",
        "soft_article": "article_soft",
        "faceless": "faceless_video",
        "material_video": "faceless_video",
        "premium": "premium_human_video",
        "human_video": "premium_human_video",
        "digital_human": "premium_human_video",
    }
    kind = aliases.get(kind, kind or "auto")
    if kind not in VALID_EXPERIMENT_PRODUCTION_KINDS:
        raise ValueError(f"unsupported experiment production kind: {kind}")
    return kind


def _normalise_platforms(value: Any) -> list[str]:
    if isinstance(value, str):
        raw = re.split(r"[,，、/\s]+", value)
    elif isinstance(value, (list, tuple, set)):
        raw = [str(item) for item in value]
    else:
        raw = []
    aliases = {
        "知乎": "zhihu",
        "公众号": "wechat_official",
        "微信公众号": "wechat_official",
        "抖音": "douyin",
        "视频号": "wechat_channels",
        "b站": "bilibili",
        "哔哩哔哩": "bilibili",
    }
    result: list[str] = []
    for item in raw:
        platform = aliases.get(item.strip(), item.strip().lower())
        if platform in ARTICLE_PLATFORMS | VIDEO_PLATFORMS and platform not in result:
            result.append(platform)
    return result


def _infer_kind(experiment: dict[str, Any], params: dict[str, Any]) -> str:
    requested = _normalise_kind(params.get("kind") or params.get("content_kind") or "auto")
    if requested != "auto":
        return requested
    platforms = _normalise_platforms(params.get("platforms") or params.get("platform"))
    if platforms and set(platforms).issubset(ARTICLE_PLATFORMS):
        return "article_soft"
    if platforms and any(platform in VIDEO_PLATFORMS for platform in platforms):
        return "faceless_video"

    variable = experiment.get("variable") if isinstance(experiment.get("variable"), dict) else {}
    success = (
        experiment.get("success_criteria")
        if isinstance(experiment.get("success_criteria"), dict)
        else {}
    )
    variable_kind = _text(
        variable.get("production_kind")
        or variable.get("content_kind")
        or variable.get("lane")
    )
    if variable_kind in {"article_soft", "faceless_video", "premium_human_video"}:
        return variable_kind
    component = _text(variable.get("component"))
    primary_metric = _text(success.get("primary_metric") or variable.get("primary_metric")).lower()
    if primary_metric in VIDEO_METRICS or component in VIDEO_COMPONENTS:
        return "faceless_video"
    return "article_soft"


def _default_platforms(kind: str) -> list[str]:
    if kind == "article_soft":
        return ["zhihu", "wechat_official"]
    if kind == "faceless_video":
        return ["douyin", "wechat_channels", "bilibili"]
    return ["douyin", "bilibili"]


def _topic_from_experiment(experiment: dict[str, Any], params: dict[str, Any]) -> str:
    if _text(params.get("topic")):
        return _text(params.get("topic"), limit=80)
    variable = experiment.get("variable") if isinstance(experiment.get("variable"), dict) else {}
    for key in ("recommendation", "rule_key", "component", "type"):
        value = _text(variable.get(key), limit=80)
        if value:
            return value
    hypothesis = _text(experiment.get("hypothesis"), limit=80)
    return hypothesis or "账号内容实验"


def _objective_from_experiment(experiment: dict[str, Any], params: dict[str, Any], kind: str) -> str:
    if _text(params.get("objective") or params.get("brief")):
        return _text(params.get("objective") or params.get("brief"))
    success = (
        experiment.get("success_criteria")
        if isinstance(experiment.get("success_criteria"), dict)
        else {}
    )
    primary_metric = _text(success.get("primary_metric") or "账号适配度")
    lane_label = "不露脸素材视频" if kind == "faceless_video" else "知乎/公众号软文"
    if kind == "premium_human_video":
        lane_label = "高质量视频项目"
    return (
        f"围绕账号实验生成一条{lane_label}：{_text(experiment.get('hypothesis'))}。"
        f"核心验证指标：{primary_metric}。发布前必须保留证据、预演和回执链路。"
    )


def _audience_context(
    lifecycle: AccountLifecycleService,
    *,
    user_id: str,
    account_id: str,
    project_id: str,
    experiment: dict[str, Any],
    params: dict[str, Any],
) -> dict[str, Any]:
    provided = params.get("audience_context") or params.get("account_context")
    if isinstance(provided, dict) and provided:
        return dict(provided)
    status = lifecycle.read_status(user_id=user_id, account_id=account_id, project_id=project_id)
    dna = lifecycle.account_dna_projection(user_id=user_id, account_id=account_id, project_id=project_id) or {}
    audience = status.get("audience_hypothesis") if isinstance(status.get("audience_hypothesis"), dict) else {}
    segments = _list(audience.get("segments"))
    pains = _list(audience.get("pains"))
    scenarios = _list(audience.get("scenarios"))
    segment_labels = [
        _text(item.get("label") if isinstance(item, dict) else item, limit=80)
        for item in segments
    ]
    target = _text(dna.get("audience") or "、".join(label for label in segment_labels if label), limit=180)
    promise = ""
    goals = dna.get("goals")
    if isinstance(goals, list) and goals:
        promise = _text(goals[0], limit=180)
    return {
        "target_reader": target or "已确认账号目标受众",
        "audience": target or "已确认账号目标受众",
        "persona": _text(dna.get("persona"), limit=120),
        "pain_points": [_text(item, limit=120) for item in pains if _text(item)][:6],
        "scenarios": [_text(item, limit=120) for item in scenarios if _text(item)][:6],
        "promise": promise or _text(experiment.get("hypothesis"), limit=180),
        "tone": dna.get("tone") if isinstance(dna.get("tone"), list) else [],
        "content_pillars": dna.get("content_pillars") if isinstance(dna.get("content_pillars"), list) else [],
        "taboos": dna.get("taboos") if isinstance(dna.get("taboos"), list) else [],
        "experiment_hypothesis": experiment.get("hypothesis"),
        "primary_metric": (experiment.get("success_criteria") or {}).get("primary_metric"),
        "source": "account_lifecycle",
    }


def _evidence(params: dict[str, Any]) -> list[dict[str, Any]]:
    evidence = params.get("evidence") or params.get("evidence_pack") or []
    if isinstance(evidence, dict):
        for key in ("items", "results", "evidence", "data"):
            nested = evidence.get(key)
            if isinstance(nested, list):
                evidence = nested
                break
        else:
            evidence = [evidence]
    if not isinstance(evidence, list):
        return []
    return [item for item in evidence if isinstance(item, dict)]


def build_content_request_from_experiment(store: Any, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build the concrete content-production request for one experiment."""

    params = dict(params or {})
    user_id = _text(params.get("__user_id") or params.get("user_id")) or "default"
    account_id = _text(params.get("account_id"))
    experiment_id = _text(params.get("experiment_id"))
    if not account_id:
        raise ValueError("account_id is required")
    if not experiment_id:
        raise ValueError("experiment_id is required")

    lifecycle = AccountLifecycleService(store)
    project_id = _text(params.get("project_id"))
    if not project_id:
        project = lifecycle.get_active_project(user_id=user_id, account_id=account_id)
        if project is None:
            raise ValueError("project_id is required when account has no active strategy project")
        project_id = project["id"]
    experiment = lifecycle.get_experiment(
        user_id=user_id,
        account_id=account_id,
        project_id=project_id,
        experiment_id=experiment_id,
    )
    kind = _infer_kind(experiment, params)
    platforms = _normalise_platforms(params.get("platforms") or params.get("platform")) or _default_platforms(kind)
    request = {
        "__user_id": user_id,
        "user_id": user_id,
        "account_id": account_id,
        "project_id": project_id,
        "experiment_id": experiment_id,
        "kind": kind,
        "platforms": platforms,
        "topic": _topic_from_experiment(experiment, params),
        "title": _text(params.get("title"), limit=120),
        "objective": _objective_from_experiment(experiment, params, kind),
        "audience_context": _audience_context(
            lifecycle,
            user_id=user_id,
            account_id=account_id,
            project_id=project_id,
            experiment=experiment,
            params=params,
        ),
        "evidence": _evidence(params),
        "memory_refs": _list(params.get("memory_refs")),
        "receipt_refs": _list(params.get("receipt_refs")),
        "source": {
            "type": "account_experiment",
            "project_id": project_id,
            "experiment_id": experiment_id,
            "hypothesis": experiment.get("hypothesis"),
            "status": experiment.get("status"),
            "variable": experiment.get("variable"),
            "success_criteria": experiment.get("success_criteria"),
        },
    }
    if not request["title"]:
        request.pop("title")
    for key in ("hook", "body_markdown", "platform_variants"):
        value = params.get(key)
        if value not in (None, "", [], {}):
            request[key] = value
    return {
        "status": "ready",
        "kind": kind,
        "project_id": project_id,
        "experiment_id": experiment_id,
        "experiment": experiment,
        "production_request": request,
        "production_plan": build_content_production_plan(request),
    }


def create_content_from_experiment(store: Any, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Create a content draft from an existing account experiment."""

    built = build_content_request_from_experiment(store, params)
    request = dict(built["production_request"])
    kind = built["kind"]
    if kind == "premium_human_video":
        preflight = create_content_production_preflight(store, request)
        return {
            "status": "blocked",
            "reason": "premium_human_video_requires_video_previsualization_project",
            "kind": kind,
            "project_id": built["project_id"],
            "experiment_id": built["experiment_id"],
            "production_request": request,
            "production_plan": built["production_plan"],
            "preflight_id": preflight["preflight_id"],
            "preflight_status": preflight["preflight_decision"]["status"],
            "preflight_decision": preflight["preflight_decision"],
            "video_previsualization": preflight["video_previsualization"],
            "guardrail": "high-end video must pass the dedicated film previsualization agent first",
        }
    if kind == "faceless_video":
        asset_result = create_faceless_video_asset(store, request)
    else:
        asset_result = create_soft_article_asset(store, request)
    return {
        "status": asset_result.get("status"),
        "kind": kind,
        "project_id": built["project_id"],
        "experiment_id": built["experiment_id"],
        "asset_id": asset_result.get("asset_id"),
        "asset_result": asset_result,
        "experiment_link": asset_result.get("experiment_link"),
        "production_request": request,
        "production_plan": built["production_plan"],
        "guardrail": "content draft created from an account experiment and linked back for receipt learning",
    }
