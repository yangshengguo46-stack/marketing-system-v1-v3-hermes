"""TaskPoller —— 异步任务收割 + 崩溃恢复（ADR v2 决策 0 / 台账 VIDEO-04）。

并行模型：并行点在 API 任务层。摄影 Agent fan-out 批量提交后把 task_id
写进画布 shot.task_id，Poller 统一轮询收割（fan-in），Agent 不阻塞等待。

崩溃恢复：重启后宿主调用 recover(store)，扫描所有项目的
Project.pending_task_shots()，重新纳入轮询。

设计约束（填代码的模型必读）：
- 纯 asyncio，不开线程；单实例服务多项目
- 轮询间隔指数退避：10s 起，×1.5，封顶 120s（任务通常分钟级）
- 完成回调里做三件事：下载视频落盘 videos/、更新 shot 状态与画布、触发 on_done
- 禁止 import agent_core / marketing_tools
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable, Optional

from engine.video_core.adapter import (
    AdapterError,
    TaskFailedError,
    VideoModelAdapter,
    VideoTaskResult,
    VideoTaskStatus,
)
from engine.video_core.project_store import ProjectStore
from engine.video_core.schema import ShotStatus


@dataclass
class PollJob:
    project_id: str
    shot_id: str
    task_id: str
    interval_sec: float = 0.0        # 当前退避间隔（add 时置 base）
    next_poll_at: float = 0.0        # 单调时钟时刻，到点才轮询


# 回调签名：任务终态（成功或失败）时调用
DoneCallback = Callable[[PollJob, VideoTaskResult], Awaitable[None]]

# 下载器签名：(url, 目标路径)。默认 httpx 流式下载，测试注入假实现
DownloadFn = Callable[[str, Path], Awaitable[None]]


async def _default_download(url: str, dest: Path) -> None:
    import httpx  # 懒加载：离线测试环境可以不装 httpx

    async with httpx.AsyncClient(timeout=300.0, follow_redirects=True) as client:
        async with client.stream("GET", url) as resp:
            resp.raise_for_status()
            dest.parent.mkdir(parents=True, exist_ok=True)
            with open(dest, "wb") as f:
                async for chunk in resp.aiter_bytes(1 << 16):
                    f.write(chunk)


class TaskPoller:
    """共享轮询器（单实例服务多项目）。

    测试入口：不走 start()，直接调 poll_once()（确定性，无 sleep）。
    生产入口：start() 后台循环，stop() 优雅退出。
    """

    def __init__(
        self,
        adapter: VideoModelAdapter,
        store: ProjectStore,
        *,
        on_done: Optional[DoneCallback] = None,
        download: DownloadFn = _default_download,
        max_concurrency: int = 10,
        base_interval_sec: float = 10.0,
        backoff_factor: float = 1.5,
        max_interval_sec: float = 120.0,
        tick_sec: float = 1.0,
    ) -> None:
        self._adapter = adapter
        self._store = store
        self._on_done = on_done
        self._download = download
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._base_interval = base_interval_sec
        self._backoff_factor = backoff_factor
        self._max_interval = max_interval_sec
        self._tick = tick_sec
        self._jobs: dict[str, PollJob] = {}          # task_id -> job
        self._loop_task: Optional[asyncio.Task] = None
        self._stopping = asyncio.Event()

    # ---------------------------------------------------------- 队列管理

    def add(self, job: PollJob) -> None:
        """纳入轮询。同 task_id 去重；立即可轮（next_poll_at=现在）。"""
        if job.task_id in self._jobs:
            return
        job.interval_sec = self._base_interval
        job.next_poll_at = time.monotonic()
        self._jobs[job.task_id] = job

    async def recover(self) -> int:
        """崩溃恢复：扫描全部项目的 pending 镜头，重新纳入轮询。"""
        count = 0
        for project_id in self._store.list_projects():
            project = self._store.load(project_id)
            for shot in project.pending_task_shots():
                if shot.task_id not in self._jobs:
                    self.add(PollJob(project_id=project_id, shot_id=shot.id, task_id=shot.task_id))
                    count += 1
        return count

    @property
    def pending_count(self) -> int:
        return len(self._jobs)

    # ---------------------------------------------------------- 轮询核心

    async def poll_once(self) -> int:
        """轮询一批到期 job，返回本批进入终态的任务数。测试直接调用。"""
        now = time.monotonic()
        due = [j for j in list(self._jobs.values()) if j.next_poll_at <= now]
        if not due:
            return 0
        results = await asyncio.gather(*(self._poll_job(j) for j in due))
        return sum(results)

    async def _poll_job(self, job: PollJob) -> int:
        async with self._semaphore:
            try:
                result = await self._adapter.query_video_task(job.task_id)
            except TaskFailedError as exc:
                result = VideoTaskResult(
                    status=VideoTaskStatus.FAILED,
                    error_message=str(exc) or "remote video task failed",
                )
            except AdapterError:
                # 网络/限流错误：保留 job，退避后重试
                self._backoff(job)
                return 0
        if result.status in (VideoTaskStatus.QUEUED, VideoTaskStatus.RUNNING):
            self._backoff(job)
            return 0
        await self._finalize(job, result)
        return 1

    def _backoff(self, job: PollJob) -> None:
        job.next_poll_at = time.monotonic() + job.interval_sec
        job.interval_sec = min(job.interval_sec * self._backoff_factor, self._max_interval)

    async def _finalize(self, job: PollJob, result: VideoTaskResult) -> None:
        """终态处理：落盘 + 整读整写画布 + 回调。Poller 是画布合法写者之一。"""
        self._jobs.pop(job.task_id, None)
        project = self._store.load(job.project_id)
        shot = project.get_shot(job.shot_id)
        callback_result = result
        if shot is not None:
            if result.status == VideoTaskStatus.SUCCEEDED:
                version = shot.version + 1
                rel_path = f"videos/{shot.id}_v{version}.mp4"
                dest = self._store.project_dir(job.project_id) / rel_path
                try:
                    await self._download(result.video_url, dest)
                except Exception as exc:  # 下载失败按任务失败处理，可重试
                    shot.status = ShotStatus.QC_FAILED
                    shot.retry_count += 1
                    shot.task_id = ""
                    shot.continuity_notes.append(f"download failed: {exc}")
                    callback_result = VideoTaskResult(
                        status=VideoTaskStatus.FAILED,
                        error_message=f"download failed: {exc}",
                        raw=result.raw,
                    )
                else:
                    shot.version = version
                    shot.file_path = rel_path
                    shot.duration_sec = result.duration_sec or shot.duration_sec
                    shot.status = ShotStatus.GENERATED
                    shot.task_id = ""
            else:  # FAILED / EXPIRED
                shot.status = ShotStatus.QC_FAILED
                shot.retry_count += 1
                shot.task_id = ""
                if result.error_message:
                    shot.continuity_notes.append(f"task failed: {result.error_message}")
            self._store.save(project)
        if self._on_done is not None:
            await self._on_done(job, callback_result)

    # ---------------------------------------------------------- 生产循环

    async def start(self) -> None:
        if self._loop_task is not None:
            return
        self._stopping.clear()
        self._loop_task = asyncio.create_task(self._run(), name="video-task-poller")

    async def stop(self) -> None:
        """优雅停止：等当前轮询批次完成后退出。"""
        if self._loop_task is None:
            return
        self._stopping.set()
        await self._loop_task
        self._loop_task = None

    async def _run(self) -> None:
        while not self._stopping.is_set():
            await self.poll_once()
            try:
                await asyncio.wait_for(self._stopping.wait(), timeout=self._tick)
            except asyncio.TimeoutError:
                pass
