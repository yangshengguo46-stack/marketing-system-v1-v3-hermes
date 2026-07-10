"""Account DNA onboarding protocol.

This module is intentionally deterministic.  It does not try to replace the
model; it gives the model a product-owned operating rhythm for the first
conversation with a new creator, so onboarding does not degrade into a passive
questionnaire or a generic "please log in first" flow.
"""

from __future__ import annotations

import re
from typing import Any


ACCOUNT_ONBOARDING_VERSION = "account-dna-onboarding-v0.1"


def _text(params: dict[str, Any], *keys: str) -> str:
    parts: list[str] = []
    for key in keys:
        value = params.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())
        elif isinstance(value, list):
            parts.extend(str(item).strip() for item in value if str(item).strip())
    return " ".join(parts)


def _list(params: dict[str, Any], key: str) -> list[str]:
    value = params.get(key)
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [item.strip() for item in re.split(r"[、,，/;；\n]", value) if item.strip()]
    return []


def _safe_user_id(params: dict[str, Any]) -> str:
    user_id = str(params.get("__user_id") or params.get("user_id") or "default").strip() or "default"
    return re.sub(r"[^A-Za-z0-9_-]", "_", user_id)[:80] or "default"


def _resolve_account_id(params: dict[str, Any]) -> str:
    account_id = str(params.get("account_id") or params.get("_resolved_account_id") or "").strip()
    if account_id:
        return account_id
    return f"prospect_{_safe_user_id(params)}"


def _infer_stage(params: dict[str, Any], lifecycle: dict[str, Any] | None) -> str:
    text = _text(
        params, "message", "objective", "business_goal", "industry", "current_stage", "resources"
    ).lower()
    if lifecycle and lifecycle.get("project_id"):
        if lifecycle.get("stage") in {"positioning_approved", "experiment_running"}:
            return "operating_creator"
        return "strategy_in_progress"
    if any(marker in text for marker in ("百万", "矩阵", "团队", "投放", "商业化", "已有账号")):
        return "advanced_operator"
    if any(marker in text for marker in ("产品", "获客", "业务", "公司", "课程", "门店", "服务")):
        return "business_builder"
    if any(marker in text for marker in ("普通人", "不知道", "没账号", "不会", "小白", "探索")):
        return "explorer"
    return "new_creator"


def _confidence(params: dict[str, Any]) -> float:
    signals = 0
    for key in ("business_goal", "industry", "resources", "constraints", "platforms"):
        value = params.get(key)
        if isinstance(value, str) and value.strip():
            signals += 1
        elif isinstance(value, list) and value:
            signals += 1
    if _text(params, "message", "objective"):
        signals += 1
    return min(0.78, 0.16 + signals * 0.11)


def _platforms(params: dict[str, Any]) -> list[str]:
    values = _list(params, "platforms")
    if values:
        return values
    text = _text(params, "message", "objective", "business_goal").lower()
    inferred: list[str] = []
    for marker, platform in (
        ("知乎", "zhihu"),
        ("公众号", "wechat_mp"),
        ("抖音", "douyin"),
        ("视频号", "wechat_channels"),
        ("小红书", "xiaohongshu"),
        ("b站", "bilibili"),
        ("bilibili", "bilibili"),
    ):
        if marker in text and platform not in inferred:
            inferred.append(platform)
    return inferred or ["douyin", "zhihu", "wechat_mp"]


def _opening_message(stage: str) -> str:
    if stage == "explorer":
        return (
            "你先不用研究功能，也不用急着登录账号。接下来 30 分钟我先帮你把“能长期做什么、"
            "可能服务谁、第一条内容怎么验证”跑出来；今天晚上你至少能拿到一个可执行的起号假设。"
        )
    if stage == "business_builder":
        return (
            "我们不先堆内容，先把你的业务目标翻译成账号 DNA：谁会信你、为什么现在要听你、"
            "第一批内容验证什么。30 分钟内先产出一个可发布方向，而不是一份空泛方案。"
        )
    if stage == "advanced_operator":
        return (
            "你这种情况不能用新手模板。我会先拆账号资产、受众缺口和平台推流变量，"
            "再把下一轮内容做成可证伪实验，避免靠感觉改方向。"
        )
    if stage == "strategy_in_progress":
        return (
            "我会沿着已有账号生命周期继续：先看当前证据缺口，再决定补受众、找对标、定定位，"
            "还是进入第一条内容实验。"
        )
    return (
        "我先不让你填长问卷。我们用一轮对话把账号方向、目标受众和第一条验证内容搭起来，"
        "再把它沉淀成后续内容生产都能复用的账号 DNA。"
    )


