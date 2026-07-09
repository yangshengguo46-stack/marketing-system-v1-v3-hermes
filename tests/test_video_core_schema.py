"""video_core 已写实部分的单元测试：画布/EDL/存储/成本/hook/harness。"""

import asyncio

import pytest

from engine.video_core.adapter import ModelTier
from engine.video_core.cost import (
    default_budget_lines,
    estimate_production_phase,
    estimate_video,
)
from engine.video_core.edl import ClipEntry, EDL, SubtitleEntry, TimelineSlot
from engine.video_core.editing_engine import (
    build_edl_from_segments,
    edl_handoff_summary,
    fill_edl_clips,
    shared_editing_contract,
)
from engine.video_core.hooks import (
    AutoApproveGate,
    BudgetCostGate,
    GateDecision,
    GateRequest,
)
from engine.video_core.renderer import Renderer
from engine.video_core.project_store import ProjectStore
from engine.video_core.schema import Budget, SpendRecord
from engine.video_core.testing import (
    MockAdapter,
    ScriptedGate,
    make_demo_project,
    make_demo_skeleton,
)


# ---------------------------------------------------------------- 画布依赖图


def test_affected_shots_cascade():
    proj = make_demo_project()
    affected = proj.affected_shots("asset-hero")
    assert {s.id for s in affected} == {"shot-1", "shot-2"}
    assert proj.affected_shots("asset-nonexistent") == []


def test_pending_task_shots_for_recovery():
    proj = make_demo_project()
    pending = proj.pending_task_shots()
    assert [s.id for s in pending] == ["shot-2"]
    assert pending[0].task_id == "mock-task-99"


def test_shot_and_asset_lookup():
    proj = make_demo_project()
    assert proj.get_shot("shot-3").scene_id == "scene-2"
    assert proj.get_shot("nope") is None
    assert proj.get_asset("asset-hero").name == "主角"


# ---------------------------------------------------------------- EDL 骨架


def test_skeleton_validation_passes_for_demo():
    skeleton = make_demo_skeleton()
    assert skeleton.validate_skeleton() == []
    assert skeleton.total_duration_sec() == pytest.approx(10.0)


def test_skeleton_validation_catches_problems():
    bad = EDL(slots=[
        TimelineSlot(id="s1", order=1, duration_sec=0),
        TimelineSlot(id="s1", order=1, duration_sec=2.0),
    ])
    problems = bad.validate_skeleton()
    assert any("order 重复" in p for p in problems)
    assert any("id 重复" in p for p in problems)
    assert any("时长非法" in p for p in problems)


def test_unfilled_slots():
    skeleton = make_demo_skeleton()
    assert len(skeleton.unfilled_slots()) == 3


def test_renderer_builds_animatic_command_without_running_ffmpeg(tmp_path):
    edl = EDL(
        resolution="1080x1920",
        slots=[
            TimelineSlot(id="slot-1", order=1, duration_sec=2.0, shot_id="shot-1", narration="第一句"),
            TimelineSlot(id="slot-2", order=2, duration_sec=3.0, shot_id="shot-2", narration="第二句"),
        ],
        subtitles=[SubtitleEntry(text="第一句", start_sec=0, end_sec=2.0)],
    )

    command = Renderer(ffmpeg_path="/bin/ffmpeg").build_animatic_command(
        edl, tmp_path, tmp_path / "final" / "animatic.mp4",
    )

    joined = " ".join(command)
    assert command[0] == "/bin/ffmpeg"
    assert "-loop" in command
    assert str(tmp_path / "frames" / "shot-1.png") in command
    assert "concat=n=2:v=1:a=0" in joined
    assert "drawtext=" in joined
    assert str(tmp_path / "final" / "animatic.mp4") == command[-1]


def test_renderer_builds_final_command_from_shot_videos(tmp_path):
    edl = EDL(
        resolution="1920x1080",
        slots=[
            TimelineSlot(id="slot-1", order=1, duration_sec=2.0, shot_id="shot-a"),
            TimelineSlot(id="slot-2", order=2, duration_sec=3.0, shot_id="shot-b"),
        ],
        clips=[
            ClipEntry(slot_id="slot-2", shot_id="shot-b"),
            ClipEntry(slot_id="slot-1", shot_id="shot-a", source_in_sec=0.5, source_out_sec=2.5),
        ],
    )

    command = Renderer().build_final_command(edl, tmp_path, tmp_path / "final.mp4")
    joined = " ".join(command)

    assert command.index(str(tmp_path / "videos" / "shot-a.mp4")) < command.index(str(tmp_path / "videos" / "shot-b.mp4"))
    assert "scale=1920:1080" in joined
    assert "trim=start=0.5:end=2.5" in joined
    assert "concat=n=2:v=1:a=0" in joined
    assert "-an" in command


