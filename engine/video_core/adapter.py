"""VideoModelAdapter 基类 + VolcengineAdapter —— ADR v2 决策 8。

✅ 真实字段校准完成（2026-07-11，真实 ARK Key 实测，记录见台账 VIDEO-03）：
- 图片：POST /images/generations，size 下限 1920x1920（≥3,686,400 像素），
  响应 data[].url（24h 有效）+ usage.output_tokens（按 token 计价）
- 视频提交：POST /contents/generations/tasks，content 数组；text 项支持
  `--resolution 720p --duration 4` 后缀参数（响应回显）；首帧用
  {"type":"image_url","image_url":{"url":...},"role":"first_frame"}；响应仅 {id}
- 视频轮询：GET /contents/generations/tasks/{id}，status 小写
  （running/succeeded/...），成功后 content.video_url + usage.completion_tokens
  + seed/resolution/duration/framespersecond；fast 档 4s/720p 实测约 108s
- 取消：DELETE /contents/generations/tasks/{id}，running 任务返回 409
  InvalidAction.RunningTaskDeletion（按安全 no-op 处理）
- 模型 ID：seedream-5-0-260128 / seedance-2-0-260128（正片）/
  seedance-2-0-fast-260128（替身）
- ⚠️ reference 角色名（多参考图/视频/音频）未实测，按 role="reference_image"
  等推断实现，首次真实使用参考模式时需验证

设计约束：只用 httpx（async）；禁止 import agent_core / marketing_tools；
API Key 由调用方传入，不落盘不打日志；429/5xx 指数退避重试上限 3 次。
"""

from __future__ import annotations

import asyncio
import base64
import mimetypes
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import httpx

DEFAULT_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
DEFAULT_IMAGE_MODEL = "doubao-seedream-5-0-260128"
DEFAULT_VIDEO_MODELS = {
    "final": "doubao-seedance-2-0-260128",
    "audition": "doubao-seedance-2-0-fast-260128",
}
MIN_IMAGE_SIZE = "1920x1920"   # Seedream 5.0 实测下限：≥3,686,400 像素


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


def _file_to_data_uri(path: str) -> str:
    """本地文件 → base64 data URI；http(s)/data URL 直接透传。"""
    if path.startswith(("http://", "https://", "data:")):
        return path
    mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
    payload = base64.b64encode(Path(path).read_bytes()).decode()
    return f"data:{mime};base64,{payload}"


def _media_item(path: str, role: str, kind: str = "image_url") -> dict:
    return {"type": kind, kind: {"url": _file_to_data_uri(path)}, "role": role}


