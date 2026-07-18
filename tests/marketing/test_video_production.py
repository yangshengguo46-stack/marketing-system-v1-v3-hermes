import io
import hashlib
import json
import shutil
import sqlite3
import os
import subprocess

import hermes_state
import pytest
from PIL import Image
from hermes_state import SessionDB
from model_tools import handle_function_call
from tui_gateway import server

from agent.marketing.data_paths import MarketingDataPaths
from agent.marketing.domains import (
    ContentAssetRepository,
    EvidenceRepository,
    MediaAssetRepository,
    PublishingRepository,
    ProductionAudioRepository,
    VideoProductionRepository,
    VideoQualityAnalyzer,
    VideoRendererRuntime,
)
from agent.marketing.intelligence.store import OperatingLoopRepository
from agent.marketing.domains.video_renderers import PINNED_PACKAGES


def _paths(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    return MarketingDataPaths(
        user_data=tmp_path,
        config_dir=config_dir,
        agent_db=tmp_path / "state.db",
    )


def _bind_session(paths, tmp_path, monkeypatch):
    monkeypatch.setenv("MARKETING_OS_USER_DATA", str(paths.user_data))
    monkeypatch.setenv("MARKETING_OS_CONFIG_DIR", str(paths.config_dir))
    monkeypatch.setenv("MARKETING_OS_AGENT_DB", str(paths.agent_db))
    state_path = tmp_path / "session-state.db"
    monkeypatch.setattr(hermes_state, "DEFAULT_DB_PATH", state_path)
    db = SessionDB(db_path=state_path)
    db.create_session(
        "video-session",
        "tui",
        marketing_user_id="default",
        marketing_account_id="acct-1",
    )
    db.close()


def _png(color):
    image = Image.new("RGB", (32, 48), color=color)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _pinned_renderer_runtime(tmp_path):
    root = tmp_path / "video-renderers"
    modules = root / "node_modules"
    packages = {"": {"dependencies": PINNED_PACKAGES}}
    installed_packages = {}
    for name, version in PINNED_PACKAGES.items():
        key = f"node_modules/{name}"
        package_root = root / key
        package_root.mkdir(parents=True, exist_ok=True)
        (package_root / "package.json").write_text(
            json.dumps({"name": name, "version": version}), encoding="utf-8"
        )
        packages[key] = {"version": version}
        installed_packages[key] = {"version": version}
    (root / "package.json").write_text(
        json.dumps({"dependencies": PINNED_PACKAGES}), encoding="utf-8"
    )
    (root / "package-lock.json").write_text(
        json.dumps({"lockfileVersion": 3, "packages": packages}), encoding="utf-8"
    )
    (root / "version-policy.json").write_text(
        json.dumps(
            {
                "dependencies": PINNED_PACKAGES,
                "remotion_upgrade_gate": {
                    "locked_version": "4.0.488",
                    "blocked_major": 5,
                    "requires": [
                        "explicit_user_approval",
                        "license_review",
                        "renderer_regression",
                    ],
                },
            }
        ),
        encoding="utf-8",
    )
    (modules / ".package-lock.json").write_text(
        json.dumps({"lockfileVersion": 3, "packages": installed_packages}),
        encoding="utf-8",
    )
    for entrypoint in ("render-remotion.mjs", "render-hyperframes.mjs"):
        (root / entrypoint).write_text("", encoding="utf-8")
    node = tmp_path / "node"
    node.write_text("#!/bin/sh\nprintf '24.0.0\\n'\n", encoding="utf-8")
    node.chmod(0o755)
    browser = tmp_path / "browser"
    browser.write_text("", encoding="utf-8")
    return VideoRendererRuntime(
        root=root, node_executable=node, browser_executable=browser
    )


def test_video_quality_analyzer_returns_hold_with_timed_evidence(tmp_path):
    media_path = tmp_path / "final.mp4"
    media_path.write_bytes(b"video")

    def runner(command, _timeout):
        if command[0] == "ffprobe":
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps(
                    {
                        "format": {"duration": "10.0"},
                        "streams": [
                            {
                                "codec_type": "video",
                                "codec_name": "h264",
                                "width": 1080,
                                "height": 1920,
                                "avg_frame_rate": "30/1",
                                "pix_fmt": "yuv420p",
                            },
                            {
                                "codec_type": "audio",
                                "codec_name": "aac",
                                "sample_rate": "48000",
                                "channels": 2,
                            },
                        ],
                    }
                ),
                stderr="",
            )
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="",
            stderr=(
                "black_start:1 black_end:4 black_duration:3\n"
                "freeze_start: 5\n"
                "freeze_end: 9.5 | freeze_duration: 4.5\n"
                '{\n  "input_i" : "-31.0",\n  "input_tp" : "-2.0"\n}\n'
            ),
        )

    report = VideoQualityAnalyzer(
        ffmpeg_path="ffmpeg",
        ffprobe_path="ffprobe",
        runner=runner,
    ).analyze(
        media_path,
        expected_duration=10,
        expected_width=1080,
        expected_height=1920,
        audio_expected=True,
    )

    assert report["version"] == "marketing.media_quality.v1"
    assert report["disposition"] == "hold"
    checks = {check["id"]: check for check in report["checks"]}
    assert checks["technical_delivery"]["status"] == "pass"
    assert checks["black_frames"]["status"] == "fail"
    assert checks["black_frames"]["evidence"]["events"] == [
        {"start": 1.0, "end": 4.0, "duration": 3.0}
    ]
    assert checks["frozen_frames"]["status"] == "fail"
    assert checks["audio_loudness"]["status"] == "fail"
    assert checks["audio_loudness"]["evidence"]["integrated_lufs"] == -31