def _questions(params: dict[str, Any], stage: str) -> list[dict[str, str]]:
    questions: list[dict[str, str]] = []
    if not _text(params, "business_goal", "objective", "message"):
        questions.append({
            "id": "goal_anchor",
            "question": "你希望这个账号先帮你完成什么：表达、获客、变现，还是找到长期方向？",
            "why": "先锁定账号服务的真实目标，避免一开始就被平台热点带偏。",
        })
    if not _list(params, "resources"):
        questions.append({
            "id": "supply_asset",
            "question": "你身上有哪些能长期供给内容的东西：经历、技能、案例、资源、人脉或观点？",
            "why": "账号能否长期跑，取决于稳定供给，而不是第一条内容写得多漂亮。",
        })
    if not _list(params, "audience") and stage in {"explorer", "new_creator", "business_builder"}:
        questions.append({
            "id": "audience_seed",
            "question": "如果只选一类人先服务，你更想帮谁变好、变省事、变赚钱或变清醒？",
            "why": "目标受众先是假设，后续再用对标、数据和发布结果修正。",
        })
    if not _list(params, "constraints"):
        questions.append({
            "id": "boundary",
            "question": "你有哪些明确不想做的事：不露脸、不讲私生活、不碰争议，还是不能每天更新？",
            "why": "边界越早写进 DNA，后面生产内容越不容易跑偏。",
        })
    return questions[:2]


def _dna_seed(params: dict[str, Any], stage: str) -> dict[str, Any]:
    goal = _text(params, "business_goal", "objective", "message") or "待通过自然对话确认"
    resources = _list(params, "resources")
    constraints = _list(params, "constraints")
    audience = _list(params, "audience")
    industry = _text(params, "industry") or "待确认"
    return {
        "status": "provisional",
        "stage": stage,
        "business_goal": goal,
        "industry_or_theme": industry,
        "target_audience_hypothesis": audience or ["待从能力、兴趣、可服务人群中生成 2-3 个方向假设"],
        "supply_assets": resources or ["待补充：真实经历/技能/案例/资源/观点"],
        "boundaries": constraints or ["待补充：出镜、频率、争议、隐私和时间投入边界"],
        "preferred_platforms": _platforms(params),
        "monetization_paths": [
            "先验证注意力与信任，再判断咨询、课程、服务、社群、私域或产品化路径",
        ],
        "confidence": _confidence(params),
        "data_gaps": [
            "真实受众画像需要登录平台或创作者中心数据",
            "对标依据需要带作者身份、来源 URL 和样本内容",
            "变现判断需要结合用户资源、交付能力和可承受风险",
        ],
    }


def _audience_draft_payload(params: dict[str, Any], dna: dict[str, Any]) -> dict[str, Any]:
    segment = dna["target_audience_hypothesis"][0]
    if isinstance(segment, dict):
        label = str(segment.get("label") or "待验证受众")
    else:
        label = str(segment or "待验证受众")
    return {
        "account_id": _resolve_account_id(params),
        "business_goal": dna["business_goal"],
        "segments": [{
            "label": label,
            "source": "account_dna_onboarding",
            "confidence": dna["confidence"],
        }],
        "pains": ["待通过对话、对标和真实评论验证"],
        "scenarios": ["首次起号/账号重定位的 72 小时验证"],
        "exclusions": dna["boundaries"],
        "data_gaps": dna["data_gaps"],
    }


def _thirty_minute_plan(stage: str) -> list[dict[str, Any]]:
    return [
        {
            "minute": "0-3",
            "action": "把用户从功能选择里拉出来，明确今晚的可见成果",
            "output": "一句话目标 + 当前不确定性",
        },
        {
            "minute": "3-8",
            "action": "只问 1-2 个关键问题，抽取能力、资源、边界和收入期待",
            "output": "Account DNA v0 草案",
        },
        {
            "minute": "8-15",
            "action": "生成 2-3 个账号方向假设，并说明内容难度、验证周期和潜在变现路径",
            "output": "方向候选，不冒充最终定位",
        },
        {
            "minute": "15-23",
            "action": "选一个方向做第一轮可证伪内容实验",
            "output": "实验假设、单一变量、成功标准",
        },
        {
            "minute": "23-30",
            "action": "产出第一条内容 brief；有平台数据则读数据，没有数据则走待绑定项目",
            "output": "可打磨的选题/软文/视频脚本起点",
        },
    ]


def _seventy_two_hour_plan() -> list[dict[str, Any]]:
    return [
        {
            "window": "Day 0",
            "goal": "让用户 30 分钟内看到智能体理解了自己",
            "actions": ["Account DNA v0", "第一条内容实验 brief", "记录拒绝项与偏好"],
        },
        {
            "window": "Day 1",
            "goal": "补证据，不急着放大生产",
            "actions": ["找 3-5 个对标候选", "补平台规则与表达差异", "完成第一版内容"],
        },
        {
            "window": "Day 2",
            "goal": "形成小闭环",
            "actions": ["发布或模拟发布前预演", "记录预测", "收集早期指标或人工反馈"],
        },
        {
            "window": "Day 3",
            "goal": "让用户感到系统在变聪明",
            "actions": ["复盘预测偏差", "生成策略候选", "修订账号 DNA 或下一条内容变量"],
        },
    ]


