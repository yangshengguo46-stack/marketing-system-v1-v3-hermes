"""画布（黑板）数据协议 —— ADR v2 决策 3。

所有子 Agent 只通过画布通信。本文件是产品协议，改动需 bump SCHEMA_VERSION
并在台账记录迁移说明。

依赖图规则：
- Shot.asset_refs  记录镜头引用的 asset id（角色/场景/道具参考图）
- ClipEntry.shot_id 记录 EDL 条目引用的 shot
- 由此支持 Project.affected_shots(asset_id) 级联计算（改一张资产图要重投哪些镜头）

版本化规则：
- v0 = 动态样片（animatic 草稿），v1/v2/... = 成片迭代
- 每个版本保留当时的 EDL 快照与 shot 版本号，可回退
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field

SCHEMA_VERSION = 1


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------- 资产


class AssetKind(str, Enum):
    CHARACTER = "character"  # 角色（三视图）
    SCENE = "scene"          # 场景
    PROP = "prop"            # 道具
    STORYBOARD = "storyboard"  # 分镜图
    AUDIO_REF = "audio_ref"  # 音频参考（Seedance 参考资产可含音频）


class Asset(BaseModel):
    """资产库条目。美术 Agent 独写，摄影 Agent 只读。"""

    id: str
    kind: AssetKind
    name: str = ""
    prompt: str = ""                  # 生成该资产的完整提示词（复现用）
    file_path: str = ""               # 相对项目目录路径，如 frames/char_hero_front.png
    candidates: list[str] = Field(default_factory=list)  # best-of-k 落选文件（可清理）
    seed: Optional[int] = None
    version: int = 1
    created_at: str = Field(default_factory=_now)


class StyleLock(BaseModel):
    """全局风格锁。Phase 1 结束后冻结，Phase 2 只读。"""

    palette: str = ""                 # 色调描述
    art_style: str = ""               # 画风描述词模板（拼进所有生成 prompt）
    global_seed: Optional[int] = None
    reference_asset_ids: list[str] = Field(default_factory=list)
    locked: bool = False


# ---------------------------------------------------------------- 镜头


class ShotStatus(str, Enum):
    PLANNED = "planned"            # 分镜已定，未生成
    DRAFT = "draft"                # 样片占位（分镜图 + Ken Burns）
    AUDITION = "audition"          # 替身试拍中（fast/lite）
    SUBMITTED = "submitted"        # 正片任务已提交（Seedance 异步）
    GENERATED = "generated"        # 正片已生成，待质检
    QC_FAILED = "qc_failed"        # 盲评/场记不合格，待重投（需制片人批额）
    ACCEPTED = "accepted"          # 质检通过
    ABANDONED = "abandoned"        # 制片人叫停，用替代方案


class GenerationMode(str, Enum):
    """Seedance 同一 API 的 content 组合四模式（ADR v2 决策 1）。"""

    TEXT = "text"                      # 纯文生视频
    FIRST_FRAME = "first_frame"        # 图生视频（首帧）
    REFERENCE_IMAGES = "reference_images"  # 参考图生视频（资产库参考）
    REFERENCE_VIDEO = "reference_video"    # 参考视频生视频


class Shot(BaseModel):
    """镜头。摄影 Agent 写，场记 Agent 读评，剪辑师引用。"""

    id: str
    scene_id: str
    slot_id: str = ""                 # 绑定的时间线槽位（edl.TimelineSlot.id）
    storyboard_asset_id: str = ""     # 分镜图资产 id
    asset_refs: list[str] = Field(default_factory=list)  # 依赖图：引用的资产 id
    mode: GenerationMode = GenerationMode.FIRST_FRAME
    camera_prompt: str = ""           # 运镜描述
    full_prompt: str = ""             # 实际提交的完整 prompt（复现用）
    task_id: str = ""                 # Seedance 异步任务 id（崩溃恢复关键）
    status: ShotStatus = ShotStatus.PLANNED
    file_path: str = ""               # videos/shot_xxx_v2.mp4
    duration_sec: float = 0.0
    qc_score: Optional[float] = None          # 盲评分
    continuity_notes: list[str] = Field(default_factory=list)  # 场记记录
    retry_count: int = 0
    version: int = 0                  # 0 = 样片占位
    updated_at: str = Field(default_factory=_now)


class Scene(BaseModel):
    id: str
    summary: str = ""
    shots: list[Shot] = Field(default_factory=list)


# ---------------------------------------------------------------- 音轨


class TrackClip(BaseModel):
    """音轨片段：配音 / 音效 / BGM 统一结构。"""

    id: str
    kind: Literal["voice", "sfx", "bgm"]
    file_path: str = ""
    text: str = ""                    # voice: 台词原文
    start_sec: float = 0.0            # 相对成片时间轴
    duration_sec: float = 0.0
    volume: float = 1.0
    volume_curve: list[tuple[float, float]] = Field(default_factory=list)  # (时刻, 音量) ducking


class Tracks(BaseModel):
    voice: list[TrackClip] = Field(default_factory=list)
    sfx: list[TrackClip] = Field(default_factory=list)
    bgm: list[TrackClip] = Field(default_factory=list)


# ---------------------------------------------------------------- 预算（制片人独写）


class BudgetLine(BaseModel):
    label: str                        # e.g. "shots" / "retry_reserve" / "flex"
    allocated: float
    spent: float = 0.0


class SpendRecord(BaseModel):
    at: str = Field(default_factory=_now)
    amount: float
    what: str                         # e.g. "seedance shot_03 audition"
    shot_id: str = ""


class Budget(BaseModel):
    """预算案。制片人 Agent 独写（ADR v2 倒置 C：70/20/10）。"""

    currency: str = "CNY"
    total: float = 0.0
    lines: list[BudgetLine] = Field(default_factory=list)
    records: list[SpendRecord] = Field(default_factory=list)
    approved: bool = False            # Phase 1 一次审批时置位

    @property
    def spent(self) -> float:
        return sum(r.amount for r in self.records)

    @property
    def remaining(self) -> float:
        return self.total - self.spent


# ---------------------------------------------------------------- 版本快照


class VersionSnapshot(BaseModel):
    """成片版本：v0 样片，v1+ 成片。保留 EDL 快照与各 shot 版本，可回退。"""

    version: int
    kind: Literal["animatic", "final"]
    edl_snapshot: dict = Field(default_factory=dict)   # edl.EDL.model_dump()
    shot_versions: dict[str, int] = Field(default_factory=dict)  # shot_id -> version
    output_path: str = ""             # final/v1.mp4
    user_feedback: str = ""           # 该版本收到的自然语言反馈
    created_at: str = Field(default_factory=_now)


# ---------------------------------------------------------------- 项目根


class ProjectPhase(str, Enum):
    SCRIPTING = "scripting"          # 剧本/资产/分镜/骨架
    ANIMATIC = "animatic"            # 样片粗合成
    AWAITING_APPROVAL = "awaiting_approval"  # 等待唯一一次重审批（草稿+预算）
    PRODUCTION = "production"        # Phase 2 正片生成
    POST = "post"                    # 质检/剪辑/渲染
    DELIVERED = "delivered"          # 已交付，等待反馈
    REVISING = "revising"            # 反馈修改中


class Project(BaseModel):
    """画布根对象。导演 Agent 只看它决定下一步（黑板模式）。"""

    schema_version: int = SCHEMA_VERSION
    id: str
    brief: str = ""                   # 用户一句话需求原文
    phase: ProjectPhase = ProjectPhase.SCRIPTING
    style_lock: StyleLock = Field(default_factory=StyleLock)
    script: str = ""                  # 结构化剧本（markdown），大文本另存 script.md，此处为摘要
    assets: list[Asset] = Field(default_factory=list)
    scenes: list[Scene] = Field(default_factory=list)
    tracks: Tracks = Field(default_factory=Tracks)
    timeline: dict = Field(default_factory=dict)       # edl.EDL.model_dump()（避免循环 import）
    budget: Budget = Field(default_factory=Budget)
    versions: list[VersionSnapshot] = Field(default_factory=list)
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)

    # ---- 依赖图查询（已写实，有测试） ----

    def all_shots(self) -> list[Shot]:
        return [s for sc in self.scenes for s in sc.shots]

    def get_shot(self, shot_id: str) -> Optional[Shot]:
        for s in self.all_shots():
            if s.id == shot_id:
                return s
        return None

    def get_asset(self, asset_id: str) -> Optional[Asset]:
        for a in self.assets:
            if a.id == asset_id:
                return a
        return None

    def affected_shots(self, asset_id: str) -> list[Shot]:
        """级联计算：某资产变更后需要重投的镜头（反馈闭环第三级）。"""
        return [s for s in self.all_shots() if asset_id in s.asset_refs]

    def pending_task_shots(self) -> list[Shot]:
        """崩溃恢复：重启后需继续轮询的镜头。"""
        return [
            s for s in self.all_shots()
            if s.status in (ShotStatus.SUBMITTED, ShotStatus.AUDITION) and s.task_id
        ]

    def latest_version(self) -> Optional[VersionSnapshot]:
        return max(self.versions, key=lambda v: v.version) if self.versions else None