def test_video_quality_analyzer_rejects_missing_expected_audio(tmp_path):
    media_path = tmp_path / "silent.mp4"
    media_path.write_bytes(b"video")

    def runner(command, _timeout):
        if command[0] == "ffprobe":
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps(
                    {
                        "format": {"duration": "3.0"},
                        "streams": [
                            {
                                "codec_type": "video",
                                "codec_name": "h264",
                                "width": 1920,
                                "height": 1080,
                            }
                        ],
                    }
                ),
                stderr="",
            )
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    report = VideoQualityAnalyzer(
        ffmpeg_path="ffmpeg",
        ffprobe_path="ffprobe",
        runner=runner,
    ).analyze(
        media_path,
        expected_duration=3,
        expected_width=1920,
        expected_height=1080,
        audio_expected=True,
    )

    assert report["disposition"] == "reject"
    audio = next(check for check in report["checks"] if check["id"] == "audio_loudness")
    assert audio["severity"] == "critical"


def test_video_renderer_runtime_rejects_installed_package_drift(tmp_path):
    runtime = _pinned_renderer_runtime(tmp_path)
    assert runtime.health()["ready"] is True

    package_path = runtime.root / "node_modules" / "remotion" / "package.json"
    package = json.loads(package_path.read_text(encoding="utf-8"))
    package["version"] = "5.0.0"
    package_path.write_text(json.dumps(package), encoding="utf-8")

    health = runtime.health(refresh=True)
    assert health["ready"] is False
    assert "renderer installed packages does not match product pins" in health[
        "failures"
    ]


def test_video_gateway_lists_bounded_summaries_and_loads_review_projection(
    tmp_path, monkeypatch
):
    paths = _paths(tmp_path)
    monkeypatch.setenv("MARKETING_OS_USER_DATA", str(paths.user_data))
    monkeypatch.setenv("MARKETING_OS_CONFIG_DIR", str(paths.config_dir))
    monkeypatch.setenv("MARKETING_OS_AGENT_DB", str(paths.agent_db))
    source = _source_asset(paths)
    media = MediaAssetRepository(paths)
    visual = _visual_asset(
        media,
        account_id="acct-1",
        name="horizontal-scene",
        color="#31556d",
    )
    video_ir = _video_ir(visual["id"])
    video_ir["canvas"] = {"width": 1920, "height": 1080, "fps": 30}
    production = VideoProductionRepository(
        paths, enabled_renderers=["ffmpeg_timeline_v1"]
    ).prepare(
        user_id="default",
        account_id="acct-1",
        source_asset_id=source["id"],
        video_ir=video_ir,
    )

    listed = server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": "video-list",
            "method": "marketing.video.productions.list",
            "params": {"account_id": "acct-1"},
        }
    )["result"]
    assert listed["total"] == 1
    assert listed["productions"][0]["id"] == production["id"]
    assert listed["productions"][0]["canvas"] == {
        "width": 1920,
        "height": 1080,
        "fps": 30,
    }
    assert "video_ir" not in listed["productions"][0]

    opened = server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": "video-get",
            "method": "marketing.video.production.get",
            "params": {
                "account_id": "acct-1",
                "production_id": production["id"],
            },
        }
    )["result"]
    assert opened["production"]["video_ir"]["canvas"]["width"] == 1920
    assert opened["media_assets"][0]["playback_path"].endswith(
        "horizontal-scene.png"
    )

    cross_account = server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": "video-cross-account",
            "method": "marketing.video.production.get",
            "params": {
                "account_id": "acct-other",
                "production_id": production["id"],
            },
        }
    )
    assert cross_account["error"]["code"] == 4044


def _source_asset(paths):
    evidence_id = EvidenceRepository(paths).capture_web_extract_result(
        user_id="default",
        account_id="acct-1",
        result={
            "results": [
                {
                    "url": "https://example.com/source",
                    "title": "source",
                    "content": "A bounded source for a faceless-video production test.",
                }
            ]
        },
        session_id="test-session",
    )[0]["id"]
    repository = ContentAssetRepository(paths)
    plan = repository.save_production_plan(
        user_id="default",
        account_id="acct-1",
        plan={
            "status": "planned",
            "kind": "faceless_video",
            "objective": "做一条有来源的不露脸素材视频",
            "target_platforms": ["douyin"],
            "constraints": {},
            "audience_model": {"target_audience": "需要真实工作方法的职场人"},
        },
    )
    return repository.create_draft(
        user_id="default",
        account_id="acct-1",
        title="素材合成视频",
        plan_id=plan["plan_id"],
        asset_type="script",
        platform="douyin",
        production_kind="faceless_video",
        content={
            "schema": "marketing.faceless_video.v1",
            "script": "先展示结果，再解释方法。",
            "validation": {"ready": True, "issues": []},
            "material_manifest": {"status": "planned"},
            "sound_plan": {"mode": "original_voice_only"},
        },
        evidence_refs=[evidence_id],
    )


def _visual_asset(media, *, account_id, name, color):
    return media.import_bytes(
        user_id="default",
        account_id=account_id,
        name=name,
        media_type="image",
        role="broll",
        source_type="user_upload",
        rights_status="user_confirmed",
        payload=_png(color),
        filename=f"{name}.png",
        mime_type="image/png",
    )


