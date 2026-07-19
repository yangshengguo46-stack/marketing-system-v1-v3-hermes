"""Renderer-neutral contracts for native faceless-video production."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable


VIDEO_IR_VERSION = "marketing.video.ir.v1"
RENDER_PLAN_VERSION = "marketing.video.render_plan.v1"
FFMPEG_RENDERER = "ffmpeg_timeline_v1"
REMOTION_RENDERER = "remotion_scene_v1"
HYPERFRAMES_RENDERER = "hyperframes_scene_v1"

_RENDERER_ALIASES = {
    "ffmpeg": FFMPEG_RENDERER,
    FFMPEG_RENDERER: FFMPEG_RENDERER,
    "remotion": REMOTION_RENDERER,
    REMOTION_RENDERER: REMOTION_RENDERER,
    "hyperframes": HYPERFRAMES_RENDERER,
    HYPERFRAMES_RENDERER: HYPERFRAMES_RENDERER,
}
_MOTION_CAPABILITIES = {
    "none": set(),
    "straight_cut": {"straight_cut"},
    "kinetic_typography": {"kinetic_typography"},
    "data_visualization": {"data_visualization"},
    "react_component": {"react_component"},
    "brand_layout": {"brand_layout"},
    "html_css_motion": {"html_css_motion"},
    "svg_motion": {"svg_motion"},
    "designed_transition": {"designed_transition"},
    "layered_composition": {"layered_composition"},
}
_ALLOWED_CAPABILITIES = {
    "source_media",
    "crop_cover",
    "fit_contain",
    "straight_cut",
    "static_text",
    *_MOTION_CAPABILITIES.keys(),
} - {"none"}
_RENDERER_CAPABILITIES = {
    FFMPEG_RENDERER: {
        "source_media",
        "crop_cover",
        "fit_contain",
        "straight_cut",
    },
    REMOTION_RENDERER: _ALLOWED_CAPABILITIES,
    HYPERFRAMES_RENDERER: _ALLOWED_CAPABILITIES
    - {"react_component", "data_visualization"},
}
_HYPERFRAMES_HINTS = {"html_css_motion", "svg_motion", "designed_transition"}
_REMOTION_REQUIRED = {"react_component", "data_visualization"}
_REMOTION_HINTS = {
    "kinetic_typography",
    "brand_layout",
    "static_text",
}
_VISUAL_PRESENTATIONS = {"full_bleed", "inset_card", "letterbox"}
_SUBJECT_ANCHORS = {"center", "left", "right", "top", "bottom"}


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _number(
    value: Any,
    field: str,
    *,
    minimum: float,
    maximum: float,
) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if result < minimum or result > maximum:
        raise ValueError(f"{field} must be between {minimum} and {maximum}")
    return result


def _integer(
    value: Any,
    field: str,
    *,
    minimum: int,
    maximum: int,
) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer") from exc
    if result < minimum or result > maximum:
        raise ValueError(f"{field} must be between {minimum} and {maximum}")
    return result


def _text(value: Any, field: str, *, maximum: int, required: bool = False) -> str:
    result = str(value or "").strip()
    if required and not result:
        raise ValueError(f"{field} is required")
    if len(result) > maximum:
        raise ValueError(f"{field} must not exceed {maximum} characters")
    return result


def _string_list(
    value: Any,
    field: str,
    *,
    maximum_items: int,
    maximum_length: int,
) -> list[str]:
    raw = value or []
    if not isinstance(raw, list) or len(raw) > maximum_items:
        raise ValueError(f"{field} must be a bounded list")
    result = [
        _text(item, f"{field}[]", maximum=maximum_length, required=True) for item in raw
    ]
    if len(result) != len(set(result)):
        raise ValueError(f"{field} must not contain duplicates")
    return result


def _renderer(value: Any, field: str, *, allow_auto: bool = False) -> str:
    raw = str(value or ("auto" if allow_auto else FFMPEG_RENDERER)).strip().lower()
    if allow_auto and raw == "auto":
        return raw
    result = _RENDERER_ALIASES.get(raw)
    if not result:
        raise ValueError(f"{field} references an unknown renderer")
    return result


def _normalize_scene(scene: Any, index: int) -> dict[str, Any]:
    if not isinstance(scene, dict):
        raise ValueError("each video IR scene must be an object")
    scene_id = _text(
        scene.get("id"),
        f"scenes[{index}].id",
        maximum=128,
        required=True,
    )
    duration = _number(
        scene.get("duration"),
        f"scenes[{index}].duration",
        minimum=0.1,
        maximum=120.0,
    )
    visuals = scene.get("visuals")
    if not isinstance(visuals, list) or not visuals or len(visuals) > 20:
        raise ValueError(f"scenes[{index}].visuals requires between 1 and 20 items")
    normalized_visuals = []
    for visual_index, visual in enumerate(visuals):
        if not isinstance(visual, dict):
            raise ValueError("each scene visual must be an object")
        fit = str(visual.get("fit") or "cover").strip().lower()
        if fit not in {"cover", "contain"}:
            raise ValueError("scene visual fit must be cover or contain")
        presentation = str(
            visual.get("presentation") or "full_bleed"
        ).strip().lower()
        if presentation not in _VISUAL_PRESENTATIONS:
            raise ValueError("scene visual presentation is unsupported")
        if presentation != "full_bleed" and fit != "contain":
            raise ValueError("non-full-bleed visuals must use contain fit")
        subject_anchor = str(
            visual.get("subject_anchor") or "center"
        ).strip().lower()
        if subject_anchor not in _SUBJECT_ANCHORS:
            raise ValueError("scene visual subject_anchor is unsupported")
        normalized_visuals.append({
            "media_asset_id": _text(
                visual.get("media_asset_id"),
                f"scenes[{index}].visuals[{visual_index}].media_asset_id",
                maximum=256,
                required=True,
            ),
            "source_in": round(
                _number(
                    visual.get("source_in", 0),
                    f"scenes[{index}].visuals[{visual_index}].source_in",
                    minimum=0,
                    maximum=86_400,
                ),
                3,
            ),
            "fit": fit,
            "presentation": presentation,
            "subject_anchor": subject_anchor,
        })

    text_layers = scene.get("text") or []
    if not isinstance(text_layers, list) or len(text_layers) > 20:
        raise ValueError(f"scenes[{index}].text must be a bounded list")
    normalized_text = []
    for text_index, layer in enumerate(text_layers):
        if not isinstance(layer, dict):
            raise ValueError("each scene text layer must be an object")
        normalized_text.append({
            "text": _text(
                layer.get("text"),
                f"scenes[{index}].text[{text_index}].text",
                maximum=500,
                required=True,
            ),
            "role": _text(
                layer.get("role") or "body",
                f"scenes[{index}].text[{text_index}].role",
                maximum=64,
                required=True,
            ),
            "style_token": _text(
                layer.get("style_token"),
                f"scenes[{index}].text[{text_index}].style_token",
                maximum=128,
            ),
        })

    motion_intent = _string_list(
        scene.get("motion_intent"),
        f"scenes[{index}].motion_intent",
        maximum_items=20,
        maximum_length=64,
    )
    unknown_motion = set(motion_intent) - set(_MOTION_CAPABILITIES)
    if unknown_motion:
        raise ValueError(f"unknown motion intent: {sorted(unknown_motion)}")
    declared_capabilities = _string_list(
        scene.get("required_capabilities"),
        f"scenes[{index}].required_capabilities",
        maximum_items=20,
        maximum_length=64,
    )
    unknown_capabilities = set(declared_capabilities) - _ALLOWED_CAPABILITIES
    if unknown_capabilities:
        raise ValueError(
            f"unknown renderer capabilities: {sorted(unknown_capabilities)}"
        )
    capabilities = {"source_media", "straight_cut"}
    capabilities.update(
        "crop_cover" if visual["fit"] == "cover" else "fit_contain"
        for visual in normalized_visuals
    )
    capabilities.update(declared_capabilities)
    for item in motion_intent:
        capabilities.update(_MOTION_CAPABILITIES[item])
    if len(normalized_visuals) > 1:
        capabilities.add("layered_composition")
    if any(
        visual["presentation"] == "inset_card" for visual in normalized_visuals
    ):
        capabilities.add("brand_layout")
    if normalized_text:
        capabilities.add("static_text")

    constraints = scene.get("constraints") or {}
    if not isinstance(constraints, dict):
        raise ValueError("scene constraints must be an object")
    rights_required = constraints.get("rights_required", True)
    if rights_required is not True:
        raise ValueError("scene rights_required must remain true")
    policy = scene.get("renderer_policy") or {}
    if not isinstance(policy, dict):
        raise ValueError("scene renderer_policy must be an object")
    normalized = {
        "id": scene_id,
        "duration": round(duration, 3),
        "purpose": _text(
            scene.get("purpose"),
            f"scenes[{index}].purpose",
            maximum=2000,
            required=True,
        ),
        "visuals": normalized_visuals,
        "text": normalized_text,
        "motion_intent": motion_intent,
        "required_capabilities": sorted(capabilities),
        "constraints": {
            "safe_area": _text(
                constraints.get("safe_area") or "short_vertical",
                f"scenes[{index}].constraints.safe_area",
                maximum=64,
                required=True,
            ),
            "rights_required": True,
        },
        "renderer_policy": {
            "preference": _renderer(
                policy.get("preference"),
                f"scenes[{index}].renderer_policy.preference",
                allow_auto=True,
            ),
            "fallback": _renderer(
                policy.get("fallback"),
                f"scenes[{index}].renderer_policy.fallback",
            ),
        },
        "review_rules": _string_list(
            scene.get("review_rules"),
            f"scenes[{index}].review_rules",
            maximum_items=20,
            maximum_length=300,
        ),
    }
    scene_hash = _sha256(normalized)
    asserted_hash = str(scene.get("scene_sha256") or "").strip()
    if asserted_hash and asserted_hash != scene_hash:
        raise ValueError(f"scene {scene_id} has a stale scene_sha256")
    normalized["scene_sha256"] = scene_hash
    return normalized


def normalize_video_ir(value: Any) -> dict[str, Any]:
    """Validate and canonicalize one immutable Marketing Video IR."""
    if not isinstance(value, dict):
        raise ValueError("video_ir must be an object")
    if value.get("version") != VIDEO_IR_VERSION:
        raise ValueError(f"video_ir version must be {VIDEO_IR_VERSION}")
    canvas = value.get("canvas") or {}
    if not isinstance(canvas, dict):
        raise ValueError("video_ir canvas must be an object")
    scenes = value.get("scenes")
    if not isinstance(scenes, list) or not scenes or len(scenes) > 100:
        raise ValueError("video_ir requires between 1 and 100 scenes")
    normalized_scenes = [
        _normalize_scene(scene, index) for index, scene in enumerate(scenes)
    ]
    scene_ids = [scene["id"] for scene in normalized_scenes]
    if len(scene_ids) != len(set(scene_ids)):
        raise ValueError("video_ir scene ids must be unique")
    duration = round(sum(float(scene["duration"]) for scene in normalized_scenes), 3)
    if duration > 600:
        raise ValueError("video_ir total duration must not exceed 600 seconds")

    captions = value.get("captions") or []
    if not isinstance(captions, list) or len(captions) > 500:
        raise ValueError("video_ir captions must be a bounded list")
    normalized_captions = []
    for index, cue in enumerate(captions):
        if not isinstance(cue, dict):
            raise ValueError("each video_ir caption must be an object")
        start = _number(
            cue.get("start"), f"captions[{index}].start", minimum=0, maximum=600
        )
        end = _number(cue.get("end"), f"captions[{index}].end", minimum=0, maximum=600)
        text = _text(
            cue.get("text"), f"captions[{index}].text", maximum=200, required=True
        )
        if end <= start or end > duration + 0.05:
            raise ValueError("video_ir caption timing is invalid")
        normalized_captions.append({
            "start": round(start, 3),
            "end": round(end, 3),
            "text": text,
        })

    audio = value.get("audio") or {}
    if not isinstance(audio, dict):
        raise ValueError("video_ir audio must be an object")
    normalized = {
        "version": VIDEO_IR_VERSION,
        "canvas": {
            "width": _integer(
                canvas.get("width", 1080), "canvas.width", minimum=240, maximum=3840
            ),
            "height": _integer(
                canvas.get("height", 1920), "canvas.height", minimum=240, maximum=3840
            ),
            "fps": _integer(
                canvas.get("fps", 30), "canvas.fps", minimum=15, maximum=60
            ),
        },
        "scenes": normalized_scenes,
        "captions": normalized_captions,
        "audio": {
            "voice_asset_id": _text(
                audio.get("voice_asset_id"), "audio.voice_asset_id", maximum=256
            ),
            "music_asset_id": _text(
                audio.get("music_asset_id"), "audio.music_asset_id", maximum=256
            ),
        },
        "review_rules": _string_list(
            value.get("review_rules"),
            "review_rules",
            maximum_items=50,
            maximum_length=300,
        ),
        "duration": duration,
    }
    ir_hash = _sha256(normalized)
    asserted_hash = str(value.get("ir_sha256") or "").strip()
    if asserted_hash and asserted_hash != ir_hash:
        raise ValueError("video_ir has a stale ir_sha256")
    normalized["ir_sha256"] = ir_hash
    return normalized


def video_ir_from_edl(edl: dict[str, Any]) -> dict[str, Any]:
    """Upgrade a normalized legacy EDL into the renderer-neutral IR."""
    scenes = []
    for index, clip in enumerate(edl.get("clips") or [], start=1):
        scenes.append({
            "id": f"scene_{index:03d}",
            "duration": clip["duration"],
            "purpose": "legacy_edl_clip",
            "visuals": [
                {
                    "media_asset_id": clip["media_asset_id"],
                    "source_in": clip.get("source_in", 0),
                    "fit": clip.get("fit", "cover"),
                    "presentation": "full_bleed",
                    "subject_anchor": "center",
                }
            ],
            "text": [],
            "motion_intent": ["straight_cut"],
            "constraints": {
                "safe_area": "short_vertical",
                "rights_required": True,
            },
            "renderer_policy": {
                "preference": "auto",
                "fallback": FFMPEG_RENDERER,
            },
            "review_rules": [],
        })
    return normalize_video_ir({
        "version": VIDEO_IR_VERSION,
        "canvas": {
            "width": edl["width"],
            "height": edl["height"],
            "fps": edl["fps"],
        },
        "scenes": scenes,
        "captions": edl.get("captions") or [],
        "audio": {
            "voice_asset_id": edl.get("voice_asset_id", ""),
            "music_asset_id": edl.get("music_asset_id", ""),
        },
        "review_rules": [],
    })


def _supports(renderer: str, capabilities: set[str]) -> bool:
    return capabilities <= _RENDERER_CAPABILITIES[renderer]


def _ideal_renderer(scene: dict[str, Any]) -> str:
    preference = scene["renderer_policy"]["preference"]
    if preference != "auto":
        return preference
    capabilities = set(scene["required_capabilities"])
    if capabilities & _REMOTION_REQUIRED:
        return REMOTION_RENDERER
    if capabilities & _HYPERFRAMES_HINTS:
        return HYPERFRAMES_RENDERER
    if capabilities & _REMOTION_HINTS:
        return REMOTION_RENDERER
    if "layered_composition" in capabilities:
        return REMOTION_RENDERER
    return FFMPEG_RENDERER


def build_render_plan(
    video_ir: dict[str, Any],
    *,
    enabled_renderers: Iterable[str] = (FFMPEG_RENDERER,),
) -> dict[str, Any]:
    """Build an explainable per-scene capability route without side effects."""
    normalized = normalize_video_ir(video_ir)
    enabled = {_renderer(item, "enabled_renderers[]") for item in enabled_renderers}
    scene_plans = []
    executable = True
    for scene in normalized["scenes"]:
        capabilities = set(scene["required_capabilities"])
        ideal = _ideal_renderer(scene)
        selected = ""
        fallback_used = False
        reason = ""
        if ideal in enabled and _supports(ideal, capabilities):
            selected = ideal
            reason = "preferred renderer is enabled and satisfies every capability"
        else:
            fallback = scene["renderer_policy"]["fallback"]
            if fallback in enabled and _supports(fallback, capabilities):
                selected = fallback
                fallback_used = True
                reason = (
                    "preferred renderer unavailable; declared fallback is equivalent"
                )
            else:
                executable = False
                reason = "no enabled renderer satisfies capabilities: " + ", ".join(
                    sorted(capabilities)
                )
        scene_plans.append({
            "scene_id": scene["id"],
            "scene_sha256": scene["scene_sha256"],
            "preferred_renderer": ideal,
            "renderer": selected,
            "status": "ready" if selected else "unavailable",
            "fallback_used": fallback_used,
            "required_capabilities": sorted(capabilities),
            "reason": reason,
        })
    plan = {
        "version": RENDER_PLAN_VERSION,
        "source_ir_sha256": normalized["ir_sha256"],
        "enabled_renderers": sorted(enabled),
        "scenes": scene_plans,
        "executable": executable,
    }
    plan["render_plan_sha256"] = _sha256(plan)
    return plan


def compile_ffmpeg_edl(
    video_ir: dict[str, Any],
    render_plan: dict[str, Any],
) -> dict[str, Any]:
    """Compile an executable all-FFmpeg plan into the existing renderer input."""
    normalized = normalize_video_ir(video_ir)
    if render_plan.get("source_ir_sha256") != normalized["ir_sha256"]:
        raise ValueError("render plan is stale for this video_ir")
    if render_plan.get("executable") is not True:
        raise ValueError("render plan is not executable")
    planned = {item["scene_id"]: item for item in render_plan.get("scenes") or []}
    clips = []
    for scene in normalized["scenes"]:
        plan = planned.get(scene["id"])
        if not plan or plan.get("scene_sha256") != scene["scene_sha256"]:
            raise ValueError(f"render plan is stale for scene {scene['id']}")
        if plan.get("renderer") != FFMPEG_RENDERER:
            raise ValueError("FFmpeg EDL cannot compile a non-FFmpeg scene")
        if len(scene["visuals"]) != 1:
            raise ValueError("FFmpeg scene compilation requires exactly one visual")
        visual = scene["visuals"][0]
        clips.append({
            "media_asset_id": visual["media_asset_id"],
            "source_in": visual["source_in"],
            "duration": scene["duration"],
            "fit": visual["fit"],
        })
    result = {
        "version": "marketing.faceless_video.edl.v1",
        "width": normalized["canvas"]["width"],
        "height": normalized["canvas"]["height"],
        "fps": normalized["canvas"]["fps"],
        "clips": clips,
        "captions": normalized["captions"],
    }
    for field in ("voice_asset_id", "music_asset_id"):
        if normalized["audio"].get(field):
            result[field] = normalized["audio"][field]
    return result


def affected_scene_ids(
    previous_ir: dict[str, Any],
    next_ir: dict[str, Any],
) -> list[str]:
    """Return the minimal scene set whose canonical contracts changed."""
    previous = normalize_video_ir(previous_ir)
    next_value = normalize_video_ir(next_ir)
    before = {scene["id"]: scene["scene_sha256"] for scene in previous["scenes"]}
    after = {scene["id"]: scene["scene_sha256"] for scene in next_value["scenes"]}
    ordered_ids = list(before) + [
        scene_id for scene_id in after if scene_id not in before
    ]
    return [
        scene_id
        for scene_id in ordered_ids
        if before.get(scene_id) != after.get(scene_id)
    ]
