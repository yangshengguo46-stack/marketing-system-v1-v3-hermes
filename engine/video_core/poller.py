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
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional

from engine.video_core.adapter import VideoModelAdapter, VideoTaskResult
from engine.video_core.project_store import ProjectStore


@dataclass
class PollJob:
    project_id: str
    shot_id: str
    task_id: str


# 回调签名：任务终态（成功或失败）时调用
DoneCallback = Callable[[PollJob, VideoTaskResult], Awaitable[None]]


class TaskPoller:
    """共享轮询器。

    TODO(填代码)：
    1. start()/stop()：启动/停止主循环（asyncio.Task），stop 需优雅等待当前轮询完成
    2. add(job)：纳入轮询队列（去重：同 task_id 只轮一次）
    3. 主循环：并发查询所有 pending job（asyncio.gather，单批上限 10 并发），
       按 job 独立退避（10s → ×1.5 → 封顶 120s）
    4. 终态处理：
       - SUCCEEDED：下载 video_url 到 <project>/videos/{shot_id}_v{n}.mp4，
         更新 shot.file_path/status=generated/duration_sec，save 画布，调 on_done
       - FAILED/EXPIRED：shot.status=qc_failed + retry_count+1，save，调 on_done
    5. recover(store)：遍历 store.list_projects()，把 pending_task_shots() 全部 add
    6. 画布写入必须整读整写（load → 改 → save），Poller 是画布的合法写者之一
    """

    def __init__(
        self,
        adapter: VideoModelAdapter,
        store: ProjectStore,
        *,
        on_done: Optional[DoneCallback] = None,
        max_concurrency: int = 10,
    ) -> None:
        self._adapter = adapter
        self._store = store
        self._on_done = on_done
        self._max_concurrency = max_concurrency
        self._jobs: dict[str, PollJob] = {}          # task_id -> job
        self._loop_task: Optional[asyncio.Task] = None

    def add(self, job: PollJob) -> None:
        raise NotImplementedError("TODO: VIDEO-04")

    async def start(self) -> None:
        raise NotImplementedError("TODO: VIDEO-04")

    async def stop(self) -> None:
        raise NotImplementedError("TODO: VIDEO-04")

    async def recover(self) -> int:
        """扫描全部项目恢复 pending 任务，返回恢复数量。"""
        raise NotImplementedError("TODO: VIDEO-04")

    @property
    def pending_count(self) -> int:
        return len(self._jobs)
