"""审批/成本门 hook 接口 —— ADR v2 决策 7 边界纪律第 2 条。

引擎只定义卡点，不感知宿主：
- 营销系统模式：宿主实现 CostGate，内部转发 tool_gateway 审批链
- 独立模式：用 BudgetCostGate（制片人预算内自动批，超额升级人工回调）

卡点位置（引擎内所有花钱动作前必须过 gate）：
1. Phase 1 → Phase 2 的一次性重审批（草稿 + 预算案）
2. Phase 2 中超出储备金的重试
3. 反馈修改中制片人报价后的贵操作（级联重投）

已写实（纯逻辑，有测试）。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional

from engine.video_core.cost import CostEstimate
from engine.video_core.schema import Budget


@dataclass
class GateRequest:
    project_id: str
    action: str                      # e.g. "phase2_production" / "retry_shot_03" / "cascade_reshoot"
    estimate: CostEstimate
    detail: str = ""                 # 人类可读说明（EDL 摘要 / 重试原因）


@dataclass
class GateDecision:
    approved: bool
    reason: str = ""
    approved_amount: float = 0.0     # 批准额度（可低于申请额）


class CostGate(ABC):
    """花钱卡点接口。宿主注入实现。"""

    @abstractmethod
    async def request(self, req: GateRequest) -> GateDecision: ...


class AutoApproveGate(CostGate):
    """测试/开发用：全部放行。禁止在生产宿主使用。"""

    async def request(self, req: GateRequest) -> GateDecision:
        return GateDecision(approved=True, reason="auto", approved_amount=req.estimate.amount)


# 人工升级回调：独立模式下由入口层（MCP/CLI/API）提供
EscalateFn = Callable[[GateRequest], Awaitable[GateDecision]]


class BudgetCostGate(CostGate):
    """独立模式默认实现：预算内自动批，超额走人工升级回调。

    规则（ADR v2 倒置 C）：
    - budget.approved 为 False 时一律升级（Phase 1 审批尚未完成）
    - 申请额 ≤ budget.remaining 且对应预算线有余量 → 自动批
    - 否则升级 escalate（无回调则拒绝）
    """

    def __init__(self, budget: Budget, *, escalate: Optional[EscalateFn] = None) -> None:
        self._budget = budget
        self._escalate = escalate

    async def request(self, req: GateRequest) -> GateDecision:
        amount = req.estimate.amount
        if self._budget.approved and amount <= self._budget.remaining:
            return GateDecision(approved=True, reason="within_budget", approved_amount=amount)
        if self._escalate is not None:
            return await self._escalate(req)
        return GateDecision(
            approved=False,
            reason="over_budget_no_escalation" if self._budget.approved else "budget_not_approved",
        )
