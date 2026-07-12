"""Shared editing engine contract for all video lanes.

This module is intentionally small and deterministic.  It does not fetch
materials, call model providers, or render files.  It turns script/shot
segments into the single editing protocol used by both:

- ``faceless_video``: licensed/user/code/generated material fills slots.
- ``premium_human_video``: Seedream/Seedance/generated shots fill slots.

The key product decision is that *editing is one engine*.  Material sources may
be different, but the downstream timeline, review, replacement and rendering
contract stays EDL-first.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Literal

from engine.video_core.edl import EDL, ClipEntry, SubtitleEntry, TimelineSlot

EditingLane = Literal["faceless_video", "premium_human_video"]


@dataclass(frozen=True)
class EditingSegment:
    """A human-readable script/shot segment before it becomes an EDL slot."""

    id: str
    order: int
    duration_sec: float
    narration: str = ""
    visual_intent: str = ""
    shot_id: str = ""
    scene_id: str = ""
    energy: Literal["low", "medium", "high"] = "medium"
    mood: str = ""
    beat_locked: bool = False


def shared_editing_contract(lane: EditingLane) -> dict[str, Any]:
    """Return the editing contract shared by faceless and premium video lanes."""

    if lane not in {"faceless_video", "premium_human_video"}:
        raise ValueError(f"unsupported editing lane: {lane}")
    return {
        "engine": "engine.video_core.editing_engine",
        "lane": lane,
        "single_source_of_truth": "EDL",
        "principles": [
            "剪辑师先产时间线骨架，素材/镜头只是填坑。",
            "素材来源不同，但进入剪辑前必须变成可追溯资产引用。",
            "节奏、字幕、配音、BGM 和转场都写进 EDL，渲染器只做确定性转换。",
            "用户反馈优先定位到 EDL；能改时间线解决的，不重新生成镜头。",
        ],
        "material_inputs": {
            "faceless_video": [
                "licensed_stock_video",
                "licensed_or_user_image_to_clip",
                "code_generated_visual",
                "model_generated_gap_shot",
            ],
            "premium_human_video": [
                "storyboard_animatic",
                "seedance_generated_shot",
                "licensed_b_roll",
                "code_generated_visual",
            ],
        }[lane],
        "render_targets": ["ffmpeg", "remotion", "hyperframes"],
        "review_outputs": ["human_readable_edl", "animatic", "review_cut", "final_cut"],
    }


def build_edl_from_segments(
    segments: list[EditingSegment | dict[str, Any]],
    *,
    lane: EditingLane,
    resolution: str = "1080x1920",
    fps: int = 30,
    subtitle_style: str = "default",
    notes: str = "",
) -> EDL:
    """Build an EDL skeleton plus subtitle timing from script segments."""

    normalised = [_normalise_segment(item, index) for index, item in enumerate(segments, start=1)]
    slots: list[TimelineSlot] = []
    subtitles: list[SubtitleEntry] = []
    cursor = 0.0
    for segment in sorted(normalised, key=lambda item: item.order):
        slot_id = segment.id or f"slot_{segment.order:02d}"
        shot_id = segment.shot_id or re.sub(r"^slot", "shot", slot_id)
        slots.append(
            TimelineSlot(
                id=slot_id,
                order=segment.order,
                duration_sec=float(segment.duration_sec),
                camera_direction=segment.visual_intent or "match material; keep motion readable",
                energy=segment.energy,
                mood=segment.mood or ("信息密度高、节奏克制" if lane == "faceless_video" else "风格一致、情绪连续"),
                beat_locked=bool(segment.beat_locked),
                narration=segment.narration,
                scene_id=segment.scene_id or f"scene_{segment.order:02d}",
                shot_id=shot_id,
            )
        )
        if segment.narration:
            subtitles.append(
                SubtitleEntry(
                    text=segment.narration,
                    start_sec=round(cursor, 2),
                    end_sec=round(cursor + float(segment.duration_sec), 2),
                    style=subtitle_style,
                )
            )
        cursor += float(segment.duration_sec)

    edl = EDL(
        version=1,
        fps=fps,
        resolution=resolution,
        slots=slots,
        clips=[],
        subtitles=subtitles,
        notes=notes or f"Shared Editing Engine skeleton for {lane}; clips remain empty until materials fill slots.",
    )
    problems = edl.validate_skeleton()
    if problems:
        raise ValueError("; ".join(problems))
    return edl


def fill_edl_clips(
    edl: EDL,
    materials: list[dict[str, Any]],
    *,
    replace_existing: bool = True,
) -> EDL:
    """Return a copy of ``edl`` with ClipEntry items filled from material refs.

    This is deliberately source-agnostic.  The caller must validate provenance
    before passing materials here.  A material only needs to identify the slot
    and shot plus optional in/out trims.
    """

    slot_by_id = {slot.id: slot for slot in edl.slots}
    shot_to_slot = {slot.shot_id: slot for slot in edl.slots if slot.shot_id}
    clips = [clip.model_dump() for clip in edl.clips]

    for index, material in enumerate(materials, start=1):
        slot_id = _text(material.get("slot_id"))
        shot_id = _text(material.get("shot_id"))
        slot = slot_by_id.get(slot_id) or shot_to_slot.get(shot_id)
        if slot is None:
            raise ValueError(f"material {index} has no matching timeline slot")
        resolved_shot_id = shot_id or slot.shot_id or slot.id
        if replace_existing:
            clips = [clip for clip in clips if clip["slot_id"] != slot.id]
        clips.append(
            ClipEntry(
                slot_id=slot.id,
                shot_id=resolved_shot_id,
                source_in_sec=_float(material.get("source_in_sec"), 0.0),
                source_out_sec=_float(material.get("source_out_sec"), float(slot.duration_sec)),
            ).model_dump()
        )

    order = {slot.id: slot.order for slot in edl.slots}
    sorted_clips = sorted(clips, key=lambda clip: order.get(clip["slot_id"], 10_000))
    return edl.model_copy(update={"clips": [ClipEntry.model_validate(clip) for clip in sorted_clips]})


def edl_handoff_summary(edl: EDL) -> dict[str, Any]:
    """Produce a compact handoff summary for content assets and approval UI."""

    unfilled = [slot.id for slot in edl.unfilled_slots()]
    return {
        "duration_sec": edl.total_duration_sec(),
        "slot_count": len(edl.slots),
        "clip_count": len(edl.clips),
        "subtitle_count": len(edl.subtitles),
        "unfilled_slots": unfilled,
        "ready_for_render": not unfilled and bool(edl.clips),
        "problems": edl.validate_skeleton(),
    }


def segment_from_shot(shot: dict[str, Any]) -> EditingSegment:
    """Convert a content-factory shot dict into an EditingSegment."""

    order = int(shot.get("order") or 0)
    return EditingSegment(
        id=f"slot_{order:02d}" if order else _text(shot.get("slot_id")) or _text(shot.get("id")),
        order=order,
        duration_sec=_float(shot.get("duration_sec"), 1.0),
        narration=_text(shot.get("voiceover") or shot.get("narration")),
        visual_intent=_text(shot.get("visual_intent") or shot.get("camera_direction")),
        shot_id=_text(shot.get("id") or shot.get("shot_id")),
        scene_id=_text(shot.get("scene_id")) or (f"scene_{order:02d}" if order else ""),
        energy="high" if _text(shot.get("beat")) in {"hook", "cta"} else _normalise_energy(shot.get("energy")),
        mood=_text(shot.get("mood")),
        beat_locked=bool(shot.get("beat_locked") or _text(shot.get("beat")) in {"hook", "cta"}),
    )


def _normalise_segment(item: EditingSegment | dict[str, Any], index: int) -> EditingSegment:
    if isinstance(item, EditingSegment):
        return item
    if not isinstance(item, dict):
        raise TypeError(f"segment {index} must be EditingSegment or dict")
    if "visual_intent" in item or "voiceover" in item or "beat" in item:
        segment = segment_from_shot(item)
    else:
        segment = EditingSegment(
            id=_text(item.get("id") or item.get("slot_id")) or f"slot_{index:02d}",
            order=int(item.get("order") or index),
            duration_sec=_float(item.get("duration_sec"), 1.0),
            narration=_text(item.get("narration") or item.get("voiceover")),
            visual_intent=_text(item.get("visual_intent") or item.get("camera_direction")),
            shot_id=_text(item.get("shot_id")),
            scene_id=_text(item.get("scene_id")),
            energy=_normalise_energy(item.get("energy")),
            mood=_text(item.get("mood")),
            beat_locked=bool(item.get("beat_locked")),
        )
    if segment.order <= 0:
        return EditingSegment(**(asdict(segment) | {"order": index}))
    if segment.duration_sec <= 0:
        raise ValueError(f"segment {index} duration must be positive")
    return segment


def _normalise_energy(value: Any) -> Literal["low", "medium", "high"]:
    text = _text(value).lower()
    if text in {"low", "medium", "high"}:
        return text  # type: ignore[return-value]
    return "medium"


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
