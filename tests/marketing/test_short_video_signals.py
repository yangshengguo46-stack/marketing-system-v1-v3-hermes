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
    build_article_draft_preflight,
    build_content_production_preflight,
    build_video_cut_preflight,
    build_video_treatment_preflight,
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
    assert with_sound["formula_version"] == "content-production-preflight-v0.9"


def test_public_priors_keep_cold_start_productive_without_fake_personalization():
    treatment = {
        "platform": "douyin",
        "format": "short_video",
        "title": "AI 是泡沫吗",
        "thesis": "估值泡沫不等于需求不存在",
        "audience_promise": "用三组证据拆开这个问题",
        "hook": "AI 泡沫已经破了，但真正的问题不是估值。",
        "hook_hypothesis": {
            "first_three_seconds": "AI 泡沫已经破了，但你可能看错了泡沫在哪。",
            "tension": "市场下跌与真实需求同时存在",
            "payoff": "给出估值、需求、生产率三层判断",
        },
        "aspect_ratio": "9:16",
        "target_duration": 9,
        "pacing": "前三秒冲突，随后每三秒兑现一个证据",
        "caption_style": "逐句高亮关键词",
        "cta": "你认为泡沫在哪一层？",
        "voiceover_script": "AI 泡沫已经破了。估值、需求和生产率其实是三个问题。",
        "beat_sheet": [
            {"purpose": "hook"},
            {"purpose": "evidence"},
            {"purpose": "conclusion"},
        ],
        "claim_evidence_map": [
            {"claim": "基础设施投入正在变化", "evidence_refs": ["evidence-1"]}
        ],
        "sound_strategy": {
            "voice_style": "冷静、快速",
            "music_role": "低频张力，不盖旁白",
            "sfx_cues": ["开场冲击"],
        },
        "shot_list": [
            {
                "id": "s1",
                "duration": 3,
                "purpose": "hook",
                "visual_query": "AI stock market crash chart",
                "on_screen_text": "泡沫破了吗？",
            },
            {
                "id": "s2",
                "duration": 3,
                "purpose": "evidence",
                "visual_query": "data center servers",
                "on_screen_text": "需求仍在增长",
            },
            {
                "id": "s3",
                "duration": 3,
                "purpose": "conclusion",
                "visual_query": "office worker artificial intelligence",
                "on_screen_text": "分三层判断",
            },
        ],
    }
    result = build_video_treatment_preflight(
        {
            "platform": "douyin",
            "treatment": treatment,
            "evidence_refs": ["evidence-1"],
            "knowledge_context": {
                "platform": [{"id": "public-platform-1"}],
                "market": [{"id": "public-market-1"}],
                "content": [{"id": "public-content-1"}],
                "account": [],
            },
            "account_context": {},
        }
    )

    assert result["prior_mode"] == "public_prior_cold_start"
    assert result["personal_prior"]["available"] is False
    assert result["public_prior"]["support"] > 0
    assert result["preflight_decision"]["go"] is True
    assert "personal_model_missing_public_prior_cold_start" in result[
        "preflight_decision"
    ]["warnings"]
    assert result["prediction_contract"]["exact_views_allowed"] is False


def test_general_preflight_missing_private_audience_is_warning_not_brain_death():
    result = build_content_production_preflight(
        {
            "objective": "AI 泡沫公域冷启动内容",
            "kind": "faceless_video",
            "platforms": ["douyin"],
            "evidence": [{"url": "https://example.com/public-report"}],
            "knowledge_context": {"content": [{"id": "public-prior-1"}]},
        }
    )

    assert "audience_context_missing" not in result["decision"]["blockers"]
    assert "personal_audience_context_missing_using_public_prior" in result[
        "decision"
    ]["warnings"]
    assert result["input"]["prior_mode"] == "public_prior_cold_start"
    assert result["preflight_decision"]["go"] is True
    assert result["decision"]["publish_eligible"] is False
    assert "public_prior_exploratory_draft_only" in result["decision"]["warnings"]


def test_video_treatment_preflight_blocks_even_one_unverified_claim():
    treatment = {
        "platform": "douyin",
        "hook": "模型越强越要核验",
        "hook_hypothesis": {"first_three_seconds": "模型越强，你越危险"},
        "aspect_ratio": "9:16",
        "target_duration": 6,
        "pacing": "快",
        "caption_style": "大字",
        "cta": "评论",
        "voiceover_script": "先核验证据。",
        "beat_sheet": [{"purpose": "hook"}],
        "claim_evidence_map": [
            {"claim": "模型已发布", "evidence_refs": ["evidence-1"]},
            {"claim": "60% 的人被误导", "evidence_refs": []},
        ],
        "shot_list": [
            {
                "duration": 3,
                "purpose": "hook",
                "visual_query": "AI release screen",
                "on_screen_text": "模型发布",
            },
            {
                "duration": 3,
                "purpose": "close",
                "visual_query": "person fact checking",
                "on_screen_text": "先核验",
            },
        ],
    }

    result = build_video_treatment_preflight({
        "platform": "douyin",
        "treatment": treatment,
        "evidence_refs": ["evidence-1"],
        "knowledge_context": {"platform": [{}], "market": [{}], "content": [{}]},
        "account_context": {},
    })

    assert result["preflight_decision"]["go"] is False
    assert "treatment_contains_unverified_claims" in result[
        "preflight_decision"
    ]["blockers"]
    assert result["treatment_features"]["unmapped_claim_count"] == 1

