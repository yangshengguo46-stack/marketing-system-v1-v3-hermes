from __future__ import annotations

import json

import hermes_state

from agent.marketing.data_paths import MarketingDataPaths
from agent.marketing.domains.short_video_signals import (
    SIGNAL_SCHEMA,
    ShortVideoSignalRepository,
    decode_browser_signal_result,
)
from agent.marketing.intelligence.production_preflight import (
    build_content_production_preflight,
)
from agent.marketing.evidence_capture import enrich_tool_result_with_evidence
from hermes_state import SessionDB


def _repository(tmp_path):
    state_path = tmp_path / "state.db"
    owner = SessionDB(db_path=state_path)
    owner.close()
    return ShortVideoSignalRepository(
        MarketingDataPaths(
            user_data=tmp_path,
            config_dir=tmp_path / "config",
            agent_db=state_path,
        )
    )


def _payload(*, view_count=1_200_000, source_item_id="video-1"):
    return {
        "schema": SIGNAL_SCHEMA,
        "platform": "douyin",
        "observed_at": "2026-07-11T12:00:00+00:00",
        "items": [
            {
                "source_item_id": source_item_id,
                "source_url": f"https://www.douyin.com/video/{source_item_id}?from=feed",
                "caption": "创业者如何做内容",
                "creator": "creator",
                "published_at": "1752230000",
                "rank": 2,
                "view_count": view_count,
                "like_count": 80_000,
                "comment_count": 3_000,
                "share_count": 5_000,
                "use_count": 160_000,
                "sound": {
                    "platform_sound_id": "music-88",
                    "title": "向前走",
                    "artist": "平台音乐人",
                    "duration_ms": 18_000,
                    "canonical_url": "https://www.douyin.com/music/music-88",
                    "rights_status": "platform_library",
                    "tags": ["励志", "创业"],
                },
            }
        ],
    }


def test_browser_signal_capture_creates_evidence_sound_and_observation(tmp_path):
    repository = _repository(tmp_path)

    result = repository.capture_browser_result(
        user_id="default",
        account_id="acct-1",
        payload=_payload(),
        session_id="session-1",
        tool_call_id="call-1",
    )

    assert result["total"] == 1
    assert result["captured"][0]["evidence_id"].startswith("evidence_")
    assert result["captured"][0]["sound_id"].startswith("sound_")
    ranked = repository.rank_sounds(
        user_id="default",
        account_id="acct-1",
        platform="douyin",
        objective="创业 励志",
        window_hours=720,
    )
    assert ranked["sound_count"] == 1
    candidate = ranked["candidates"][0]
    assert candidate["platform_sound_id"] == "music-88"
    assert candidate["rights_status"] == "platform_library"
    assert candidate["signals"]["objective_fit"] > 0
    assert candidate["evidence_ids"] == [result["captured"][0]["evidence_id"]]


def test_signal_capture_is_idempotent_and_decoder_finds_mcp_payload(tmp_path):
    repository = _repository(tmp_path)
    payload = _payload()
    wrapped = "### Marketing short-video signals\n```json\n" + __import__("json").dumps(payload) + "\n```"

    assert decode_browser_signal_result(wrapped) == payload
    first = repository.capture_browser_result(
        user_id="default", account_id="acct-1", payload=payload, session_id="s"
    )
    second = repository.capture_browser_result(
        user_id="default", account_id="acct-1", payload=payload, session_id="s"
    )
    assert first["captured"][0]["observation_id"] == second["captured"][0]["observation_id"]
    assert repository.rank_sounds(
        user_id="default", account_id="acct-1", platform="douyin", window_hours=720
    )["observation_count"] == 1


def test_video_preflight_treats_bgm_as_first_class_signal():
    base = {
        "objective": "创业者内容",
        "kind": "faceless_video",
        "platforms": ["douyin"],
        "audience_context": {"target_audience": "创业者"},
        "evidence": [{"url": "https://example.com/source"}],
    }
    without_sound = build_content_production_preflight(base)
    with_sound = build_content_production_preflight(
        {
            **base,
            "sound_context": {
                "candidates": [{"sound_id": "sound-1", "selection_score": 0.92}]
            },
        }
    )

    assert "bgm_trend_evidence_missing" in without_sound["decision"]["warnings"]
    assert without_sound["scores"]["sound_fit"] == 0
    assert with_sound["scores"]["sound_fit"] == 0.92
    assert with_sound["scores"]["overall"] > without_sound["scores"]["overall"]
    assert with_sound["formula_version"] == "content-production-preflight-v0.5"


def test_playwright_post_tool_seam_persists_verified_sound_signal(tmp_path, monkeypatch):
    state_path = tmp_path / "state.db"
    monkeypatch.setenv("MARKETING_OS_AGENT_DB", str(state_path))
    monkeypatch.setenv("MARKETING_OS_USER_DATA", str(tmp_path))
    monkeypatch.setenv("MARKETING_OS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setattr(hermes_state, "DEFAULT_DB_PATH", state_path)
    owner = SessionDB(db_path=state_path)
    owner.create_session(
        "session-1",
        "tui",
        marketing_user_id="default",
        marketing_account_id="acct-1",
    )
    owner.close()
    payload = _payload()

    result = enrich_tool_result_with_evidence(
        tool_name="mcp_marketing_browser_browser_extract_short_video_signals",
        args={},
        result="### Marketing short-video signals\n" + json.dumps(payload),
        task_id="session-1",
        session_id="session-1",
        tool_call_id="browser-call-1",
    )

    assert "Marketing OS verified capture" in result
    ranked = ShortVideoSignalRepository().rank_sounds(
        user_id="default",
        account_id="acct-1",
        platform="douyin",
        window_hours=720,
    )
    assert ranked["sound_count"] == 1
    assert ranked["candidates"][0]["platform_sound_id"] == "music-88"