def _edl(*asset_ids):
    return {
        "version": "marketing.faceless_video.edl.v1",
        "width": 360,
        "height": 640,
        "fps": 24,
        "clips": [
            {
                "media_asset_id": asset_id,
                "source_in": 0,
                "duration": 0.6,
            }
            for asset_id in asset_ids
        ],
        "captions": [],
    }


def _video_ir(asset_id, *, motion_intent=None, text=None):
    return {
        "version": "marketing.video.ir.v1",
        "canvas": {"width": 360, "height": 640, "fps": 24},
        "scenes": [
            {
                "id": "scene_hook",
                "duration": 0.6,
                "purpose": "show the result before explaining the method",
                "visuals": [
                    {
                        "media_asset_id": asset_id,
                        "source_in": 0,
                        "fit": "cover",
                    }
                ],
                "text": text or [],
                "motion_intent": motion_intent or ["straight_cut"],
                "constraints": {
                    "safe_area": "short_vertical",
                    "rights_required": True,
                },
                "renderer_policy": {
                    "preference": "auto",
                    "fallback": "ffmpeg",
                },
                "review_rules": ["the hook is visually legible"],
            }
        ],
        "captions": [],
        "audio": {},
        "review_rules": ["duration and dimensions match the approved plan"],
    }


def test_compact_video_setup_builds_idempotent_local_storyboard_and_ir(tmp_path):
    paths = _paths(tmp_path)
    evidence_id = EvidenceRepository(paths).capture_web_extract_result(
        user_id="default",
        account_id="acct-1",
        result={
            "results": [{
                "url": "https://example.com/ai-bubble",
                "title": "source",
                "content": "Verified context for the short-video script.",
            }]
        },
        session_id="compact-video-test",
    )[0]["id"]
    content = ContentAssetRepository(paths)
    plan = content.save_production_plan(
        user_id="default",
        account_id="acct-1",
        plan={
            "status": "planned",
            "kind": "faceless_video",
            "objective": "把一篇有证据的稿子做成抖音短视频",
            "target_platforms": ["douyin"],
            "constraints": {},
            "audience_model": {"target_audience": "独立创业者"},
        },
    )
    script = """### Shot 1 — HOOK (0-3s)
**On-screen text**: AI 工具不是护城河

### Shot 2 — CLOSE (3-9s)
**VO**: 真正重要的是判断力和问题定义能力。
"""
    repository = VideoProductionRepository(paths)
    first = repository.prepare_from_script(
        user_id="default",
        account_id="acct-1",
        plan_id=plan["plan_id"],
        title="AI 泡沫之后",
        script=script,
        platform="douyin",
        evidence_refs=[evidence_id],
    )
    repeated = repository.prepare_from_script(
        user_id="default",
        account_id="acct-1",
        plan_id=plan["plan_id"],
        title="AI 泡沫之后",
        script=script,
        platform="douyin",
        evidence_refs=[evidence_id],
    )

    assert first["production"]["status"] == "prepared"
    assert first["production"]["id"] == repeated["production"]["id"]
    assert first["source_asset"]["id"] == repeated["source_asset"]["id"]
    assert len(first["production"]["video_ir"]["scenes"]) == 2
    assert [scene["duration"] for scene in first["production"]["video_ir"]["scenes"]] == [3.0, 6.0]
    assert len(first["storyboard_assets"]) == 2
    assert all(item["provider"] == "marketing_os_local_storyboard" for item in first["storyboard_assets"])
    assert all(item["rights_status"] == "inherited" for item in first["storyboard_assets"])
    assert len(first["material_searches"]) == 2
    assert first["voice_job"]["status"] == "prepared"
    assert first["production"]["video_ir"]["scenes"][0]["text"][0]["text"] == "AI 工具不是护城河"
    assert first["production"]["video_ir"]["captions"][0]["text"] == "真正重要的是判断力和问题定义能力。"
    readiness = repository.render_readiness(
        production_id=first["production"]["id"],
        user_id="default",
        account_id="acct-1",
    )
    assert readiness["ready"] is False
    assert {item["code"] for item in readiness["blockers"]} >= {
        "storyboard_placeholders",
        "voiceover_missing",
    }
    assert first["external_effect_executed"] is False

    # A previously accepted static-card preview must not be able to bypass the
    # native video-production gate and enter publishing approval.
    with sqlite3.connect(paths.agent_db) as db:
        source_row = db.execute(
            "SELECT content_json FROM content_assets WHERE id=?",
            (first["source_asset"]["id"],),
        ).fetchone()
        source_content = json.loads(source_row[0])
        source_content["production"] = {
            "production_id": first["production"]["id"],
        }
        db.execute(
            """UPDATE content_assets
            SET status='review_ready',human_review_status='accepted',content_json=?
            WHERE id=?""",
            (
                json.dumps(source_content, ensure_ascii=False),
                first["source_asset"]["id"],
            ),
        )
        db.execute(
            "UPDATE marketing_video_productions SET status='completed' WHERE id=?",
            (first["production"]["id"],),
        )
    with pytest.raises(ValueError, match="storyboard placeholders"):
        PublishingRepository(paths).prepare_action(
            user_id="default",
            account_id="acct-1",
            asset_id=first["source_asset"]["id"],
            platform="douyin",
            provider="playwright_mcp",
        )