def test_cut_preflight_requires_observed_hook_material_audio_and_treatment_parity():
    review = {
        "playable": True,
        "hook_first_three_seconds_visible": True,
        "treatment_parity": True,
        "caption_readability": True,
        "material_relevance": True,
        "evidence_alignment": True,
        "audio_present": True,
        "audio_sync": True,
        "ending_cta_present": True,
        "scores": {
            "audience_fit": 8,
            "platform_fit": 8,
            "account_fit": 7,
            "emotional_pull": 7,
            "pacing": 8,
            "information_density": 8,
            "evidence_alignment": 8,
        },
        "issues": [],
    }
    ready = build_video_cut_preflight(
        {
            "platform": "douyin",
            "treatment": {"platform": "douyin"},
            "technical_qa": {"disposition": "ready"},
            "audio_expected": True,
            "visual_review": review,
        }
    )

    assert ready["scope"] == "video_cut_preflight"
    assert ready["preflight_decision"]["go"] is True
    assert ready["preflight_decision"]["stage"] == "cut_review"
    assert ready["prediction_contract"]["exact_views_allowed"] is False

    failed = build_video_cut_preflight(
        {
            "platform": "douyin",
            "treatment": {"platform": "douyin"},
            "technical_qa": {"disposition": "ready"},
            "audio_expected": True,
            "visual_review": {
                **review,
                "hook_first_three_seconds_visible": False,
                "material_relevance": False,
                "audio_sync": False,
            },
        }
    )
    assert failed["preflight_decision"]["go"] is False
    assert failed["preflight_decision"]["action"] == "revise_cut"
    assert {
        "cut_hook_contract_failed",
        "cut_material_relevance_failed",
        "cut_audio_contract_failed",
    } <= set(failed["preflight_decision"]["blockers"])


def test_article_draft_preflight_is_platform_native_and_evidence_gated():
    review = {
        "platform_native": True,
        "factual_claims_traceable": True,
        "hook_effective": True,
        "structure_complete": True,
        "cta_present": True,
        "deliverable_complete": True,
        "scores": {
            "audience_fit": 8,
            "platform_fit": 8,
            "account_fit": 6,
            "knowledge_fit": 8,
            "strategy_fit": 8,
            "evidence_strength": 8,
            "hook": 8,
            "emotion": 7,
            "structure": 8,
            "viewpoint": 8,
        },
        "issues": [],
    }
    ready = build_article_draft_preflight(
        {
            "platform": "zhihu",
            "article": {
                "platform": "zhihu",
                "claim_evidence_map": [
                    {"claim": "AI 投资增加", "evidence_refs": ["evidence-1"]}
                ],
            },
            "draft_review": review,
        }
    )
    assert ready["preflight_decision"]["go"] is True
    assert ready["draft_features"]["mapped_evidence_count"] == 1

    failed = build_article_draft_preflight(
        {
            "platform": "zhihu",
            "article": {"platform": "zhihu", "claim_evidence_map": []},
            "draft_review": {
                **review,
                "platform_native": False,
                "factual_claims_traceable": False,
            },
        }
    )
    assert failed["preflight_decision"]["go"] is False
    assert failed["preflight_decision"]["action"] == "revise_article"


def test_preflight_human_observer_projection_is_read_only_and_score_neutral():
    base = {
        "objective": "解释群体决策",
        "kind": "article_soft",
        "platforms": ["wechat_official"],
        "audience_context": {"target_audience": "创业者"},
        "evidence": [{"url": "https://example.com/source"}],
    }
    without_projection = build_content_production_preflight(base)
    with_projection = build_content_production_preflight(
        {
            **base,
            "human_observer_projection": {
                "contract": "human-observer-read-projection-v1",
                "namespace": "human_research",
                "interpretations": [{"id": "humanint-1"}],
                "model_revisions": [{"id": "modelrev-1"}],
            },
        }
    )

    assert without_projection["human_observer_context"] is None
    assert with_projection["human_observer_context"]["interpretation_count"] == 1
    assert with_projection["human_observer_context"]["authority"] == (
        "read_only_no_score_or_writeback"
    )
    assert with_projection["scores"] == without_projection["scores"]


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


def test_signal_decoder_handles_nested_mcp_result_envelope():
    payload = _payload()
    wrapped = json.dumps({"result": "### Result\n" + json.dumps(payload)})

    assert decode_browser_signal_result(wrapped) == payload
