"""Faceless video production chain.

This is the low-cost video lane: script, shot list, material search package,
gap-fill generation requests and an EDL draft.  It deliberately does not
download media, register fake attachments, call paid video providers, or render
an mp4.  Those actions are separate capability steps with their own provenance,
license and approval requirements.
"""

from __future__ import annotations

import re
import struct
import hashlib
import subprocess
import textwrap
from pathlib import Path
from typing import Any, TYPE_CHECKING
import zlib

from .content_lane_gate import (
    attach_asset_to_requested_experiment,
    attach_content_lane_gate,
    attach_experiment_context,
    gate_result_status,
    requested_experiment_context,
    run_content_lane_gate,
)
from .content_prediction import attach_prediction_dimensions
from .content_production import build_content_production_plan
from .learning_pipeline import review_content_asset
from engine.video_core.editing_engine import build_edl_from_segments, edl_handoff_summary, segment_from_shot
from engine.video_core.edl import EDL, TimelineSlot
from engine.video_core.renderer import RenderError, Renderer

if TYPE_CHECKING:
    from .store import AgentCoreStore


VIDEO_PLATFORMS = ("douyin", "wechat_channels", "bilibili")


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
        "抖音": "douyin",
        "视频号": "wechat_channels",
        "b站": "bilibili",
        "哔哩哔哩": "bilibili",
    }
    result: list[str] = []
    for item in raw:
        platform = alias.get(item.strip(), item.strip().lower())
        if platform in VIDEO_PLATFORMS and platform not in result:
            result.append(platform)
    return result or list(VIDEO_PLATFORMS)


def _topic_terms(objective: str) -> list[str]:
    terms: list[str] = []
    for token in re.findall(r"[A-Za-z][A-Za-z0-9+\-.]{1,24}|[\u4e00-\u9fff]{2,12}", objective):
        if token not in terms and token not in {"帮我", "生成", "制作", "内容", "视频", "一个", "一条", "不露脸", "素材", "拼接"}:
            terms.append(token)
    return terms[:6] or ["行业变化", "用户痛点", "决策框架"]


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
        if title or summary:
            evidence.append({
                "id": f"ev_{index:02d}",
                "title": title or f"证据 {index}",
                "summary": summary or title,
                "url": url,
                "has_url": bool(url),
            })
    return evidence[:12]