def test_accepted_campaign_hands_video_variant_directly_to_material_pipeline(tmp_path):
    paths = _paths(tmp_path)
    evidence_id = EvidenceRepository(paths).capture_web_extract_result(
        user_id="default",
        account_id="acct-1",
        result={
            "results": [{
                "url": "https://example.com/direct-video",
                "title": "source",
                "content": "Verified evidence for one platform-native video variant.",
            }]
        },
        session_id="direct-video-test",
    )[0]["id"]
    content = ContentAssetRepository(paths)
    campaign_plan = content.save_production_plan(
        user_id="default",
        account_id="acct-1",
        plan={
            "status": "planned",
            "kind": "cross_platform_campaign",
            "objective": "AI 泡沫过后，判断力才是一人公司的护城河",
            "target_platforms": ["douyin", "wechat_official"],
            "constraints": {},
            "audience_model": {"target_audience": "独立创业者"},
        },
    )
    campaign = content.create_draft(
        user_id="default",
        account_id="acct-1",
        title="AI 泡沫过后，判断力才是护城河",
        plan_id=campaign_plan["plan_id"],
        asset_type="script",
        platform="multi_platform",
        production_kind="cross_platform_campaign",
        content={
            "content_kernel": "AI 工具会同质化，判断力不会。",
            "platform_variants": {
                "douyin": {
                    "adaptation_basis": {
                        "audience_intent": "刷流中快速获得反常识判断",
                        "cta": "评论自己的护城河",
                        "format": "short_video",
                        "opening": "先给结论",
                        "structure": "冲突到结论",
                    },
                    "body_markdown": """### Shot 1 — HOOK (0-3s)
**Visual**: 创业者工位近景
**VO**: AI 工具会同质化，但判断力不会。
**On-screen text**: 真正的护城河是判断力

### Shot 2 — CLOSE (3-7s)
**Visual**: 电脑画面快切
**VO**: 别再把工具清单当成经营战略。
**On-screen text**: 工具不是战略
""",
                    "format": "short_video",
                    "title": "判断力才是护城河",
                },
                "wechat_official": {
                    "adaptation_basis": {
                        "audience_intent": "系统理解经营判断",
                        "cta": "转发给创业伙伴",
                        "opening": "从工具同质化切入",
                        "structure": "问题到框架",
                    },
                    "body_markdown": "这是一篇平台长文。",
                    "format": "long_article",
                    "title": "判断力才是护城河",
                },
            },
        },
        evidence_refs=[evidence_id],
    )
    campaign = content.record_human_review(
        asset_id=campaign["id"],
        user_id="default",
        account_id="acct-1",
        decision="accepted",
        confirmed=True,
    )
    video_plan = content.save_production_plan(
        user_id="default",
        account_id="acct-1",
        plan={
            "status": "planned",
            "kind": "faceless_video",
            "objective": "把 AI 泡沫过后判断力才是护城河做成抖音素材视频",
            "target_platforms": ["douyin"],
            "constraints": {},
            "audience_model": {"target_audience": "独立创业者"},
        },
    )
    OperatingLoopRepository(paths).create_preflight(
        user_id="default",
        account_id="acct-1",
        plan_id=video_plan["plan_id"],
        platform="douyin",
        session_id="direct-video-test",
        formula_version="test-v1",
        input={},
        scores={"overall": 0.9},
        decision={
            "preflight_decision": {"go": True, "status": "ready_for_asset_draft"}
        },
    )
    library_asset = _visual_asset(
        MediaAssetRepository(paths),
        account_id="acct-1",
        name="创业者工位 电脑画面",
        color="#305f66",
    )
    repository = VideoProductionRepository(
        paths,
        enabled_renderers=[
            "ffmpeg_timeline_v1",
            "remotion_scene_v1",
            "hyperframes_scene_v1",
        ],
    )

    prepared = repository.prepare_from_campaign(
        user_id="default",
        account_id="acct-1",
        campaign_asset_id=campaign["id"],
        platform="douyin",
    )

    assert prepared["source_asset"]["content"]["source_campaign_asset_id"] == campaign["id"]
    assert len(prepared["material_searches"]) == 2
    assert all(search["candidates"] for search in prepared["material_searches"])
    assert [scene["renderer"] for scene in prepared["production"]["render_plan"]["scenes"]] == [
        "remotion_scene_v1",
        "hyperframes_scene_v1",
    ]
    first_search = prepared["material_searches"][0]
    local_candidate = next(
        candidate
        for candidate in first_search["candidates"]
        if candidate["provider_asset_id"] == library_asset["id"]
    )
    revised = repository.select_material_candidate(
        production_id=prepared["production"]["id"],
        scene_id="scene_001",
        candidate_id=local_candidate["id"],
        user_id="default",
        account_id="acct-1",
        rights_reviewed=True,
    )
    assert revised["production"]["id"] != prepared["production"]["id"]
    assert revised["production"]["video_ir"]["scenes"][0]["visuals"][0]["media_asset_id"] == library_asset["id"]
    assert revised["readiness"]["placeholder_scene_count"] == 1


def test_video_ir_prepare_persists_ir_plan_and_compiled_edl(tmp_path):
    paths = _paths(tmp_path)
    source = _source_asset(paths)
    media = MediaAssetRepository(paths)
    visual = _visual_asset(media, account_id="acct-1", name="ir", color="#d8c45a")
    repository = VideoProductionRepository(paths)

    prepared = repository.prepare(
        user_id="default",
        account_id="acct-1",
        source_asset_id=source["id"],
        video_ir=_video_ir(visual["id"]),
    )
    repeated = repository.prepare(
        user_id="default",
        account_id="acct-1",
        source_asset_id=source["id"],
        video_ir=_video_ir(visual["id"]),
    )

    assert repeated["id"] == prepared["id"]
    assert prepared["video_ir"]["version"] == "marketing.video.ir.v1"
    assert len(prepared["video_ir"]["ir_sha256"]) == 64
    assert prepared["render_plan"]["executable"] is True
    assert prepared["render_plan"]["scenes"][0]["renderer"] == "ffmpeg_timeline_v1"
    assert prepared["edl"]["clips"][0]["media_asset_id"] == visual["id"]