def test_renderer_builds_final_command_with_voice_and_bgm(tmp_path):
    edl = EDL(
        resolution="1080x1920",
        slots=[TimelineSlot(id="slot-1", order=1, duration_sec=2.0, shot_id="shot-a")],
        clips=[ClipEntry(slot_id="slot-1", shot_id="shot-a")],
    )

    command = Renderer(ffmpeg_path="/bin/ffmpeg").build_final_command(
        edl,
        tmp_path,
        tmp_path / "final.mp4",
        voice_path=tmp_path / "audio" / "voice.wav",
        bgm_path=tmp_path / "audio" / "bgm.wav",
        bgm_volume=0.12,
    )
    joined = " ".join(command)

    assert str(tmp_path / "audio" / "voice.wav") in command
    assert str(tmp_path / "audio" / "bgm.wav") in command
    assert "-stream_loop" in command
    assert "volume=0.12" in joined
    assert "amix=inputs=2" in joined
    assert "-map [aout]" in joined
    assert "-an" not in command


def test_renderer_refuses_final_without_clips(tmp_path):
    with pytest.raises(ValueError, match="at least one clip"):
        Renderer().build_final_command(EDL(slots=[TimelineSlot(id="slot", order=1, duration_sec=1)]), tmp_path, tmp_path / "out.mp4")


def test_shared_editing_engine_builds_faceless_and_premium_edl_contract():
    faceless_contract = shared_editing_contract("faceless_video")
    premium_contract = shared_editing_contract("premium_human_video")

    assert faceless_contract["single_source_of_truth"] == "EDL"
    assert premium_contract["single_source_of_truth"] == "EDL"
    assert "code_generated_visual" in faceless_contract["material_inputs"]
    assert "seedance_generated_shot" in premium_contract["material_inputs"]

    edl = build_edl_from_segments(
        [
            {"id": "slot_01", "order": 1, "duration_sec": 2.5, "narration": "开头钩子", "shot_id": "shot_01", "energy": "high"},
            {"id": "slot_02", "order": 2, "duration_sec": 3.0, "narration": "解释观点", "shot_id": "shot_02"},
        ],
        lane="faceless_video",
        subtitle_style="bold_center_keyword",
    )

    assert edl.validate_skeleton() == []
    assert edl.total_duration_sec() == pytest.approx(5.5)
    assert edl.subtitles[0].style == "bold_center_keyword"
    assert edl.unfilled_slots()[0].id == "slot_01"


def test_shared_editing_engine_fills_material_refs_without_knowing_source_type():
    edl = build_edl_from_segments(
        [
            {"id": "slot_01", "order": 1, "duration_sec": 2.0, "narration": "授权素材"},
            {"id": "slot_02", "order": 2, "duration_sec": 4.0, "narration": "AI 镜头"},
        ],
        lane="premium_human_video",
    )

    filled = fill_edl_clips(
        edl,
        [
            {"slot_id": "slot_01", "shot_id": "stock_clip_01", "source_in_sec": 0.5, "source_out_sec": 2.5},
            {"slot_id": "slot_02", "shot_id": "seedance_shot_02"},
        ],
    )
    summary = edl_handoff_summary(filled)

    assert [clip.shot_id for clip in filled.clips] == ["stock_clip_01", "seedance_shot_02"]
    assert summary["ready_for_render"] is True
    assert summary["clip_count"] == 2
    assert summary["unfilled_slots"] == []


# ---------------------------------------------------------------- 项目存储


def test_project_store_roundtrip(tmp_path):
    store = ProjectStore(tmp_path)
    proj = make_demo_project("proj-rt")
    pdir = store.create(proj)
    for sub in ("frames", "videos", "audio", "final"):
        assert (pdir / sub).is_dir()
    loaded = store.load("proj-rt")
    assert loaded.model_dump() == proj.model_dump()
    assert store.list_projects() == ["proj-rt"]


