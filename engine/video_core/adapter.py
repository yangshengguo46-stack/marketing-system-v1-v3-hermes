"""VideoModelAdapter 基类 + VolcengineAdapter —— ADR v2 决策 8。

⚠️ 实现前置条件（台账 VIDEO-03）：07 调研中的请求体字段为**推断**，
动手实现 VolcengineAdapter 前必须用真实 ARK API Key 打一次请求校准字段，
校准记录写进台账。

设计约束（填代码的模型必读）：
- 只用 httpx（async），禁止引入 openai SDK / LangChain 等
- 禁止 import agent_core / marketing_tools（架构回归测试会拦）
- API Key 由调用方传入（宿主从 secret store 读取），本模块不落盘不打日志
- 所有方法幂等可重试；网络错误抛 AdapterError 子类，不吞异常
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AdapterError(Exception):
    """适配器错误基类。"""


class TaskFailedError(AdapterError):
    """远端任务失败（含 expired）。"""


class QuotaError(AdapterError):
    """限流 / 余额不足，可退避重试或升级制片人。"""


class ModelTier(str, Enum):
    """替身/正片双档位（ADR v2 倒置 C）。"""

    AUDITION = "audition"   # 便宜快速档（seedance fast/lite）：试拍选构图
    FINAL = "final"         # 正片档（seedance 2.0）


class VideoTaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    EXPIRED = "expired"


@dataclass
class ImageResult:
    file_bytes: bytes
    mime: str = "image/png"
    seed: Optional[int] = None
    raw: dict = field(default_factory=dict)   # 原始响应（调试用，脱敏后）


@dataclass
class VideoTaskHandle:
    task_id: str
    tier: ModelTier
    raw: dict = field(default_factory=dict)


@dataclass
class VideoTaskResult:
    status: VideoTaskStatus
    video_url: str = ""          # succeeded 时有效；由调用方下载落盘
    duration_sec: float = 0.0
    error_message: str = ""
    raw: dict = field(default_factory=dict)


@dataclass
class ReferenceAssets:
    """Seedance 2.0 参考资产：最多 9 图 + 3 视频 + 3 音频（跨镜头一致性核心）。"""

    image_paths: list[str] = field(default_factory=list)
    video_paths: list[str] = field(default_factory=list)
    audio_paths: list[str] = field(default_factory=list)

    def validate(self) -> None:
        if len(self.image_paths) > 9:
            raise ValueError("参考图最多 9 张")
        if len(self.video_paths) > 3:
            raise ValueError("参考视频最多 3 个")
        if len(self.audio_paths) > 3:
            raise ValueError("参考音频最多 3 个")


class VideoModelAdapter(ABC):
    """视频/图片生成模型的通用适配接口。火山为首个实现，不锁死单模型。"""

    # ---- 图片（同步，Seedream） ----

    @abstractmethod
    async def generate_image(
        self,
        prompt: str,
        *,
        size: str = "1024x1024",
        seed: Optional[int] = None,
        n: int = 1,
    ) -> list[ImageResult]:
        """同步文生图。n>1 用于 best-of-k。"""

    # ---- 视频（异步任务，Seedance） ----

    @abstractmethod
    async def submit_video_task(
        self,
        prompt: str,
        *,
        tier: ModelTier = ModelTier.FINAL,
        first_frame_path: Optional[str] = None,       # 图生视频
        references: Optional[ReferenceAssets] = None,  # 参考图/视频生视频
        duration_sec: float = 5.0,
        resolution: str = "1080p",
        seed: Optional[int] = None,
    ) -> VideoTaskHandle:
        """提交异步视频任务，立即返回 handle。四种生成模式由参数组合表达：
        纯 prompt = 文生；+first_frame = 图生；+references = 参考生成。
        """

    @abstractmethod
    async def query_video_task(self, task_id: str) -> VideoTaskResult:
        """轮询任务状态。QUEUED/RUNNING 表示继续等；FAILED/EXPIRED 抛 TaskFailedError
        由 poller 统一处理为 shot.status=qc_failed 路径。
        """

    @abstractmethod
    async def cancel_video_task(self, task_id: str) -> None:
        """取消任务（用户取消 / 制片人叫停）。远端不支持时应为安全 no-op。"""


class VolcengineAdapter(VideoModelAdapter):
    """火山方舟实现（Seedream 5.0 + Seedance 2.0）。

    TODO(填代码)：
    1. 先用真实 ARK API Key 校准请求体字段（07 调研第八节为推断），记录进台账 VIDEO-03。
    2. 鉴权：Bearer ARK_API_KEY；base_url 形如 https://ark.cn-beijing.volces.com/api/v3
    3. generate_image → POST /images/generations（OpenAI 兼容形状，但走 httpx）
    4. submit_video_task → POST /contents/generations/tasks，content 数组按模式拼装：
       [{"type":"text","text":prompt}] + 首帧/参考图（image_url，本地文件转 base64 data URI）
       tier=AUDITION 时切换 model 字段到 fast/lite 型号（型号名待校准）
    5. query_video_task → GET /contents/generations/tasks/{id}
    6. 重试策略：429/5xx 指数退避（上限 3 次）；QuotaError 直接上抛给制片人
    7. 超时：单请求 60s；任务整体超时由 poller 管，adapter 不管
    """

    def __init__(self, api_key: str, base_url: str, *, timeout_sec: float = 60.0) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_sec

    async def generate_image(self, prompt, *, size="1024x1024", seed=None, n=1):
        raise NotImplementedError("TODO: VIDEO-03，先完成真实字段校准")

    async def submit_video_task(
        self, prompt, *, tier=ModelTier.FINAL, first_frame_path=None,
        references=None, duration_sec=5.0, resolution="1080p", seed=None,
    ):
        raise NotImplementedError("TODO: VIDEO-03，先完成真实字段校准")

    async def query_video_task(self, task_id):
        raise NotImplementedError("TODO: VIDEO-03，先完成真实字段校准")

    async def cancel_video_task(self, task_id):
        raise NotImplementedError("TODO: VIDEO-03，先完成真实字段校准")