def test_video_ir_prepare_blocks_unavailable_renderer_capability(tmp_path):
    paths = _paths(tmp_path)
    source = _source_asset(paths)
    visual = _visual_asset(
        MediaAssetRepository(paths),
        account_id="acct-1",
        name="advanced-ir",
        color="#305f66",
    )
    repository = VideoProductionRepository(
        paths,
        enabled_renderers=["ffmpeg_timeline_v1"],
    )

    prepared = repository.prepare(
        user_id="default",
        account_id="acct-1",
        source_asset_id=source["id"],
        video_ir=_video_ir(
            visual["id"],
            motion_intent=["kinetic_typography"],
            text=[{"text": "先看结果", "role": "headline"}],
        ),
    )
    assert prepared["render_plan"]["executable"] is False
    with pytest.raises(ValueError, match="not render-ready"):
        repository.approve(
            production_id=prepared["id"],
            user_id="default",
            account_id="acct-1",
            approval_ref="human-review:blocked-renderer",
            confirmed_by_user=True,
        )


def test_video_production_schema_adds_ir_columns_to_legacy_table(tmp_path):
    paths = _paths(tmp_path)
    with sqlite3.connect(paths.agent_db) as db:
        db.execute(
            """CREATE TABLE marketing_video_productions (
            id TEXT PRIMARY KEY,
            idempotency_key TEXT NOT NULL UNIQUE,
            user_id TEXT NOT NULL,
            account_id TEXT NOT NULL,
            source_asset_id TEXT NOT NULL,
            source_asset_version INTEGER NOT NULL,
            provider TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'prepared',
            edl_json TEXT NOT NULL,
            approval_ref TEXT,
            voice_asset_id TEXT,
            final_video_asset_id TEXT,
            output_asset_id TEXT,
            receipt_json TEXT NOT NULL DEFAULT '{}',
            failure_code TEXT,
            created_at TEXT NOT NULL,
            started_at TEXT,
            settled_at TEXT,
            updated_at TEXT NOT NULL
            )"""
        )

    VideoProductionRepository(paths)

    with sqlite3.connect(paths.agent_db) as db:
        columns = {
            row[1]
            for row in db.execute("PRAGMA table_info(marketing_video_productions)")
        }
    assert {"video_ir_json", "render_plan_json"} <= columns


