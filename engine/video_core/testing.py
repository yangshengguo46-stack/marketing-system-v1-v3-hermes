"""离线测试 harness —— 填代码的模型用它自证，无需真实 API Key / FFmpeg。

三件套：
1. MockAdapter        确定性假模型（图=1x1 PNG，视频任务两次轮询后成功）
2. make_demo_project  标准三镜头 demo 画布（骨架+资产+镜头，覆盖依赖图）
3. ScriptedGate       按剧本放行/拒绝的成本门（测试审批路径）

用法约定（写测试必读）：
- 单元测试只用本模块，禁止真实网络调用
- 渲染器测试只测 build_*_command 纯函数输出，不实际跑 ffmpeg
- 真实 API / 真实渲染放 tests/integration/（跳过条件：无 ARK_API_KEY / 无 ffmpeg）
"""

from __future__ import annotations

import itertools
from typing import Optional

from engine.video_core.adapter import (
    ImageResult,
    ModelTier,
    ReferenceAssets,
    VideoModelAdapter,
    VideoTaskHandle,
    VideoTaskResult,
    VideoTaskStatus,
)
from engine.video_core.cost import estimate_production_phase
from engine.video_core.edl import EDL, TimelineSlot
from engine.video_core.hooks import CostGate, GateDecision, GateRequest
from engine.video_core.schema import (
    Asset,
    AssetKind,
    Budget,
    BudgetLine,
    GenerationMode,
    Project,
    Scene,
    Shot,
    ShotStatus,
    StyleLock,
)

# 最小合法 1x1 PNG（生成的假资产图字节）
TINY_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c626001000000ffff03000006000557bfabd40000000049454e44ae426082"
)


class MockAdapter(VideoModelAdapter):
    """确定性假模型。

    行为：
    - generate_image: 返回 n 张 TINY_PNG，seed 递增
    - submit_video_task: 返回递增 task_id（mock-task-1, -2, ...）
    - query_video_task: 每个任务前 polls_until_done-1 次返回 RUNNING，之后 SUCCEEDED
      （video_url 为 fake://，测试中由调用方决定如何落盘）
    - fail_task_ids 中的任务返回 FAILED（测试重试/叫停路径）
    """

    def __init__(self, *, polls_until_done: int = 2, fail_task_ids: Optional[set[str]] = None) -> None:
        self.polls_until_done = polls_until_done
        self.fail_task_ids = fail_task_ids or set()
        self.submitted: list[dict] = []          # 供断言：所有提交的参数
        self._task_counter = itertools.count(1)
        self._poll_counts: dict[str, int] = {}

    async def generate_image(self, prompt, *, size="1024x1024", seed=None, n=1):
        return [
            ImageResult(file_bytes=TINY_PNG, seed=(seed or 0) + i, raw={"prompt": prompt, "size": size})
            for i in range(n)
        ]

    async def submit_video_task(
        self, prompt, *, tier=ModelTier.FINAL, first_frame_path=None,
        references=None, duration_sec=5.0, resolution="1080p", seed=None,
    ):
        if references is not None:
            assert isinstance(references, ReferenceAssets)
            references.validate()
        task_id = f"mock-task-{next(self._task_counter)}"
        self.submitted.append({
            "task_id": task_id, "prompt": prompt, "tier": tier,
            "first_frame_path": first_frame_path, "references": references,
            "duration_sec": duration_sec, "resolution": resolution, "seed": seed,
        })
        return VideoTaskHandle(task_id=task_id, tier=tier)

    async def query_video_task(self, task_id):
        count = self._poll_counts.get(task_id, 0) + 1
        self._poll_counts[task_id] = count
        if task_id in self.fail_task_ids:
            return VideoTaskResult(status=VideoTaskStatus.FAILED, error_message="mock failure")
        if count < self.polls_until_done:
            return VideoTaskResult(status=VideoTaskStatus.RUNNING)
        return VideoTaskResult(
            status=VideoTaskStatus.SUCCEEDED,
            video_url=f"fake://{task_id}.mp4",
            duration_sec=5.0,
        )

    async def cancel_video_task(self, task_id):
        self.fail_task_ids.add(task_id)


class ScriptedGate(CostGate):
    """按剧本响应的成本门。decisions 依次弹出；耗尽后默认放行。"""

    def __init__(self, decisions: Optional[list[GateDecision]] = None) -> None:
        self.decisions = list(decisions or [])
        self.requests: list[GateRequest] = []    # 供断言

    async def request(self, req: GateRequest) -> GateDecision:
        self.requests.append(req)
        if self.decisions:
            return self.decisions.pop(0)
        return GateDecision(approved=True, reason="scripted_default", approved_amount=req.estimate.amount)


def make_demo_skeleton() -> EDL:
    """三槽位标准骨架（总时长 10s）。"""
    return EDL(
        slots=[
            TimelineSlot(id="slot-1", order=1, duration_sec=3.0, camera_direction="推近",
                         narration="开头钩子", scene_id="scene-1", beat_locked=True),
            TimelineSlot(id="slot-2", order=2, duration_sec=4.5, camera_direction="左→右横移",
                         narration="展开", scene_id="scene-1"),
            TimelineSlot(id="slot-3", order=3, duration_sec=2.5, camera_direction="静止",
                         narration="CTA", scene_id="scene-2"),
        ],
    )


def make_demo_project(project_id: str = "demo-proj") -> Project:
    """标准 demo 画布：1 角色资产 + 2 场景 3 镜头，覆盖依赖图与级联计算。

    依赖关系：shot-1/shot-2 引用 asset-hero（affected_shots 应返回这两个）。
    shot-2 处于 submitted 状态带 task_id（pending_task_shots 应返回它）。
    """
    skeleton = make_demo_skeleton()
    hero = Asset(id="asset-hero", kind=AssetKind.CHARACTER, name="主角",
                 prompt="主角三视图", file_path="frames/hero.png")
    shots1 = [
        Shot(id="shot-1", scene_id="scene-1", slot_id="slot-1",
             asset_refs=["asset-hero"], mode=GenerationMode.REFERENCE_IMAGES,
             status=ShotStatus.ACCEPTED, file_path="videos/shot-1_v1.mp4",
             duration_sec=3.0, version=1),
        Shot(id="shot-2", scene_id="scene-1", slot_id="slot-2",
             asset_refs=["asset-hero"], mode=GenerationMode.FIRST_FRAME,
             status=ShotStatus.SUBMITTED, task_id="mock-task-99"),
    ]
    shots2 = [
        Shot(id="shot-3", scene_id="scene-2", slot_id="slot-3",
             mode=GenerationMode.TEXT, status=ShotStatus.PLANNED),
    ]
    estimate = estimate_production_phase([s.duration_sec for s in skeleton.slots])
    budget = Budget(
        total=round(estimate.amount * 1.3, 2),
        lines=[BudgetLine(label=lbl, allocated=amt)
               for lbl, amt in [("shots", 7.0), ("retry_reserve", 2.0), ("flex", 1.0)]],
        approved=True,
    )
    return Project(
        id=project_id,
        brief="demo: 三镜头短片",
        style_lock=StyleLock(art_style="扁平插画风", locked=True),
        assets=[hero],
        scenes=[
            Scene(id="scene-1", summary="开场", shots=shots1),
            Scene(id="scene-2", summary="收尾", shots=shots2),
        ],
        timeline=skeleton.model_dump(),
        budget=budget,
    )
