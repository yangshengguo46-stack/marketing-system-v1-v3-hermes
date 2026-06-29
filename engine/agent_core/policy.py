"""Deterministic capability policy evaluated before any tool dispatch."""

from dataclasses import dataclass

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


DEFAULT_CAPABILITIES = (
    CapabilitySpec("marketing.read.trends", CapabilityLevel.READ_ONLY, "读取热点与证据"),
    CapabilitySpec("marketing.read.accounts", CapabilityLevel.READ_ONLY, "读取脱敏账号状态"),
    CapabilitySpec("marketing.draft.create", CapabilityLevel.REVERSIBLE_WRITE, "创建可撤销草稿"),
    CapabilitySpec("marketing.task.create", CapabilityLevel.REVERSIBLE_WRITE, "创建可撤销任务"),
    CapabilitySpec("marketing.session.login", CapabilityLevel.CONTROLLED_RESOURCE, "打开平台登录会话"),
    CapabilitySpec("marketing.model.paid", CapabilityLevel.CONTROLLED_RESOURCE, "调用有费用的模型"),
    CapabilitySpec("marketing.effect.publish", CapabilityLevel.EXTERNAL_EFFECT, "正式发布内容"),
    CapabilitySpec("marketing.effect.delete", CapabilityLevel.EXTERNAL_EFFECT, "删除外部内容"),
    CapabilitySpec("marketing.effect.send", CapabilityLevel.EXTERNAL_EFFECT, "向外部收件人发送消息"),
    CapabilitySpec("system.shell", CapabilityLevel.SYSTEM_FORBIDDEN, "任意系统命令"),
    CapabilitySpec("system.cookies.raw", CapabilityLevel.SYSTEM_FORBIDDEN, "读取原始 Cookie"),
    CapabilitySpec("system.permissions.modify", CapabilityLevel.SYSTEM_FORBIDDEN, "修改 Agent 自身权限"),
)


class CapabilityPolicy:
    def __init__(self, capabilities=DEFAULT_CAPABILITIES):
        self._capabilities = {item.name: item for item in capabilities}

    def evaluate(self, capability: str) -> PolicyDecision:
        spec = self._capabilities.get(capability)
        if spec is None:
            return PolicyDecision(
                allowed=False,
                approval_required=False,
                level=CapabilityLevel.SYSTEM_FORBIDDEN,
                reason="能力未注册，默认拒绝",
            )
        if spec.level is CapabilityLevel.SYSTEM_FORBIDDEN:
            return PolicyDecision(False, False, spec.level, "桌面 Agent 永久禁止该系统能力")
        if spec.level is CapabilityLevel.EXTERNAL_EFFECT:
            return PolicyDecision(True, True, spec.level, "外部副作用每次都需要用户确认")
        if spec.level is CapabilityLevel.CONTROLLED_RESOURCE:
            return PolicyDecision(True, True, spec.level, "受控资源需要按范围授权")
        return PolicyDecision(True, False, spec.level, "允许执行")