def _script(topic: str, objective: str, evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    evidence_hint = evidence[0]["title"] if evidence else "暂无可回链证据"
    return [
        {
            "beat": "hook",
            "duration_sec": 5,
            "voiceover": f"很多人看到『{topic}』第一反应是跟风，但真正危险的是：你不知道它和你有什么关系。",
            "visual_intent": "快节奏城市/人群滑动手机/信息流掠过",
        },
        {
            "beat": "context",
            "duration_sec": 8,
            "voiceover": f"这条内容先不讲玄学，只讲一个判断框架。用户原始目标是：{objective}。",
            "visual_intent": "屏幕录制风格的信息卡片、笔记、资料页",
        },
        {
            "beat": "evidence",
            "duration_sec": 8,
            "voiceover": f"目前能拿来做依据的是：{evidence_hint}。没有来源的内容，先不能当事实发布。",
            "visual_intent": "网页资料、数据图、报告页面的抽象化镜头",
        },
        {
            "beat": "framework",
            "duration_sec": 12,
            "voiceover": "你只需要问三个问题：它解决的是不是长期问题？你能不能连续输出？它能不能连接你的真实经历？",
            "visual_intent": "三段式框架动画、便签、流程箭头",
        },
        {
            "beat": "example",
            "duration_sec": 10,
            "voiceover": f"如果这三个问题都回答不上来，『{topic}』就不要直接做账号主线，先做一次小实验。",
            "visual_intent": "A/B 测试、日历、内容发布草稿",
        },
        {
            "beat": "cta",
            "duration_sec": 6,
            "voiceover": "把你的行业和目标用户写下来，我们再把它拆成一条可验证的内容方向。",
            "visual_intent": "清单勾选、评论区、关注按钮的抽象镜头",
        },
    ]


def _material_query(terms: list[str], visual_intent: str) -> str:
    base = " ".join(terms[:3])
    return f"{base} {visual_intent} vertical stock footage"


def _shot_list(topic_terms: list[str], script: list[dict[str, Any]]) -> list[dict[str, Any]]:
    shots: list[dict[str, Any]] = []
    cursor = 0.0
    for index, beat in enumerate(script, start=1):
        duration = float(beat["duration_sec"])
        shot_id = f"shot_{index:02d}"
        visual_intent = beat["visual_intent"]
        abstract_need = any(marker in visual_intent for marker in ("框架", "抽象", "A/B", "流程"))
        shots.append({
            "id": shot_id,
            "order": index,
            "beat": beat["beat"],
            "start_sec": round(cursor, 2),
            "duration_sec": duration,
            "voiceover": beat["voiceover"],
            "visual_intent": visual_intent,
            "material_query": _material_query(topic_terms, visual_intent),
            "preferred_source": "stock_material",
            "fallback_source": "generated_image" if abstract_need else "generated_video",
            "license_required": True,
            "status": "needs_material",
        })
        cursor += duration
    return shots


def _edl(shot_list: list[dict[str, Any]]) -> dict[str, Any]:
    edl = build_edl_from_segments(
        [segment_from_shot(shot) for shot in shot_list],
        lane="faceless_video",
        subtitle_style="bold_center_keyword",
        notes=(
            "CPF-07 EDL draft via shared EditingEngine: clips remain empty "
            "until licensed/code/generated media are attached."
        ),
    )
    payload = edl.model_dump()
    payload.update(edl_handoff_summary(edl))
    return payload


def _generated_requests(shot_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
    requests = []
    for shot in shot_list:
        if shot["fallback_source"] in {"generated_image", "generated_video"}:
            requests.append({
                "shot_id": shot["id"],
                "kind": shot["fallback_source"],
                "reason": "授权素材不贴题时补关键镜头",
                "prompt_brief": shot["visual_intent"],
                "approval_required": "cost_or_provider" if shot["fallback_source"] == "generated_image" else "cost_and_rights",
                "status": "not_submitted",
            })
    return requests


def _scores(evidence_ready: bool, shot_count: int) -> dict[str, int]:
    base = 7 if evidence_ready else 5
    density = 7 if shot_count >= 5 else 5
    return {
        "hook": base,
        "topic": base,
        "emotion": 6 if evidence_ready else 4,
        "density": density,
        "pacing": 7 if shot_count >= 5 else 5,
        "viewpoint": base,
        "cta": 6,
        "title_bait_risk": 2,
        "controversy_overload_risk": 2,
    }


def _prediction(evidence_ready: bool, platforms: list[str], shot_count: int, scores: dict[str, int]) -> dict[str, Any]:
    legacy = {
        "confidence": "medium" if evidence_ready and shot_count >= 5 else "low",
        "expected_outcome": "可进入素材收集/样片阶段" if evidence_ready else "需要先补证据，暂不建议发布",
        "platforms": platforms,
        "expected_views": {"low": 100, "mid": 800, "high": 3000} if evidence_ready else {"low": 0, "mid": 80, "high": 300},
        "expected_completion_rate": {"low": 0.18, "mid": 0.32, "high": 0.48} if evidence_ready else {"low": 0.05, "mid": 0.12, "high": 0.2},
        "expected_engagement_rate": {"low": 0.012, "mid": 0.04, "high": 0.09} if evidence_ready else {"low": 0.0, "mid": 0.008, "high": 0.018},
        "basis": [
            f"shot_count={shot_count}",
            f"evidence_ready={evidence_ready}",
            "faceless_video_lane",
            "no_render_before_media_attached",
        ],
    }
    return attach_prediction_dimensions(
        legacy, kind="faceless_video", scores=scores, evidence_ready=evidence_ready,
    )


def build_faceless_video_asset_payload(params: dict[str, Any] | None = None) -> dict[str, Any]:
    params = dict(params or {})
    objective = _text(params.get("objective") or params.get("brief") or params.get("topic") or "做一条不露脸素材视频")
    platforms = _normalise_platforms(params.get("platforms") or params.get("platform"))
    evidence = _normalise_evidence(params.get("evidence") or params.get("evidence_pack"))
    evidence_ready = any(item.get("has_url") for item in evidence)
    topic_terms = _topic_terms(objective)
    topic = _text(params.get("topic") or topic_terms[0], limit=80)
    title = _text(params.get("title") or f"{topic}这件事，先别急着跟风", limit=90)
    script = _script(topic, objective, evidence)
    shot_list = _shot_list(topic_terms, script)
    edl = _edl(shot_list)
    generated_requests = _generated_requests(shot_list)
    plan = build_content_production_plan({
        "objective": objective,
        "kind": "faceless_video",
        "platforms": platforms,
        "account_id": params.get("account_id"),
    })
    scores = _scores(evidence_ready, len(shot_list))
    prediction = _prediction(evidence_ready, platforms, len(shot_list), scores)
    material_queries = [shot["material_query"] for shot in shot_list]

    return {
        "status": "ready_for_materials" if evidence_ready else "needs_evidence",
        "title": title,
        "topic": topic,
        "hook": script[0]["voiceover"],
        "platform": platforms[0] if len(platforms) == 1 else "multi_video",
        "type": "video",
        "content": {
            "production_kind": "faceless_video",
            "objective": objective,
            "target_platforms": platforms,
            "video_status": "ready_for_materials" if evidence_ready else "needs_evidence",
            "render_status": "not_rendered",
            "evidence_status": {
                "ready": evidence_ready,
                "required": True,
                "with_url": sum(1 for item in evidence if item.get("has_url")),
                "total": len(evidence),
                "message": "可进入素材收集/样片阶段" if evidence_ready else "缺少带 URL 的证据，不能进入发布审核",
            },
            "script": script,
            "shot_list": shot_list,
            "material_queries": material_queries,
            "licensed_asset_requirements": [
                {
                    "shot_id": shot["id"],
                    "query": shot["material_query"],
                    "required_fields": ["provider", "source_url", "author", "license", "download_hash"],
                    "allowed_sources": ["Pexels", "Pixabay", "Unsplash", "Freesound", "user_supplied"],
                    "status": "pending",
                }
                for shot in shot_list
            ],
            "licensed_assets": [],
            "generated_asset_requests": generated_requests,
            "edl": edl,
            "quality_gates": [
                {"name": "事实证据门", "status": "pass" if evidence_ready else "blocked"},
                {"name": "版权/来源门", "status": "blocked_until_assets_attached"},
                {"name": "素材适配门", "status": "pending_material_review"},
                {"name": "渲染诚实门", "status": "pass", "note": "当前只称为视频草稿/EDL，不称为成片"},
            ],
            "production_plan": plan,
            "pre_review_scores": scores,
            "pre_publish_prediction": prediction,
        },
        "scores": scores,
        "prediction": prediction,
    }


def create_faceless_video_asset(store: "AgentCoreStore", params: dict[str, Any] | None = None) -> dict[str, Any]:
    params = dict(params or {})
    experiment_context = requested_experiment_context(store, params)
    gate = run_content_lane_gate(store, params, kind="faceless_video")
    payload = build_faceless_video_asset_payload(params)
    payload["content"] = attach_content_lane_gate(payload["content"], gate)
    payload["content"] = attach_experiment_context(payload["content"], experiment_context)
    if not gate["go"]:
        payload["status"] = gate["status"]
        payload["content"]["video_status"] = gate["status"]
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
            notes="CPF-07 faceless video production pre-publish review",
        )
    return {
        "status": gate_result_status(gate),
        "asset_id": asset["id"],
        "title": asset["title"],
        "video_status": payload["status"],
        "preflight_id": gate["preflight_id"],
        "production_gate": gate,
        "target_platforms": payload["content"]["target_platforms"],
        "evidence_status": payload["content"]["evidence_status"],
        "shot_count": len(payload["content"]["shot_list"]),
        "material_query_count": len(payload["content"]["material_queries"]),
        "generated_request_count": len(payload["content"]["generated_asset_requests"]),
        "render_status": payload["content"]["render_status"],
        "experiment_link": experiment_link,
        "review": review,
    }


def prepare_faceless_render(store: "AgentCoreStore", params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Prepare a deterministic render command for a faceless video asset.

    This is intentionally read-only.  It does not execute ffmpeg and does not
    mutate the asset.  The desktop host can later decide whether to execute the
    command after media provenance and user approval are satisfied.
    """

    params = dict(params or {})
    asset_id = _text(params.get("asset_id"))
    if not asset_id:
        return {"status": "error", "reason": "asset_id is required"}
    asset = store.get_content_asset(asset_id)
    content = asset.get("content") or {}
    if asset.get("type") != "video" or content.get("production_kind") != "faceless_video":
        return {"status": "error", "reason": "asset is not a faceless video content asset"}

    edl_payload = content.get("edl")
    if not isinstance(edl_payload, dict):
        return {"status": "blocked", "reason": "edl_missing"}
    edl = EDL.model_validate(edl_payload)
    if not edl.clips:
        return {
            "status": "blocked",
            "reason": "edl_clips_missing",
            "missing_slots": [slot.id for slot in edl.unfilled_slots()],
            "message": "素材未填坑，不能渲染；先补 licensed_assets 或 generated_asset_requests。",
        }

    project_dir_text = _text(params.get("project_dir"))
    if not project_dir_text:
        return {"status": "blocked", "reason": "project_dir_required"}
    project_dir = Path(project_dir_text)
    output = Path(_text(params.get("output_path")) or str(project_dir / "final" / f"{asset_id}.mp4"))
    missing_inputs = [
        str(project_dir / "videos" / f"{clip.shot_id}.mp4")
        for clip in edl.clips
        if not (project_dir / "videos" / f"{clip.shot_id}.mp4").exists()
    ]
    if missing_inputs:
        return {"status": "blocked", "reason": "render_inputs_missing", "missing_inputs": missing_inputs}

    command = Renderer(
        ffmpeg_path=_text(params.get("ffmpeg_path")) or "ffmpeg",
        ffprobe_path=_text(params.get("ffprobe_path")) or "ffprobe",
    ).build_final_command(edl, project_dir, output)
    return {
        "status": "ready",
        "asset_id": asset_id,
        "render_status": "command_ready_not_executed",
        "duration_sec": edl.total_duration_sec(),
        "output_path": str(output),
        "command": command,
    }


def render_faceless_animatic(store: "AgentCoreStore", params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Render a local text-card animatic for a faceless video asset.

    This is the first real mp4 closure point for CPF-08.  It writes only inside
    ``project_dir`` and labels the result as an animatic/sample, not a final
    publishable video.  It does not use external media or paid providers.
    """

    params = dict(params or {})
    asset_id = _text(params.get("asset_id"))
    if not asset_id:
        return {"status": "error", "reason": "asset_id is required"}
    asset = store.get_content_asset(asset_id)
    content = asset.get("content") or {}
    if asset.get("type") != "video" or content.get("production_kind") != "faceless_video":
        return {"status": "error", "reason": "asset is not a faceless video content asset"}
    edl_payload = content.get("edl")
    if not isinstance(edl_payload, dict):
        return {"status": "blocked", "reason": "edl_missing"}
    edl = EDL.model_validate(edl_payload)
    if not edl.slots:
        return {"status": "blocked", "reason": "edl_slots_missing"}

    project_dir_text = _text(params.get("project_dir"))
    if not project_dir_text:
        return {"status": "blocked", "reason": "project_dir_required"}
    project_dir = Path(project_dir_text)
    frames_dir = project_dir / "frames"
    final_dir = project_dir / "final"
    frames_dir.mkdir(parents=True, exist_ok=True)
    final_dir.mkdir(parents=True, exist_ok=True)

    ffmpeg_path = _text(params.get("ffmpeg_path")) or "ffmpeg"
    ffprobe_path = _text(params.get("ffprobe_path")) or "ffprobe"
    resolution = edl.resolution
    frame_paths = []
    for slot in sorted(edl.slots, key=lambda item: item.order):
        frame_path = frames_dir / f"{slot.shot_id or slot.id}.png"
        _write_frame_card(frame_path=frame_path, slot=slot, resolution=resolution)
        frame_paths.append(str(frame_path))

    output = Path(_text(params.get("output_path")) or str(final_dir / f"{asset_id}_animatic.mp4"))
    try:
        # Text is already baked into local frame cards. Keep subtitles out of
        # the actual ffmpeg render path because packaged ffmpeg builds may not
        # include drawtext.
        render_edl = edl.model_copy(update={"subtitles": []})
        result = Renderer(ffmpeg_path=ffmpeg_path, ffprobe_path=ffprobe_path).render_animatic(
            render_edl, project_dir, output,
        )
    except (FileNotFoundError, RenderError, ValueError) as exc:
        return {"status": "blocked", "reason": "animatic_render_failed", "message": str(exc)[:2000]}

    updated_content = dict(content)
    render_outputs = list(updated_content.get("render_outputs") or [])
    render_outputs.append({
        "kind": "animatic",
        "status": "rendered",
        "output_path": str(result.output_path),
        "duration_sec": result.duration_sec,
        "project_dir": str(project_dir),
        "frame_count": len(frame_paths),
        "command": result.command,
        "note": "文字分镜样片，不是最终成片；未使用外部素材。",
    })
    updated_content["render_outputs"] = render_outputs
    updated_content["render_status"] = "animatic_rendered"
    updated_content["animatic_path"] = str(result.output_path)
    updated_asset = store.update_content_asset_content(asset_id, updated_content)
    return {
        "status": "ok",
        "asset_id": asset_id,
        "render_status": updated_asset["content"]["render_status"],
        "kind": "animatic",
        "output_path": str(result.output_path),
        "duration_sec": result.duration_sec,
        "frame_count": len(frame_paths),
        "frame_paths": frame_paths,
        "command": result.command,
    }


def fill_faceless_image_materials(store: "AgentCoreStore", params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Turn licensed local images into per-shot video clips and fill EDL clips.

    This is the first real material-fill step for the faceless lane.  It does
    not search or download assets.  It accepts only local images that already
    carry provenance (Pexels or user supplied), converts each image to a
    deterministic mp4 clip under ``project_dir/videos`` and writes the clip map
    back to the content asset.
    """

    params = dict(params or {})
    asset_id = _text(params.get("asset_id"))
    if not asset_id:
        return {"status": "error", "reason": "asset_id is required"}
    asset = store.get_content_asset(asset_id)
    content = asset.get("content") or {}
    if asset.get("type") != "video" or content.get("production_kind") != "faceless_video":
        return {"status": "error", "reason": "asset is not a faceless video content asset"}

    edl_payload = content.get("edl")
    if not isinstance(edl_payload, dict):
        return {"status": "blocked", "reason": "edl_missing"}
    edl = EDL.model_validate(edl_payload)
    if not edl.slots:
        return {"status": "blocked", "reason": "edl_slots_missing"}

    project_dir_text = _text(params.get("project_dir"))
    if not project_dir_text:
        return {"status": "blocked", "reason": "project_dir_required"}
    project_dir = Path(project_dir_text)
    videos_dir = project_dir / "videos"
    videos_dir.mkdir(parents=True, exist_ok=True)

    raw_materials = params.get("materials")
    if not isinstance(raw_materials, list) or not raw_materials:
        return {"status": "error", "reason": "materials list is required"}

    ffmpeg_path = _text(params.get("ffmpeg_path")) or "ffmpeg"
    ffprobe_path = _text(params.get("ffprobe_path")) or "ffprobe"
    slot_by_id = {slot.id: slot for slot in edl.slots}
    slots_by_shot = {slot.shot_id: slot for slot in edl.slots if slot.shot_id}
    existing_clips = [dict(clip.model_dump()) for clip in edl.clips]
    filled_slot_ids = {clip["slot_id"] for clip in existing_clips}
    candidate_slots = [slot for slot in sorted(edl.slots, key=lambda item: item.order) if slot.id not in filled_slot_ids]
    filled_assets: list[dict[str, Any]] = []
    clip_paths: list[str] = []
    commands: list[list[str]] = []

    for index, raw in enumerate(raw_materials, start=1):
        if not isinstance(raw, dict):
            return {"status": "error", "reason": f"material {index} must be an object"}
        slot = _resolve_material_slot(raw, slot_by_id, slots_by_shot, candidate_slots)
        if slot is None:
            return {"status": "error", "reason": f"material {index} has no matching slot"}
        if slot.id in filled_slot_ids:
            existing_clips = [clip for clip in existing_clips if clip["slot_id"] != slot.id]
            filled_slot_ids.remove(slot.id)

        material = _normalise_image_material(raw)
        if material.get("status") != "ok":
            return material

        image_path = Path(material["local_path"])
        shot_id = _text(raw.get("shot_id") or slot.shot_id or slot.id)
        if not shot_id:
            return {"status": "error", "reason": f"material {index} missing shot_id"}
        clip_path = videos_dir / f"{shot_id}.mp4"
        try:
            render_result = _render_image_material_clip(
                image_path=image_path,
                clip_path=clip_path,
                duration_sec=float(slot.duration_sec),
                resolution=edl.resolution,
                fps=edl.fps,
                ffmpeg_path=ffmpeg_path,
                ffprobe_path=ffprobe_path,
            )
        except (FileNotFoundError, RenderError, ValueError) as exc:
            return {"status": "blocked", "reason": "image_clip_render_failed", "message": str(exc)[:2000]}

        clip_entry = {
            "slot_id": slot.id,
            "shot_id": shot_id,
            "source_in_sec": 0.0,
            "source_out_sec": float(slot.duration_sec),
        }
        existing_clips.append(clip_entry)
        filled_slot_ids.add(slot.id)
        if slot in candidate_slots:
            candidate_slots.remove(slot)
        clip_paths.append(str(clip_path))
        commands.append(render_result["command"])
        filled_assets.append({
            "kind": "image_to_video_clip",
            "status": "clip_rendered",
            "slot_id": slot.id,
            "shot_id": shot_id,
            "local_path": str(image_path),
            "rendered_clip_path": str(clip_path),
            "duration_sec": render_result["duration_sec"],
            "provider": material["provider"],
            "source_url": material.get("source_url", ""),
            "author": material.get("author", ""),
            "license": material["license"],
            "sha256": material["sha256"],
        })

    updated_edl = dict(edl_payload)
    sorted_clips = sorted(existing_clips, key=lambda clip: slot_by_id.get(clip["slot_id"], edl.slots[-1]).order)
    updated_edl["clips"] = sorted_clips
    updated_edl["unfilled_slots"] = [
        slot.id for slot in sorted(edl.slots, key=lambda item: item.order)
        if slot.id not in {clip["slot_id"] for clip in sorted_clips}
    ]

    updated_content = dict(content)
    updated_content["edl"] = updated_edl
    updated_content["licensed_assets"] = list(updated_content.get("licensed_assets") or []) + filled_assets
    updated_content["licensed_asset_requirements"] = _mark_requirements_filled(
        updated_content.get("licensed_asset_requirements"), filled_assets,
    )
    updated_content["shot_list"] = _mark_shots_filled(updated_content.get("shot_list"), filled_assets)
    all_filled = not updated_edl["unfilled_slots"]
    updated_content["video_status"] = "materials_filled" if all_filled else "materials_partial"
    updated_content["render_status"] = "clips_ready" if all_filled else "materials_partial"
    updated_content["quality_gates"] = _update_material_quality_gates(updated_content.get("quality_gates"), all_filled)

    updated_asset = store.update_content_asset_content(asset_id, updated_content)
    return {
        "status": "ok",
        "asset_id": asset_id,
        "filled_count": len(filled_assets),
        "clip_count": len(updated_edl["clips"]),
        "missing_slots": updated_edl["unfilled_slots"],
        "render_status": updated_asset["content"]["render_status"],
        "clip_paths": clip_paths,
        "commands": commands,
        "licensed_assets": filled_assets,
    }


def render_faceless_final(store: "AgentCoreStore", params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Render a local review-cut mp4 from filled EDL clips.

    The output is deterministic and honest: subtitle sidecars are generated
    from EDL narration, optional voice/BGM files are mixed only when supplied
    with provenance, and the result remains a review cut rather than an
    automatically publishable final.
    """

    params = dict(params or {})
    asset_id = _text(params.get("asset_id"))
    if not asset_id:
        return {"status": "error", "reason": "asset_id is required"}
    asset = store.get_content_asset(asset_id)
    content = asset.get("content") or {}
    if asset.get("type") != "video" or content.get("production_kind") != "faceless_video":
        return {"status": "error", "reason": "asset is not a faceless video content asset"}
    edl_payload = content.get("edl")
    if not isinstance(edl_payload, dict):
        return {"status": "blocked", "reason": "edl_missing"}
    edl = EDL.model_validate(edl_payload)
    if not edl.clips:
        return {
            "status": "blocked",
            "reason": "edl_clips_missing",
            "missing_slots": [slot.id for slot in edl.unfilled_slots()],
        }

    project_dir_text = _text(params.get("project_dir"))
    if not project_dir_text:
        return {"status": "blocked", "reason": "project_dir_required"}
    project_dir = Path(project_dir_text)
    output = Path(_text(params.get("output_path")) or str(project_dir / "final" / f"{asset_id}_rough_cut.mp4"))
    missing_inputs = [
        str(project_dir / "videos" / f"{clip.shot_id}.mp4")
        for clip in edl.clips
        if not (project_dir / "videos" / f"{clip.shot_id}.mp4").exists()
    ]
    if missing_inputs:
        return {"status": "blocked", "reason": "render_inputs_missing", "missing_inputs": missing_inputs}

    ffmpeg_path = _text(params.get("ffmpeg_path")) or "ffmpeg"
    ffprobe_path = _text(params.get("ffprobe_path")) or "ffprobe"
    burn_subtitles = bool(params.get("burn_subtitles"))
    write_subtitles = params.get("write_subtitles", True) is not False
    subtitle_path: Path | None = None
    if write_subtitles:
        subtitle_path = Path(_text(params.get("subtitle_path")) or str(project_dir / "subtitles" / f"{asset_id}.srt"))
        try:
            _write_srt_sidecar(subtitle_path, edl)
        except ValueError as exc:
            return {"status": "blocked", "reason": "subtitle_export_failed", "message": str(exc)[:1000]}

    voice_material = _normalise_audio_material(
        params.get("voiceover_audio_path") or params.get("voice_audio_path"),
        params.get("voiceover_provenance") if isinstance(params.get("voiceover_provenance"), dict) else {},
        kind="voice",
    )
    if voice_material and voice_material.get("status") != "ok":
        return voice_material
    bgm_material = _normalise_audio_material(
        params.get("bgm_audio_path") or params.get("music_audio_path"),
        params.get("bgm_provenance") if isinstance(params.get("bgm_provenance"), dict) else {},
        kind="bgm",
    )
    if bgm_material and bgm_material.get("status") != "ok":
        return bgm_material
    voice_volume = _float_param(params.get("voice_volume"), default=1.0, minimum=0.0, maximum=2.0)
    bgm_volume = _float_param(params.get("bgm_volume"), default=0.18, minimum=0.0, maximum=1.0)

    try:
        render_edl = edl if burn_subtitles else edl.model_copy(update={"subtitles": []})
        result = Renderer(ffmpeg_path=ffmpeg_path, ffprobe_path=ffprobe_path).render_final(
            render_edl,
            project_dir,
            output,
            voice_path=Path(voice_material["local_path"]) if voice_material else None,
            bgm_path=Path(bgm_material["local_path"]) if bgm_material else None,
            voice_volume=voice_volume,
            bgm_volume=bgm_volume,
        )
    except (FileNotFoundError, RenderError, ValueError) as exc:
        return {"status": "blocked", "reason": "final_render_failed", "message": str(exc)[:2000]}

    audio_tracks = []
    if voice_material:
        audio_tracks.append({key: value for key, value in voice_material.items() if key != "status"} | {
            "kind": "voice",
            "volume": voice_volume,
        })
    if bgm_material:
        audio_tracks.append({key: value for key, value in bgm_material.items() if key != "status"} | {
            "kind": "bgm",
            "volume": bgm_volume,
        })
    review_cut = bool(audio_tracks or subtitle_path)
    output_kind = "final_review_cut" if review_cut else "final_rough_cut"
    render_status = "final_review_cut_rendered" if review_cut else "final_rough_cut_rendered"

    updated_content = dict(content)
    render_outputs = list(updated_content.get("render_outputs") or [])
    render_outputs.append({
        "kind": output_kind,
        "status": "rendered",
        "output_path": str(result.output_path),
        "duration_sec": result.duration_sec,
        "project_dir": str(project_dir),
        "command": result.command,
        "subtitles_burned": burn_subtitles,
        "subtitle_path": str(subtitle_path) if subtitle_path else "",
        "audio_tracks": audio_tracks,
        "note": "本地授权素材审片版本；字幕/音轨来源可追溯，仍需人工审片后发布。",
    })
    updated_content["render_outputs"] = render_outputs
    updated_content["render_status"] = render_status
    updated_content["final_rough_cut_path"] = str(result.output_path)
    if review_cut:
        updated_content["final_review_cut_path"] = str(result.output_path)
        updated_content["subtitle_path"] = str(subtitle_path) if subtitle_path else ""
        updated_content["audio_tracks"] = audio_tracks
    updated_asset = store.update_content_asset_content(asset_id, updated_content)
    return {
        "status": "ok",
        "asset_id": asset_id,
        "render_status": updated_asset["content"]["render_status"],
        "kind": output_kind,
        "output_path": str(result.output_path),
        "duration_sec": result.duration_sec,
        "subtitles_burned": burn_subtitles,
        "subtitle_path": str(subtitle_path) if subtitle_path else "",
        "audio_track_count": len(audio_tracks),
        "audio_tracks": audio_tracks,
        "command": result.command,
    }


def _write_srt_sidecar(path: Path, edl: EDL) -> None:
    entries = list(edl.subtitles)
    if not entries:
        cursor = 0.0
        for slot in sorted(edl.slots, key=lambda item: item.order):
            text = _text(slot.narration)
            if text:
                entries.append(type("SubtitleLike", (), {
                    "text": text,
                    "start_sec": cursor,
                    "end_sec": cursor + float(slot.duration_sec),
                })())
            cursor += float(slot.duration_sec)
    if not entries:
        raise ValueError("EDL has no subtitles or narration to export")
    lines: list[str] = []
    for index, item in enumerate(entries, start=1):
        start = max(0.0, float(getattr(item, "start_sec", 0.0)))
        end = max(start + 0.1, float(getattr(item, "end_sec", start + 0.1)))
        text = str(getattr(item, "text", "") or "").strip()
        if not text:
            continue
        lines.extend([
            str(index),
            f"{_srt_timestamp(start)} --> {_srt_timestamp(end)}",
            text,
            "",
        ])
    if not lines:
        raise ValueError("EDL subtitle text is empty")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _srt_timestamp(seconds: float) -> str:
    millis = int(round(max(0.0, float(seconds)) * 1000))
    hours, remainder = divmod(millis, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, ms = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def _normalise_audio_material(raw_path: Any, provenance: dict[str, Any], *, kind: str) -> dict[str, Any] | None:
    local_path_text = _text(raw_path)
    if not local_path_text:
        return None
    local_path = Path(local_path_text)
    if not local_path.exists() or not local_path.is_file():
        return {"status": "error", "reason": f"{kind} audio file missing: {local_path}"}
    if local_path.suffix.lower() not in {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg"}:
        return {"status": "error", "reason": f"unsupported {kind} audio type: {local_path.suffix}"}

    provenance = dict(provenance or {})
    provider = _text(provenance.get("provider") or "user_supplied").lower()
    source_url = _text(provenance.get("source_url") or provenance.get("url"), limit=1000)
    license_text = _text(provenance.get("license") or ("User supplied" if provider == "user_supplied" else ""))
    if provider == "user_supplied":
        license_text = license_text or "User supplied"
    elif provider in {"pixabay", "pexels", "freesound"}:
        if not source_url.startswith("https://"):
            return {"status": "error", "reason": f"{kind} audio provider requires https source_url"}
        if not license_text:
            return {"status": "error", "reason": f"{kind} audio provider requires license"}
    elif provider == "volcengine_tts_v1":
        license_text = license_text or "Volcengine TTS generated audio"
    else:
        return {"status": "error", "reason": f"unsupported {kind} audio provider: {provider}"}

    sha256 = _sha256_file(local_path)
    expected_hash = _text(provenance.get("sha256") or provenance.get("download_hash")).lower()
    if expected_hash and expected_hash != sha256:
        return {"status": "error", "reason": f"{kind} audio sha256 does not match local file"}
    return {
        "status": "ok",
        "local_path": str(local_path),
        "provider": provider,
        "source_url": source_url,
        "author": _text(provenance.get("author") or "Unknown", limit=160),
        "license": license_text,
        "sha256": sha256,
    }


def _float_param(value: Any, *, default: float, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return min(maximum, max(minimum, number))


def _resolve_material_slot(
    material: dict[str, Any],
    slot_by_id: dict[str, TimelineSlot],
    slots_by_shot: dict[str, TimelineSlot],
    candidate_slots: list[TimelineSlot],
) -> TimelineSlot | None:
    slot_id = _text(material.get("slot_id"))
    shot_id = _text(material.get("shot_id"))
    if slot_id:
        return slot_by_id.get(slot_id)
    if shot_id:
        return slots_by_shot.get(shot_id)
    return candidate_slots[0] if candidate_slots else None


def _normalise_image_material(raw: dict[str, Any]) -> dict[str, Any]:
    local_path = Path(_text(raw.get("local_path") or raw.get("image_path") or raw.get("path")))
    if not str(local_path):
        return {"status": "error", "reason": "material local_path is required"}
    if not local_path.exists() or not local_path.is_file():
        return {"status": "error", "reason": f"material file missing: {local_path}"}
    if local_path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
        return {"status": "error", "reason": f"unsupported image material type: {local_path.suffix}"}

    provider = _text(raw.get("provider") or "user_supplied").lower()
    source_url = _text(raw.get("source_url") or raw.get("url"), limit=1000)
    license_text = _text(raw.get("license") or raw.get("licence") or ("User supplied" if provider == "user_supplied" else ""))
    if provider == "pexels":
        if not source_url.startswith("https://www.pexels.com/"):
            return {"status": "error", "reason": "Pexels material requires https://www.pexels.com/ source_url"}
        if license_text != "Pexels License":
            return {"status": "error", "reason": "Pexels material requires Pexels License"}
    elif provider == "user_supplied":
        license_text = license_text or "User supplied"
    else:
        return {"status": "error", "reason": f"unsupported image material provider: {provider}"}

    sha256 = _sha256_file(local_path)
    expected_hash = _text(raw.get("sha256") or raw.get("download_hash")).lower()
    if expected_hash and expected_hash != sha256:
        return {"status": "error", "reason": "material sha256 does not match local file"}
    return {
        "status": "ok",
        "local_path": str(local_path),
        "provider": provider,
        "source_url": source_url,
        "author": _text(raw.get("author") or raw.get("photographer") or "Unknown", limit=160),
        "license": license_text,
        "sha256": sha256,
    }


def _render_image_material_clip(
    *,
    image_path: Path,
    clip_path: Path,
    duration_sec: float,
    resolution: str,
    fps: int,
    ffmpeg_path: str,
    ffprobe_path: str,
) -> dict[str, Any]:
    width, height = _resolution_parts(resolution)
    clip_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        ffmpeg_path,
        "-y",
        "-loop", "1",
        "-t", _duration_arg(duration_sec),
        "-i", str(image_path),
        "-vf",
        (
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={int(fps)}"
        ),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-an",
        str(clip_path),
    ]
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        raise RenderError("\n".join(str(result.stderr or "").splitlines()[-50:]) or "ffmpeg failed")
    if not clip_path.exists() or clip_path.stat().st_size <= 0:
        raise RenderError(f"clip output missing or empty: {clip_path}")
    duration = Renderer(ffprobe_path=ffprobe_path).probe_duration(clip_path)
    return {"command": command, "duration_sec": duration}


def _mark_requirements_filled(value: Any, filled_assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    requirements = [dict(item) for item in value] if isinstance(value, list) else []
    by_shot = {asset["shot_id"]: asset for asset in filled_assets}
    for requirement in requirements:
        asset = by_shot.get(_text(requirement.get("shot_id")))
        if not asset:
            continue
        requirement.update({
            "status": "filled",
            "source_url": asset.get("source_url", ""),
            "license": asset.get("license", ""),
            "download_hash": asset.get("sha256", ""),
            "rendered_clip_path": asset.get("rendered_clip_path", ""),
        })
    return requirements


def _mark_shots_filled(value: Any, filled_assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    shots = [dict(item) for item in value] if isinstance(value, list) else []
    by_shot = {asset["shot_id"]: asset for asset in filled_assets}
    for shot in shots:
        asset = by_shot.get(_text(shot.get("id")))
        if not asset:
            continue
        shot["status"] = "material_filled"
        shot["material_provenance"] = {
            "provider": asset.get("provider", ""),
            "source_url": asset.get("source_url", ""),
            "license": asset.get("license", ""),
            "sha256": asset.get("sha256", ""),
        }
    return shots


def _update_material_quality_gates(value: Any, all_filled: bool) -> list[dict[str, Any]]:
    gates = [dict(item) for item in value] if isinstance(value, list) else []
    for gate in gates:
        if gate.get("name") == "版权/来源门":
            gate["status"] = "pass" if all_filled else "partial"
            gate["note"] = "已登记素材来源、许可证和本地 hash" if all_filled else "部分镜头已登记素材来源，仍有槽位未填"
        elif gate.get("name") == "素材适配门":
            gate["status"] = "pass" if all_filled else "pending_material_review"
    return gates


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _duration_arg(value: float) -> str:
    return f"{float(value):.3f}".rstrip("0").rstrip(".")


def _write_frame_card(*, frame_path: Path, slot: TimelineSlot, resolution: str) -> None:
    width, height = _resolution_parts(resolution)
    card_text = _frame_card_text(slot)
    _write_bitmap_card_png(frame_path, width, height, card_text.splitlines())


def _frame_card_text(slot: TimelineSlot) -> str:
    lines = [
        f"SHOT {slot.order:02d}",
        "",
        "VISUAL",
        slot.camera_direction or "text card / stock material placeholder",
        "",
        "VOICEOVER",
    ]
    narration = slot.narration or "待补旁白"
    for line in textwrap.wrap(narration, width=20):
        lines.append(line)
    return "\n".join(lines)


def _resolution_parts(value: str) -> tuple[int, int]:
    try:
        width, height = str(value).lower().split("x", 1)
        return int(width), int(height)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid EDL resolution: {value}") from exc


_FONT_5X7 = {
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "B": ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    "C": ("01111", "10000", "10000", "10000", "10000", "10000", "01111"),
    "D": ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "F": ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    "G": ("01111", "10000", "10000", "10111", "10001", "10001", "01111"),
    "H": ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    "I": ("11111", "00100", "00100", "00100", "00100", "00100", "11111"),
    "J": ("00111", "00010", "00010", "00010", "10010", "10010", "01100"),
    "K": ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    "N": ("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "P": ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    "Q": ("01110", "10001", "10001", "10001", "10101", "10010", "01101"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "U": ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
    "V": ("10001", "10001", "10001", "10001", "10001", "01010", "00100"),
    "W": ("10001", "10001", "10001", "10101", "10101", "11011", "10001"),
    "X": ("10001", "10001", "01010", "00100", "01010", "10001", "10001"),
    "Y": ("10001", "10001", "01010", "00100", "00100", "00100", "00100"),
    "Z": ("11111", "00001", "00010", "00100", "01000", "10000", "11111"),
    "0": ("01110", "10001", "10011", "10101", "11001", "10001", "01110"),
    "1": ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    "2": ("01110", "10001", "00001", "00010", "00100", "01000", "11111"),
    "3": ("11110", "00001", "00001", "01110", "00001", "00001", "11110"),
    "4": ("00010", "00110", "01010", "10010", "11111", "00010", "00010"),
    "5": ("11111", "10000", "10000", "11110", "00001", "00001", "11110"),
    "6": ("01110", "10000", "10000", "11110", "10001", "10001", "01110"),
    "7": ("11111", "00001", "00010", "00100", "01000", "01000", "01000"),
    "8": ("01110", "10001", "10001", "01110", "10001", "10001", "01110"),
    "9": ("01110", "10001", "10001", "01111", "00001", "00001", "01110"),
    " ": ("00000", "00000", "00000", "00000", "00000", "00000", "00000"),
    "-": ("00000", "00000", "00000", "11111", "00000", "00000", "00000"),
    ".": ("00000", "00000", "00000", "00000", "00000", "01100", "01100"),
    ":": ("00000", "01100", "01100", "00000", "01100", "01100", "00000"),
    "/": ("00001", "00010", "00010", "00100", "01000", "01000", "10000"),
    "?": ("01110", "10001", "00001", "00010", "00100", "00000", "00100"),
}


def _write_bitmap_card_png(path: Path, width: int, height: int, lines: list[str]) -> None:
    background = (17, 24, 39)
    accent = (255, 99, 92)
    text = (241, 245, 249)
    muted = (148, 163, 184)
    pixels = bytearray(background * (width * height))

    def fill_rect(x0: int, y0: int, x1: int, y1: int, color: tuple[int, int, int]) -> None:
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(width, x1), min(height, y1)
        for y in range(y0, y1):
            row = y * width * 3
            for x in range(x0, x1):
                idx = row + x * 3
                pixels[idx:idx + 3] = bytes(color)

    fill_rect(0, 0, width, max(8, height // 90), accent)
    fill_rect(max(20, width // 18), max(40, height // 20), width - max(20, width // 18), max(42, height // 20 + 2), muted)

    x = max(20, width // 14)
    y = max(70, height // 8)
    scale = max(2, min(5, width // 120))
    line_height = 9 * scale
    max_chars = max(18, width // (6 * scale))
    rendered_lines: list[str] = []
    for line in lines:
        rendered_lines.extend(textwrap.wrap(_ascii_card_line(line), width=max_chars) or [""])
    for index, line in enumerate(rendered_lines[: max(3, (height - y - 30) // line_height)]):
        color = accent if index == 0 else text
        _draw_text(pixels, width, height, x, y + index * line_height, line, scale, color)

    raw = bytearray()
    stride = width * 3
    for y_pos in range(height):
        raw.append(0)
        raw.extend(pixels[y_pos * stride:(y_pos + 1) * stride])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_png_bytes(width, height, bytes(raw)))


def _draw_text(
    pixels: bytearray, width: int, height: int, x: int, y: int,
    value: str, scale: int, color: tuple[int, int, int],
) -> None:
    cursor = x
    for ch in value.upper():
        glyph = _FONT_5X7.get(ch, _FONT_5X7["?"])
        for gy, row in enumerate(glyph):
            for gx, bit in enumerate(row):
                if bit != "1":
                    continue
                for sy in range(scale):
                    for sx in range(scale):
                        px = cursor + gx * scale + sx
                        py = y + gy * scale + sy
                        if 0 <= px < width and 0 <= py < height:
                            idx = (py * width + px) * 3
                            pixels[idx:idx + 3] = bytes(color)
        cursor += 6 * scale


def _ascii_card_line(value: str) -> str:
    return "".join(ch if ch.isascii() and (ch.upper() in _FONT_5X7 or ch == " ") else "?" for ch in str(value or ""))


def _png_bytes(width: int, height: int, raw_scanlines: bytes) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw_scanlines, 9))
        + chunk(b"IEND", b"")
    )