class VolcengineAdapter(VideoModelAdapter):
    """火山方舟实现（Seedream 5.0 + Seedance 2.0）。字段已真实校准（见模块 docstring）。"""

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        *,
        image_model: str = DEFAULT_IMAGE_MODEL,
        video_models: Optional[dict[str, str]] = None,
        timeout_sec: float = 60.0,
        max_retries: int = 3,
        transport: Optional[httpx.AsyncBaseTransport] = None,   # 测试注入 MockTransport
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._image_model = image_model
        self._video_models = video_models or dict(DEFAULT_VIDEO_MODELS)
        self._timeout = timeout_sec
        self._max_retries = max_retries
        self._transport = transport

    # ------------------------------------------------------------ http 底座

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url,
            headers={"Authorization": f"Bearer {self._api_key}"},
            timeout=self._timeout,
            transport=self._transport,
        )

    async def _request(self, method: str, path: str, json_body: Optional[dict] = None) -> dict:
        """带重试的请求：429/5xx 指数退避（上限 max_retries），其余错误直抛。"""
        last_error: Optional[Exception] = None
        async with self._client() as client:
            for attempt in range(self._max_retries + 1):
                try:
                    resp = await client.request(method, path, json=json_body)
                except httpx.HTTPError as exc:
                    last_error = AdapterError(f"network error: {exc}")
                else:
                    if resp.status_code < 400:
                        return resp.json() if resp.content else {}
                    body: dict[str, Any] = {}
                    try:
                        body = resp.json()
                    except ValueError:
                        pass
                    message = body.get("error", {}).get("message", resp.text[:200])
                    code = body.get("error", {}).get("code", "")
                    if resp.status_code == 429:
                        last_error = QuotaError(message)
                    elif resp.status_code >= 500:
                        last_error = AdapterError(f"server error {resp.status_code}: {message}")
                    else:
                        # 4xx（除 429）不重试：参数错误重试无意义
                        raise AdapterError(f"request failed {resp.status_code} {code}: {message}")
                if attempt < self._max_retries:
                    await asyncio.sleep(min(2.0 ** attempt, 8.0))
        assert last_error is not None
        raise last_error

    # ------------------------------------------------------------ 图片

    async def generate_image(self, prompt, *, size=MIN_IMAGE_SIZE, seed=None, n=1):
        body: dict[str, Any] = {
            "model": self._image_model,
            "prompt": prompt,
            "size": size,
            "n": n,
            "response_format": "url",
        }
        if seed is not None:
            body["seed"] = seed
        data = await self._request("POST", "/images/generations", body)
        results: list[ImageResult] = []
        async with self._client() as client:
            for item in data.get("data", []):
                resp = await client.get(item["url"])
                resp.raise_for_status()
                mime = resp.headers.get("content-type", "image/jpeg").split(";")[0]
                results.append(ImageResult(
                    file_bytes=resp.content,
                    mime=mime,
                    seed=seed,
                    raw={"url": item["url"], "usage": data.get("usage", {})},
                ))
        return results

    # ------------------------------------------------------------ 视频

    def _build_content(
        self,
        prompt: str,
        first_frame_path: Optional[str],
        references: Optional[ReferenceAssets],
        duration_sec: float,
        resolution: str,
    ) -> list[dict]:
        # 分辨率/时长走 prompt 后缀参数（实测有效，响应回显）
        text = f"{prompt} --resolution {resolution} --duration {max(1, round(duration_sec))}"
        content: list[dict] = [{"type": "text", "text": text}]
        if first_frame_path:
            content.append(_media_item(first_frame_path, "first_frame"))
        if references is not None:
            references.validate()
            # ⚠️ reference 角色名未实测（校准只验了 first_frame），首用时需验证
            for p in references.image_paths:
                content.append(_media_item(p, "reference_image"))
            for p in references.video_paths:
                content.append(_media_item(p, "reference_video", kind="video_url"))
            for p in references.audio_paths:
                content.append(_media_item(p, "reference_audio", kind="audio_url"))
        return content

    async def submit_video_task(
        self, prompt, *, tier=ModelTier.FINAL, first_frame_path=None,
        references=None, duration_sec=5.0, resolution="1080p", seed=None,
    ):
        body: dict[str, Any] = {
            "model": self._video_models[tier.value],
            "content": self._build_content(prompt, first_frame_path, references, duration_sec, resolution),
        }
        if seed is not None:
            body["seed"] = seed
        data = await self._request("POST", "/contents/generations/tasks", body)
        return VideoTaskHandle(task_id=data["id"], tier=tier, raw=data)

    _STATUS_MAP = {
        "queued": VideoTaskStatus.QUEUED,
        "running": VideoTaskStatus.RUNNING,
        "succeeded": VideoTaskStatus.SUCCEEDED,
        "failed": VideoTaskStatus.FAILED,
        "cancelled": VideoTaskStatus.FAILED,
        "expired": VideoTaskStatus.EXPIRED,
    }

    async def query_video_task(self, task_id):
        data = await self._request("GET", f"/contents/generations/tasks/{task_id}")
        status = self._STATUS_MAP.get(data.get("status", ""), VideoTaskStatus.RUNNING)
        raw = {k: v for k, v in data.items() if k != "content"}
        error = data.get("error") or {}
        return VideoTaskResult(
            status=status,
            video_url=(data.get("content") or {}).get("video_url", "") if status == VideoTaskStatus.SUCCEEDED else "",
            duration_sec=float(data.get("duration", 0) or 0),
            error_message=error.get("message", "") if isinstance(error, dict) else str(error),
            raw=raw,
        )

    async def cancel_video_task(self, task_id):
        """DELETE 任务。running 任务返回 409（实测），404/409 按安全 no-op。"""
        try:
            await self._request("DELETE", f"/contents/generations/tasks/{task_id}")
        except AdapterError as exc:
            text = str(exc)
            if "409" in text or "404" in text or "RunningTaskDeletion" in text:
                return
            raise
