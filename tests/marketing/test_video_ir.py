import copy

import pytest

from agent.marketing.domains.video_ir import (
    FFMPEG_RENDERER,
    HYPERFRAMES_RENDERER,
    REMOTION_RENDERER,
    VIDEO_IR_VERSION,
    affected_scene_ids,
    build_render_plan,
    compile_ffmpeg_edl,
    normalize_video_ir,
    video_ir_from_edl,
)


def _ir(*, motion=None, text=None, preference="auto"):
    return {
        "version": VIDEO_IR_VERSION,
        "canvas": {"width": 360, "height": 640, "fps": 24},
        "scenes": [
            {
                "id": "scene_001",
                "duration": 1.2,
                "purpose": "hook",
                "visuals": [
                    {
                        "media_asset_id": "media_001",
                        "source_in": 0,
                        "fit": "cover",
                    }
                ],
                "text": text or [],
                "motion_intent": motion or ["straight_cut"],
                "constraints": {
                    "safe_area": "short_vertical",
                    "rights_required": True,
                },
                "renderer_policy": {
                    "preference": preference,
                    "fallback": "ffmpeg",
                },
                "review_rules": ["hook remains readable in the first second"],
            }
        ],
        "captions": [{"start": 0, "end": 1.1, "text": "先看结果"}],
        "audio": {},
        "review_rules": ["no blocking technical defects"],
    }


def test_video_ir_is_canonical_and_hash_assertions_fail_closed():
    normalized = normalize_video_ir(_ir())

    assert len(normalized["ir_sha256"]) == 64
    assert len(normalized["scenes"][0]["scene_sha256"]) == 64
    assert normalize_video_ir(normalized) == normalized

    stale = copy.deepcopy(normalized)
    stale["scenes"][0]["duration"] = 1.3
    with pytest.raises(ValueError, match="stale scene_sha256"):
        normalize_video_ir(stale)


def test_simple_scene_routes_to_ffmpeg_and_compiles_legacy_edl():
    normalized = normalize_video_ir(_ir())
    plan = build_render_plan(normalized)
    edl = compile_ffmpeg_edl(normalized, plan)

    assert plan["executable"] is True
    assert plan["scenes"][0]["renderer"] == FFMPEG_RENDERER
    assert edl["version"] == "marketing.faceless_video.edl.v1"
    assert edl["clips"] == [
        {
            "media_asset_id": "media_001",
            "source_in": 0.0,
            "duration": 1.2,
            "fit": "cover",
        }
    ]


def test_advanced_capability_is_blocked_until_renderer_is_enabled():
    normalized = normalize_video_ir(
        _ir(
            motion=["kinetic_typography"],
            text=[{"text": "因果不是相关", "role": "headline"}],
        )
    )
    blocked = build_render_plan(normalized)

    assert blocked["executable"] is False
    assert blocked["scenes"][0]["preferred_renderer"] == REMOTION_RENDERER
    assert blocked["scenes"][0]["status"] == "unavailable"

    enabled = build_render_plan(
        normalized,
        enabled_renderers=(FFMPEG_RENDERER, REMOTION_RENDERER),
    )
    assert enabled["executable"] is True
    assert enabled["scenes"][0]["renderer"] == REMOTION_RENDERER
    with pytest.raises(ValueError, match="non-FFmpeg scene"):
        compile_ffmpeg_edl(normalized, enabled)


def test_hyperframes_hint_and_equivalent_fallback_are_explainable():
    designed = normalize_video_ir(_ir(motion=["html_css_motion"]))
    designed_plan = build_render_plan(
        designed,
        enabled_renderers=(FFMPEG_RENDERER, HYPERFRAMES_RENDERER),
    )
    assert designed_plan["scenes"][0]["renderer"] == HYPERFRAMES_RENDERER

    simple = normalize_video_ir(_ir(preference="hyperframes"))
    fallback_plan = build_render_plan(simple)
    scene_plan = fallback_plan["scenes"][0]
    assert scene_plan["renderer"] == FFMPEG_RENDERER
    assert scene_plan["fallback_used"] is True
    assert "equivalent" in scene_plan["reason"]


def test_legacy_edl_round_trip_preserves_current_execution_contract():
    edl = {
        "version": "marketing.faceless_video.edl.v1",
        "width": 360,
        "height": 640,
        "fps": 24,
        "clips": [
            {
                "media_asset_id": "media_001",
                "source_in": 0.25,
                "duration": 1.5,
                "fit": "contain",
            }
        ],
        "captions": [],
        "voice_asset_id": "voice_001",
    }
    video_ir = video_ir_from_edl(edl)
    compiled = compile_ffmpeg_edl(video_ir, build_render_plan(video_ir))

    assert compiled == edl


def test_scene_hashes_define_minimal_repair_scope():
    previous = normalize_video_ir({
        **_ir(),
        "scenes": [
            _ir()["scenes"][0],
            {
                **_ir()["scenes"][0],
                "id": "scene_002",
                "purpose": "explanation",
            },
        ],
        "captions": [],
    })
    next_value = copy.deepcopy(previous)
    next_value["scenes"][1].pop("scene_sha256")
    next_value.pop("ir_sha256")
    next_value["scenes"][1]["purpose"] = "proof"

    assert affected_scene_ids(previous, next_value) == ["scene_002"]
