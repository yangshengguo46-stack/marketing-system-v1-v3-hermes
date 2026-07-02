"""Deterministic capability policy evaluated before any tool dispatch.

Policy resolution order:
  1. Exact match in the capability table.
  2. Prefix match (namespace-based): marketing_read_* → L0, marketing_draft_* → L1, etc.
  3. Default deny.
"""

from dataclasses import dataclass, field

from .models import CapabilityLevel


@dataclass(frozen=True)
class CapabilitySpec:
    name: str
    level: CapabilityLevel
    description: str


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    approval_required: bool
    level: CapabilityLevel
    reason: str


# Exact-match entries override the prefix rules.
_EXPLICIT: dict[str, CapabilitySpec] = {}


# Prefix → (level, approval_required)
_PREFIX_RULES: list[tuple[str, CapabilityLevel, bool, str]] = [
    ("marketing_read_", CapabilityLevel.READ_ONLY, False, "只读认知 — 自动允许"),
    ("marketing_draft_", CapabilityLevel.REVERSIBLE_WRITE, False, "可逆业务写入 — 自动允许"),
    ("marketing_accounts_", CapabilityLevel.CONTROLLED_RESOURCE, True, "账号操作 — 受控资源，首次/按范围确认"),
    ("marketing_trending_", CapabilityLevel.CONTROLLED_RESOURCE, True, "趋势抓取 — 受控资源，按范围确认"),
    ("marketing_workflow_", CapabilityLevel.CONTROLLED_RESOURCE, True, "巡检编排 — 受控资源，首次确认"),
    ("marketing_effect_", CapabilityLevel.EXTERNAL_EFFECT, True, "外部副作用 — 每次明确确认"),
    ("marketing_session_", CapabilityLevel.CONTROLLED_RESOURCE, True, "会话操作 — 受控资源，按范围确认"),
    ("marketing_research_", CapabilityLevel.READ_ONLY, False, "只读研究 — 自动允许"),
    ("marketing_skill_", CapabilityLevel.CONTROLLED_RESOURCE, True, "技能治理 — 受控资源，首次确认"),
    ("system_", CapabilityLevel.SYSTEM_FORBIDDEN, False, "系统能力 — 桌面 Agent 永久禁止"),
]

# ── canonical capabilities kept for direct import by tests ────────────

DEFAULT_CAPABILITIES: tuple[CapabilitySpec, ...] = (
    CapabilitySpec("marketing_read_trends", CapabilityLevel.READ_ONLY, "读取热点与证据"),
    CapabilitySpec("marketing_read_accounts", CapabilityLevel.READ_ONLY, "读取脱敏账号状态"),
    CapabilitySpec("marketing_draft_create", CapabilityLevel.REVERSIBLE_WRITE, "创建可撤销草稿"),
    CapabilitySpec("marketing_task_create", CapabilityLevel.REVERSIBLE_WRITE, "创建可撤销任务"),
    CapabilitySpec("marketing_session_login", CapabilityLevel.CONTROLLED_RESOURCE, "打开平台登录会话"),
    CapabilitySpec("marketing_model_paid", CapabilityLevel.CONTROLLED_RESOURCE, "调用有费用的模型"),
    CapabilitySpec("marketing_effect_publish", CapabilityLevel.EXTERNAL_EFFECT, "正式发布内容"),
    CapabilitySpec("marketing_effect_delete", CapabilityLevel.EXTERNAL_EFFECT, "删除外部内容"),
    CapabilitySpec("marketing_effect_send", CapabilityLevel.EXTERNAL_EFFECT, "向外部收件人发送消息"),
    CapabilitySpec("system_shell", CapabilityLevel.SYSTEM_FORBIDDEN, "任意系统命令"),
    CapabilitySpec("system_cookies_raw", CapabilityLevel.SYSTEM_FORBIDDEN, "读取原始 Cookie"),
    CapabilitySpec("system_permissions_modify", CapabilityLevel.SYSTEM_FORBIDDEN, "修改 Agent 自身权限"),
)


_authorized_check = None


def set_authorization_checker(fn) -> None:
    global _authorized_check
    _authorized_check = fn


class CapabilityPolicy:
    def __init__(self, capabilities: tuple[CapabilitySpec, ...] = DEFAULT_CAPABILITIES):
        self._capabilities: dict[str, CapabilitySpec] = {item.name: item for item in capabilities}
        for entry in _EXPLICIT.values():
            self._capabilities[entry.name] = entry

    def evaluate(
        self, capability: str, user_id: str | None = None,
        arguments: dict | None = None,
    ) -> PolicyDecision:
        # 1. Exact match
        spec = self._capabilities.get(capability)
        if spec is not None:
            decision = self._decide(spec)
            return self._apply_authorization(decision, capability, user_id, arguments)

        # 2. Prefix match
        for prefix, level, approval_required, reason in _PREFIX_RULES:
            if capability.startswith(prefix):
                allowed = level is not CapabilityLevel.SYSTEM_FORBIDDEN
                decision = PolicyDecision(
                    allowed=allowed,
                    approval_required=approval_required,
                    level=level,
                    reason=reason,
                )
                return self._apply_authorization(decision, capability, user_id, arguments)

        # 3. Default deny
        return PolicyDecision(
            allowed=False,
            approval_required=False,
            level=CapabilityLevel.SYSTEM_FORBIDDEN,
            reason="能力未注册，默认拒绝",
        )

    @staticmethod
    def _apply_authorization(
        decision: PolicyDecision, capability: str, user_id: str | None,
        arguments: dict | None,
    ) -> PolicyDecision:
        if not decision.allowed or not decision.approval_required or not user_id or _authorized_check is None:
            return decision
        try:
            if _authorized_check(user_id, capability, arguments or {}):
                return PolicyDecision(
                    allowed=True, approval_required=False, level=decision.level,
                    reason="用户已按范围授权该能力 — 跳过审批",
                )
        except Exception:
            pass
        return decision

    @staticmethod
    def _decide(spec: CapabilitySpec) -> PolicyDecision:
        if spec.level is CapabilityLevel.SYSTEM_FORBIDDEN:
            return PolicyDecision(False, False, spec.level, "桌面 Agent 永久禁止该系统能力")
        if spec.level is CapabilityLevel.EXTERNAL_EFFECT:
            return PolicyDecision(True, True, spec.level, "外部副作用每次都需要用户确认")
        if spec.level is CapabilityLevel.CONTROLLED_RESOURCE:
            return PolicyDecision(True, True, spec.level, "受控资源需要按范围授权")
        return PolicyDecision(True, False, spec.level, "允许执行")
