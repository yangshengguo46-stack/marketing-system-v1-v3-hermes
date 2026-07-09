"""时间线骨架 + EDL 数据协议 —— ADR v2 倒置 A / 决策 4。

两阶段用法：
1. 剪辑师 Agent 最先产出 TimelineSlot 列表（空骨架，槽位带硬约束），
   摄影 Agent 按槽位规格生成镜头（"镜头填坑"）。
2. 镜头齐后剪辑师产出完整 EDL（ClipEntry/字幕/转场/音量曲线），
   渲染器 renderer.py 将 EDL 确定性转为 mp4。

EDL 是人类可读的剪辑方案（审批展示用），也是渲染器的唯一输入。
"""

from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


class Energy(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class TimelineSlot(BaseModel):
    """空时间线骨架的槽位。镜头带规格生成的硬约束来源。"""

    id: str
    order: int
    duration_sec: float                      # 硬约束：镜头必须匹配（渲染器可微裁）
    camera_direction: str = ""               # 运镜方向约束，如 "推近" / "左→右横移" / "静止"
    energy: Energy = Energy.MEDIUM
    mood: str = ""                            # 情绪标签
    beat_locked: bool = False                 # 是否卡在 BGM 节拍点（边界不可移）
    narration: str = ""                       # 该槽位配音台词（TTS 时长反推 duration 的依据）
    scene_id: str = ""                        # 归属场景
    shot_id: str = ""                         # 填坑后回填


class Transition(BaseModel):
    kind: Literal["cut", "fade", "dissolve", "wipe"] = "cut"
    duration_sec: float = 0.0


class SubtitleEntry(BaseModel):
    text: str
    start_sec: float
    end_sec: float
    style: str = "default"                    # 参数化样式名，渲染器持有样式表


class ClipEntry(BaseModel):
    """EDL 条目：一段进入成片的素材。"""

    slot_id: str
    shot_id: str                              # 依赖图：引用的镜头
    source_in_sec: float = 0.0                # 素材入点
    source_out_sec: float = 0.0               # 素材出点（0 = 到尾）
    transition_out: Transition = Field(default_factory=Transition)


class EDL(BaseModel):
    """完整剪辑决策表。渲染器唯一输入；审批节点上给用户看的就是它。"""

    version: int = 1
    fps: int = 30
    resolution: str = "1080x1920"             # 竖屏默认，横屏 "1920x1080"
    slots: list[TimelineSlot] = Field(default_factory=list)   # 骨架（Phase 1 产出）
    clips: list[ClipEntry] = Field(default_factory=list)      # 填坑结果（Phase 2 产出）
    subtitles: list[SubtitleEntry] = Field(default_factory=list)
    notes: str = ""                            # 剪辑师给人看的方案说明

    # ---- 校验/查询（已写实，有测试） ----

    def total_duration_sec(self) -> float:
        return sum(s.duration_sec for s in self.slots)

    def unfilled_slots(self) -> list[TimelineSlot]:
        filled = {c.slot_id for c in self.clips}
        return [s for s in self.slots if s.id not in filled]

    def validate_skeleton(self) -> list[str]:
        """骨架自检，返回问题列表（空 = 通过）。剪辑师 Agent 产出后必须调用。"""
        problems: list[str] = []
        orders = [s.order for s in self.slots]
        if len(orders) != len(set(orders)):
            problems.append("槽位 order 重复")
        ids = [s.id for s in self.slots]
        if len(ids) != len(set(ids)):
            problems.append("槽位 id 重复")
        for s in self.slots:
            if s.duration_sec <= 0:
                problems.append(f"槽位 {s.id} 时长非法: {s.duration_sec}")
        return problems