def _tool_sequence(stage: str) -> list[dict[str, Any]]:
    sequence = [
        {
            "tool": "marketing_read_account_onboarding",
            "purpose": "生成 Account DNA Onboarding 计划和第一轮对话策略",
            "timing": "用户进入起号/定位/不知道做什么时立即调用",
        },
        {
            "tool": "marketing_read_account_lifecycle",
            "purpose": "读取真实生命周期阶段；无账号时使用 prospect 待绑定项目",
            "timing": "开始任何定位、受众或对标判断前",
        },
        {
            "tool": "marketing_draft_audience_hypothesis",
            "purpose": "用户确认方向后写入受众假设草案，不直接生效",
            "timing": "用户给出目标/受众/边界后",
        },
    ]
    if stage in {"strategy_in_progress", "advanced_operator", "operating_creator"}:
        sequence.extend([
            {
                "tool": "marketing_draft_benchmark_discover",
                "purpose": "从真实作者证据里找对标候选",
                "timing": "目标受众假设已确认后",
            },
            {
                "tool": "marketing_read_account_experiments",
                "purpose": "读取旧实验、预测和复盘，避免从零瞎猜",
                "timing": "进入内容生产前",
            },
        ])
    else:
        sequence.append({
            "tool": "marketing_read_trends",
            "purpose": "只在方向候选需要外部热点校准时读取，不把热点当定位",
            "timing": "用户选定一个方向候选后",
        })
    return sequence


def build_account_onboarding_plan(
    params: dict[str, Any] | None = None,
    *,
    store: Any | None = None,
) -> dict[str, Any]:
    """Build the first-use Account DNA onboarding plan.

    The function is read-only.  It may read lifecycle status when a store is
    provided, but it never creates projects, drafts, memories, or assets.
    """
    params = params or {}
    user_id = str(params.get("__user_id") or params.get("user_id") or "default").strip() or "default"
    account_id = _resolve_account_id(params)
    lifecycle: dict[str, Any] | None = None
    if store is not None:
        try:
            from .account_lifecycle import AccountLifecycleService

            lifecycle = AccountLifecycleService(store).read_account_status(
                user_id=user_id, account_id=account_id
            )
        except Exception as exc:  # pragma: no cover - defensive: onboarding must degrade gracefully.
            lifecycle = {
                "stage": "unknown",
                "next_action": "retry_account_lifecycle_read",
                "error": str(exc),
            }
    stage = _infer_stage(params, lifecycle)
    dna = _dna_seed(params, stage)
    questions = _questions(params, stage)
    has_draft_minimum = bool(
        _text(params, "business_goal", "objective", "message")
        and _list(params, "resources")
        and _list(params, "audience")
    )
    recommended_next_action = (
        "draft_audience_hypothesis_for_user_confirmation"
        if has_draft_minimum
        else "ask_next_question"
    )
    return {
        "version": ACCOUNT_ONBOARDING_VERSION,
        "user_id": user_id,
        "account_id": account_id,
        "mode": "prospect" if account_id.startswith("prospect_") else "connected_account",
        "inferred_stage": stage,
        "opening_message": _opening_message(stage),
        "recommended_next_action": recommended_next_action,
        "next_questions": questions,
        "account_dna_v0": dna,
        "suggested_audience_draft_payload": _audience_draft_payload(params, dna),
        "first_30_minutes": _thirty_minute_plan(stage),
        "first_72_hours": _seventy_two_hour_plan(),
        "activation_loop": {
            "input": "用户对话、账号数据、热点证据、对标样本、内容结果",
            "model": "Account DNA → 内容实验 → 预演预测 → 发布回执 → 复盘学习",
            "output": "下一次更准的问题、更少的废动作、更贴账号的内容方案",
        },
        "tool_sequence": _tool_sequence(stage),
        "guardrails": [
            "不要要求用户先登录；无账号时使用 prospect 待绑定项目",
            "不要一次性抛出长问卷；每轮只问 1-2 个影响决策的问题",
            "Account DNA v0 是假设，不是真实粉丝画像",
            "用户确认前不把草案当成生效定位",
            "热点只能校准表达，不能替代账号定位",
        ],
        "lifecycle": lifecycle or {
            "stage": "not_read",
            "next_action": "read_account_lifecycle_when_tool_context_is_available",
        },
    }


__all__ = ["ACCOUNT_ONBOARDING_VERSION", "build_account_onboarding_plan"]