def test_legacy_edl_idempotency_key_is_preserved_and_ir_is_backfilled(tmp_path):
    paths = _paths(tmp_path)
    source = _source_asset(paths)
    visual = _visual_asset(
        MediaAssetRepository(paths),
        account_id="acct-1",
        name="legacy-idempotency",
        color="#d8c45a",
    )
    repository = VideoProductionRepository(paths)
    normalized = repository._normalize_edl(
        _edl(visual["id"]),
        user_id="default",
        account_id="acct-1",
    )
    encoded = json.dumps(
        normalized,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    key = hashlib.sha256(
        (
            f"default\0acct-1\0{source['id']}\0{source['version']}\0"
            f"ffmpeg_timeline_v1\0{encoded}"
        ).encode("utf-8")
    ).hexdigest()
    with sqlite3.connect(paths.agent_db) as db:
        db.execute(
            """INSERT INTO marketing_video_productions
            (id,idempotency_key,user_id,account_id,source_asset_id,
             source_asset_version,provider,status,edl_json,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,'prepared',?,?,?)""",
            (
                "video_production_legacy",
                key,
                "default",
                "acct-1",
                source["id"],
                source["version"],
                "ffmpeg_timeline_v1",
                encoded,
                "2026-07-14T00:00:00+00:00",
                "2026-07-14T00:00:00+00:00",
            ),
        )

    prepared = repository.prepare(
        user_id="default",
        account_id="acct-1",
        source_asset_id=source["id"],
        edl=_edl(visual["id"]),
    )

    assert prepared["id"] == "video_production_legacy"
    assert prepared["video_ir"]["version"] == "marketing.video.ir.v1"
    assert prepared["render_plan"]["executable"] is True


def test_video_prepare_is_idempotent_and_account_scoped(tmp_path):
    paths = _paths(tmp_path)
    source = _source_asset(paths)
    media = MediaAssetRepository(paths)
    first = _visual_asset(media, account_id="acct-1", name="first", color="#d8c45a")
    foreign = _visual_asset(media, account_id="acct-2", name="foreign", color="#305f66")
    repository = VideoProductionRepository(paths)

    prepared = repository.prepare(
        user_id="default",
        account_id="acct-1",
        source_asset_id=source["id"],
        edl=_edl(first["id"]),
    )
    duplicate = repository.prepare(
        user_id="default",
        account_id="acct-1",
        source_asset_id=source["id"],
        edl=_edl(first["id"]),
    )

    assert prepared["id"] == duplicate["id"]
    assert prepared["status"] == "prepared"
    assert prepared["edl"]["duration"] == 0.6
    with pytest.raises(ValueError, match="another account"):
        repository.prepare(
            user_id="default",
            account_id="acct-1",
            source_asset_id=source["id"],
            edl=_edl(foreign["id"]),
        )
    with pytest.raises(ValueError, match="explicit human"):
        repository.approve(
            production_id=prepared["id"],
            user_id="default",
            account_id="acct-1",
            approval_ref="review:test",
            confirmed_by_user=False,
        )


def test_video_tool_prepares_renderer_neutral_ir(tmp_path, monkeypatch):
    paths = _paths(tmp_path)
    _bind_session(paths, tmp_path, monkeypatch)
    source = _source_asset(paths)
    visual = _visual_asset(
        MediaAssetRepository(paths),
        account_id="acct-1",
        name="tool-ir",
        color="#305f66",
    )

    prepared = json.loads(
        handle_function_call(
            "marketing_prepare_faceless_render",
            {
                "source_asset_id": source["id"],
                "video_ir": _video_ir(visual["id"]),
            },
            task_id="video-session",
            session_id="video-session",
            enabled_toolsets=["marketing"],
        )
    )

    assert prepared["status"] == "prepared"
    assert prepared["video_ir"]["version"] == "marketing.video.ir.v1"
    assert prepared["render_plan"]["scenes"][0]["renderer"] == ("ffmpeg_timeline_v1")


def test_failed_video_production_can_be_explicitly_reapproved(tmp_path):
    paths = _paths(tmp_path)
    source = _source_asset(paths)
    media = MediaAssetRepository(paths)
    visual = _visual_asset(media, account_id="acct-1", name="retry", color="#305f66")

    def fail_runner(_command, _log_path):
        raise RuntimeError("synthetic render failure")

    failing = VideoProductionRepository(
        paths,
        ffmpeg_path="ffmpeg",
        ffprobe_path="ffprobe",
        runner=fail_runner,
    )
    prepared = failing.prepare(
        user_id="default",
        account_id="acct-1",
        source_asset_id=source["id"],
        edl=_edl(visual["id"]),
    )
    failing.approve(
        production_id=prepared["id"],
        user_id="default",
        account_id="acct-1",
        approval_ref="human-review:first-attempt",
        confirmed_by_user=True,
    )
    with pytest.raises(RuntimeError, match="synthetic render failure"):
        failing.execute_ffmpeg(
            production_id=prepared["id"],
            user_id="default",
            account_id="acct-1",
        )

    failed = failing.get(
        production_id=prepared["id"],
        user_id="default",
        account_id="acct-1",
    )
    assert failed["status"] == "failed"
    retried = failing.approve(
        production_id=prepared["id"],
        user_id="default",
        account_id="acct-1",
        approval_ref="human-review:retry",
        confirmed_by_user=True,
    )
    assert retried["status"] == "approved"
    assert retried["failure_code"] is None
    assert retried["approval_ref"] == "human-review:retry"


def test_render_revision_is_idempotent_by_production_id(tmp_path):
    paths = _paths(tmp_path)
    source = _source_asset(paths)
    repository = ContentAssetRepository(paths)
    production = {
        "version": "marketing.faceless_video.production.v1",
        "production_id": "video_production_recovery_test",
        "renderer": "ffmpeg_timeline_v1",
        "edl": _edl("media_recovery_test"),
        "final_video_asset_id": "media_final_recovery_test",
        "technical": {"duration_seconds": 0.6, "width": 360, "height": 640},
    }

    first = repository.create_faceless_render_revision(
        parent_asset_id=source["id"],
        user_id="default",
        account_id="acct-1",
        production=production,
    )
    repeated = repository.create_faceless_render_revision(
        parent_asset_id=source["id"],
        user_id="default",
        account_id="acct-1",
        production=production,
    )

    assert repeated["id"] == first["id"]
    assert (
        repeated["content"]["production"]["production_id"]
        == production["production_id"]
    )


@pytest.mark.skipif(
    not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
    reason="FFmpeg integration is unavailable",
)
def test_video_tools_render_through_bound_hermes_session(tmp_path, monkeypatch):
    paths = _paths(tmp_path)
    _bind_session(paths, tmp_path, monkeypatch)
    source = _source_asset(paths)
    visual = _visual_asset(
        MediaAssetRepository(paths),
        account_id="acct-1",
        name="tool-entry",
        color="#d8c45a",
    )

    prepared = json.loads(
        handle_function_call(
            "marketing_prepare_faceless_render",
            {
                "source_asset_id": source["id"],
                "renderer": "ffmpeg_timeline_v1",
                "edl": _edl(visual["id"]),
            },
            task_id="video-session",
            session_id="video-session",
            enabled_toolsets=["marketing"],
        )
    )
    completed = json.loads(
        handle_function_call(
            "marketing_effect_faceless_render",
            {
                "production_id": prepared["id"],
                "approval_ref": "human-review:tool-test",
                "confirmed_by_user": True,
            },
            task_id="video-session",
            session_id="video-session",
            enabled_toolsets=["marketing"],
        )
    )
    listed = json.loads(
        handle_function_call(
            "marketing_read_video_productions",
            {"status": "completed"},
            task_id="video-session",
            session_id="video-session",
            enabled_toolsets=["marketing"],
        )
    )

    assert completed["status"] == "completed"
    assert completed["receipt"]["receipt_type"] == "render_complete"
    assert (
        completed["receipt"]["summary"]["technical"]["quality_assurance"][
            "version"
        ]
        == "marketing.media_quality.v1"
    )
    assert listed["total"] == 1
    assert listed["productions"][0]["id"] == prepared["id"]


@pytest.mark.skipif(
    not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
    reason="FFmpeg integration is unavailable",
)
def test_render_muxes_provider_tts_and_user_licensed_bgm(tmp_path):
    paths = _paths(tmp_path)
    source = _source_asset(paths)
    media = MediaAssetRepository(paths)
    visual = _visual_asset(
        media, account_id="acct-1", name="audio-lane", color="#d8c45a"
    )

    def tts_runner(_text, output_path):
        target = os.path.splitext(output_path)[0] + ".wav"
        subprocess.run(
            [
                shutil.which("ffmpeg"), "-y", "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=0.6",
                "-ar", "48000", target,
            ],
            check=True,
        )
        return json.dumps({
            "success": True, "file_path": target, "provider": "integration_tts"
        })

    audio = ProductionAudioRepository(paths, tts_runner=tts_runner)
    job = audio.prepare_voice(
        user_id="default", account_id="acct-1", name="真实旁白",
        script_text="真实旁白测试",
    )
    audio.approve(
        job_id=job["id"], user_id="default", account_id="acct-1",
        approval_ref="human-review:voice", confirmed_by_user=True,
    )
    voice_job = audio.execute(
        job_id=job["id"], user_id="default", account_id="acct-1"
    )

    bgm_path = tmp_path / "bgm.wav"
    subprocess.run(
        [
            shutil.which("ffmpeg"), "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "sine=frequency=220:duration=0.6",
            "-ar", "48000", str(bgm_path),
        ],
        check=True,
    )
    music = media.import_bytes(
        user_id="default", account_id="acct-1", name="用户授权 BGM",
        media_type="audio", role="music", source_type="user_upload",
        rights_status="user_confirmed", payload=bgm_path.read_bytes(),
        filename="bgm.wav", mime_type="audio/wav",
    )
    edl = _edl(visual["id"])
    edl["voice_asset_id"] = voice_job["output_asset_id"]
    edl["music_asset_id"] = music["id"]
    repository = VideoProductionRepository(paths)
    prepared = repository.prepare(
        user_id="default", account_id="acct-1",
        source_asset_id=source["id"], edl=edl,
    )
    repository.approve(
        production_id=prepared["id"], user_id="default", account_id="acct-1",
        approval_ref="human-review:audio-mix", confirmed_by_user=True,
    )
    completed = repository.execute(
        production_id=prepared["id"], user_id="default", account_id="acct-1"
    )

    quality = completed["receipt"]["summary"]["technical"]["quality_assurance"]
    assert completed["status"] == "completed"
    assert quality["probe"]["audio"]["present"] is True
    assert quality["probe"]["audio"]["sample_rate"] == 48000
    assert completed["receipt"]["summary"]["input_asset_ids"] == [
        visual["id"], voice_job["output_asset_id"], music["id"]
    ]


@pytest.mark.skipif(
    not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
    reason="FFmpeg integration is unavailable",
)
def test_video_render_recovers_after_receipt_stage_failure(tmp_path, monkeypatch):
    paths = _paths(tmp_path)
    source = _source_asset(paths)
    visual = _visual_asset(
        MediaAssetRepository(paths),
        account_id="acct-1",
        name="receipt-recovery",
        color="#305f66",
    )
    repository = VideoProductionRepository(paths)
    prepared = repository.prepare(
        user_id="default",
        account_id="acct-1",
        source_asset_id=source["id"],
        edl=_edl(visual["id"]),
    )
    repository.approve(
        production_id=prepared["id"],
        user_id="default",
        account_id="acct-1",
        approval_ref="human-review:first-receipt-attempt",
        confirmed_by_user=True,
    )
    original_create_receipt = OperatingLoopRepository.create_receipt

    def fail_receipt(_self, **_kwargs):
        raise RuntimeError("synthetic receipt failure")

    monkeypatch.setattr(OperatingLoopRepository, "create_receipt", fail_receipt)
    with pytest.raises(RuntimeError, match="synthetic receipt failure"):
        repository.execute_ffmpeg(
            production_id=prepared["id"],
            user_id="default",
            account_id="acct-1",
        )
    failed = repository.get(
        production_id=prepared["id"],
        user_id="default",
        account_id="acct-1",
    )
    assert failed["status"] == "failed"
    assert failed["final_video_asset_id"]
    assert failed["output_asset_id"]

    monkeypatch.setattr(
        OperatingLoopRepository,
        "create_receipt",
        original_create_receipt,
    )
    repository.approve(
        production_id=prepared["id"],
        user_id="default",
        account_id="acct-1",
        approval_ref="human-review:receipt-retry",
        confirmed_by_user=True,
    )
    completed = repository.execute_ffmpeg(
        production_id=prepared["id"],
        user_id="default",
        account_id="acct-1",
    )

    assert completed["status"] == "completed"
    assert completed["output_asset_id"] == failed["output_asset_id"]
    assets = ContentAssetRepository(paths).list(
        user_id="default",
        account_id="acct-1",
    )["assets"]
    matching = [
        asset
        for asset in assets
        if (asset.get("content") or {}).get("production", {}).get("production_id")
        == prepared["id"]
    ]
    assert len(matching) == 1


@pytest.mark.skipif(
    not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
    reason="FFmpeg integration is unavailable",
)
def test_video_production_renders_and_settles_immutable_revision(tmp_path):
    paths = _paths(tmp_path)
    source = _source_asset(paths)
    media = MediaAssetRepository(paths)
    first = _visual_asset(media, account_id="acct-1", name="first", color="#d8c45a")
    second = _visual_asset(media, account_id="acct-1", name="second", color="#305f66")
    repository = VideoProductionRepository(paths)
    prepared = repository.prepare(
        user_id="default",
        account_id="acct-1",
        source_asset_id=source["id"],
        edl=_edl(first["id"], second["id"]),
    )
    approved = repository.approve(
        production_id=prepared["id"],
        user_id="default",
        account_id="acct-1",
        approval_ref="human-review:test-session",
        confirmed_by_user=True,
    )

    completed = repository.execute_ffmpeg(
        production_id=approved["id"],
        user_id="default",
        account_id="acct-1",
        session_id="test-session",
    )
    repeated = repository.execute_ffmpeg(
        production_id=approved["id"],
        user_id="default",
        account_id="acct-1",
        session_id="test-session",
    )

    assert completed["status"] == "completed"
    assert repeated["id"] == completed["id"]
    assert completed["receipt"]["receipt_type"] == "render_complete"
    assert len(completed["receipt"]["summary"]["video_ir_sha256"]) == 64
    assert len(completed["receipt"]["summary"]["render_plan_sha256"]) == 64
    final_media = media.get(
        asset_id=completed["final_video_asset_id"],
        user_id="default",
    )
    assert final_media["role"] == "final_video"
    assert final_media["source_type"] == "derived"
    assert final_media["rights_status"] == "inherited"
    assert final_media["metadata"]["width"] == 360
    assert final_media["metadata"]["height"] == 640
    assert final_media["metadata"]["duration_seconds"] == pytest.approx(1.2, abs=0.12)
    assert final_media["metadata"]["quality_assurance"]["disposition"] == "ready"
    output = ContentAssetRepository(paths).get(
        asset_id=completed["output_asset_id"],
        user_id="default",
        account_id="acct-1",
    )
    assert output["version"] == 2
    assert output["parent_id"] == source["id"]
    assert output["status"] == "review_ready"
    assert output["content"]["production"]["production_id"] == completed["id"]
    assert output["content"]["production"]["final_video_asset_id"] == final_media["id"]
    assert (
        output["content"]["production"]["video_ir"]["ir_sha256"]
        == (completed["video_ir"]["ir_sha256"])
    )
    assert (
        output["content"]["production"]["render_plan"]["source_ir_sha256"]
        == (completed["video_ir"]["ir_sha256"])
    )
    previous = ContentAssetRepository(paths).get(
        asset_id=source["id"],
        user_id="default",
        account_id="acct-1",
    )
    assert previous["status"] == "superseded"


@pytest.mark.skipif(
    not os.environ.get("MARKETING_OS_TEST_BROWSER_EXECUTABLE")
    or not shutil.which("node")
    or not shutil.which("ffmpeg")
    or not shutil.which("ffprobe"),
    reason="offline advanced renderer integration is unavailable",
)
def test_hybrid_video_ir_renders_remotion_and_hyperframes_with_scene_cache(tmp_path):
    paths = _paths(tmp_path)
    source = _source_asset(paths)
    media = MediaAssetRepository(paths)
    first = _visual_asset(media, account_id="acct-1", name="remotion", color="#d8c45a")
    second = _visual_asset(
        media, account_id="acct-1", name="hyperframes", color="#305f66"
    )
    scenes = [
        {
            "id": "scene_remotion",
            "duration": 0.6,
            "purpose": "kinetic hook",
            "visuals": [
                {"media_asset_id": first["id"], "source_in": 0, "fit": "cover"}
            ],
            "text": [{"text": "先看结果", "role": "headline"}],
            "motion_intent": ["kinetic_typography"],
            "constraints": {"safe_area": "short_vertical", "rights_required": True},
            "renderer_policy": {"preference": "remotion", "fallback": "ffmpeg"},
            "review_rules": ["headline is legible"],
        },
        {
            "id": "scene_hyperframes",
            "duration": 0.6,
            "purpose": "designed transition",
            "visuals": [
                {"media_asset_id": second["id"], "source_in": 0, "fit": "cover"}
            ],
            "text": [{"text": "再解释方法", "role": "headline"}],
            "motion_intent": ["html_css_motion"],
            "constraints": {"safe_area": "short_vertical", "rights_required": True},
            "renderer_policy": {"preference": "hyperframes", "fallback": "ffmpeg"},
            "review_rules": ["transition is deterministic"],
        },
    ]
    runtime = VideoRendererRuntime(
        node_executable=shutil.which("node"),
        browser_executable=os.environ["MARKETING_OS_TEST_BROWSER_EXECUTABLE"],
    )
    repository = VideoProductionRepository(paths, renderer_runtime=runtime)
    prepared = repository.prepare(
        user_id="default",
        account_id="acct-1",
        source_asset_id=source["id"],
        video_ir={
            "version": "marketing.video.ir.v1",
            "canvas": {"width": 360, "height": 640, "fps": 24},
            "scenes": scenes,
            "captions": [],
            "audio": {},
            "review_rules": ["review the whole film"],
        },
    )
    assert [item["renderer"] for item in prepared["render_plan"]["scenes"]] == [
        "remotion_scene_v1",
        "hyperframes_scene_v1",
    ]
    repository.approve(
        production_id=prepared["id"],
        user_id="default",
        account_id="acct-1",
        approval_ref="human-review:hybrid-integration",
        confirmed_by_user=True,
    )
    completed = repository.execute_ffmpeg(
        production_id=prepared["id"],
        user_id="default",
        account_id="acct-1",
    )
    outputs = completed["receipt"]["summary"]["technical"]["scene_outputs"]
    assert [item["renderer"] for item in outputs] == [
        "remotion_scene_v1",
        "hyperframes_scene_v1",
    ]
    assert all(len(item["output_sha256"]) == 64 for item in outputs)

    _, cached_technical = repository._render(completed, tmp_path / "cached-render")
    assert all(item["cache_hit"] is True for item in cached_technical["scene_outputs"])
