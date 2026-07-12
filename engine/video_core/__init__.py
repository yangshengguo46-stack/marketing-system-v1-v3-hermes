"""video_core — 视频生产引擎（零业务依赖）。

架构边界（ADR v2 决策 7，tests/test_video_core_boundary.py 强制）：
- 本包及 video_agents 禁止 import agent_core / marketing_tools / backend / electron 相关模块。
- 审批与成本门只通过 hooks.CostGate 接口注入，引擎不感知宿主。

模块地图：
- schema.py         画布（黑板）数据协议 —— 产品协议，已写实
- edl.py            时间线骨架 + EDL 数据协议 —— 已写实
- project_store.py  项目目录布局 + 画布持久化 —— 已写实
- adapter.py        VideoModelAdapter 基类 + VolcengineAdapter（stub，待填）
- poller.py         TaskPoller 异步任务收割（stub，待填）
- editing_engine.py 共享剪辑引擎：脚本/素材/生成镜头 → EDL 合同
- renderer.py       EDL → mp4 确定性渲染器（stub，待填）
- cost.py           表驱动成本估算（价格表待真实数据校准）
- hooks.py          审批/成本门 hook 接口 + 独立模式默认实现
"""

from engine.video_core.schema import Project, SCHEMA_VERSION
from engine.video_core.editing_engine import (
    build_edl_from_segments,
    edl_handoff_summary,
    fill_edl_clips,
    shared_editing_contract,
)
from engine.video_core.high_end_preflight import preflight_high_end_video_project

__all__ = [
    "Project",
    "SCHEMA_VERSION",
    "build_edl_from_segments",
    "edl_handoff_summary",
    "fill_edl_clips",
    "shared_editing_contract",
    "preflight_high_end_video_project",
]