def test_project_store_rejects_duplicate_create(tmp_path):
    store = ProjectStore(tmp_path)
    store.create(make_demo_project("dup"))
    with pytest.raises(FileExistsError):
        store.create(make_demo_project("dup"))


def test_script_roundtrip(tmp_path):
    store = ProjectStore(tmp_path)
    store.create(make_demo_project("scripted"))
    store.save_script("scripted", "# 剧本\n第一场……")
    assert store.load_script("scripted").startswith("# 剧本")
    assert store.load_script("scripted-none") is None if not store.exists("scripted-none") else True


# ---------------------------------------------------------------- 成本估算


def test_estimate_video_tiers_differ():
    cheap = estimate_video(5.0, ModelTier.AUDITION)
    expensive = estimate_video(5.0, ModelTier.FINAL)
    assert cheap.amount < expensive.amount


def test_production_phase_estimate_breakdown():
    est = estimate_production_phase([3.0, 4.5, 2.5], audition_ratio=1.0, audition_takes=2)
    assert est.amount > 0
    assert len(est.breakdown) == 2
    assert "合计" in est.describe()


def test_default_budget_lines_split():
    lines = default_budget_lines(100.0)
    assert dict(lines) == {"shots": 70.0, "retry_reserve": 20.0, "flex": 10.0}


# ---------------------------------------------------------------- 预算与成本门


def _gate_req(amount: float) -> GateRequest:
    est = estimate_video(5.0 * amount / 3.5, ModelTier.FINAL)
    return GateRequest(project_id="p", action="test", estimate=est)


def test_budget_spent_and_remaining():
    b = Budget(total=10.0, approved=True)
    b.records.append(SpendRecord(amount=3.0, what="shot-1"))
    assert b.spent == pytest.approx(3.0)
    assert b.remaining == pytest.approx(7.0)


def test_budget_gate_auto_approves_within_budget():
    b = Budget(total=100.0, approved=True)
    gate = BudgetCostGate(b)
    decision = asyncio.run(gate.request(_gate_req(3.5)))
    assert decision.approved and decision.reason == "within_budget"


def test_budget_gate_rejects_unapproved_budget():
    gate = BudgetCostGate(Budget(total=100.0, approved=False))
    decision = asyncio.run(gate.request(_gate_req(3.5)))
    assert not decision.approved
    assert decision.reason == "budget_not_approved"


def test_budget_gate_escalates_over_budget():
    async def escalate(req):
        return GateDecision(approved=True, reason="human_ok", approved_amount=req.estimate.amount)

    b = Budget(total=1.0, approved=True)
    gate = BudgetCostGate(b, escalate=escalate)
    decision = asyncio.run(gate.request(_gate_req(3.5)))
    assert decision.approved and decision.reason == "human_ok"


# ---------------------------------------------------------------- harness 本体


def test_mock_adapter_video_lifecycle():
    async def run():
        adapter = MockAdapter(polls_until_done=2)
        handle = await adapter.submit_video_task("测试镜头", tier=ModelTier.AUDITION)
        first = await adapter.query_video_task(handle.task_id)
        second = await adapter.query_video_task(handle.task_id)
        return handle, first, second, adapter

    handle, first, second, adapter = asyncio.run(run())
    assert first.status.value == "running"
    assert second.status.value == "succeeded"
    assert second.video_url.endswith(".mp4")
    assert adapter.submitted[0]["tier"] == ModelTier.AUDITION


def test_mock_adapter_failure_path():
    async def run():
        adapter = MockAdapter(fail_task_ids={"mock-task-1"})
        handle = await adapter.submit_video_task("会失败的镜头")
        return await adapter.query_video_task(handle.task_id)

    result = asyncio.run(run())
    assert result.status.value == "failed"


def test_scripted_gate_plays_decisions_in_order():
    async def run():
        gate = ScriptedGate([GateDecision(approved=False, reason="deny_first")])
        d1 = await gate.request(_gate_req(3.5))
        d2 = await gate.request(_gate_req(3.5))
        return d1, d2, gate

    d1, d2, gate = asyncio.run(run())
    assert not d1.approved and d1.reason == "deny_first"
    assert d2.approved and d2.reason == "scripted_default"
    assert len(gate.requests) == 2


def test_auto_approve_gate():
    decision = asyncio.run(AutoApproveGate().request(_gate_req(3.5)))
    assert decision.approved
