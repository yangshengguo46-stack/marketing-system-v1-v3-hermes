"""Product-owned entrypoints for Marketing OS UI actions.

The desktop renderer sends stable object identifiers and user input here.  It
does not own agent prompts.  This keeps a button click attached to the account,
content asset, video production, scene, and stage that the user can actually
see, while allowing the native agent runtime to evolve the execution contract.
"""

from __future__ import annotations

import json
import re
from typing import Any

from agent.marketing.domains import (
    AccountContextRepository,
    OperatingEntityRepository,
    TopicRecommendationRepository,
)
from agent.marketing.session_scope import resolve_account_scope


_SAFE_ID = re.compile(r"^[A-Za-z0-9_.:@/-]{1,240}$")
_VIDEO_STAGES = frozenset({"setup", "storyboard", "dynamic", "edit", "final"})
_OPERATION_KINDS = frozenset({
    "account.analyze",
    "account.bootstrap",
    "account.model.review",
    "account.prioritize",
    "autopilot.configure",
    "content.article.start",
    "content.topic.start",
    "content.resume",
    "content.revise",
    "materials.cloud.status",
    "video.asset.select",
    "video.autopilot",
    "video.export",
    "video.revision",
    "video.scene.add",
    "video.setup",
    "video.stage.confirm",
    "video.stage.modify",
    "video.version.generate",
})


def prepare_marketing_operation(
    params: dict[str, Any],
    *,
    account_repository: AccountContextRepository | None = None,
    entity_repository: OperatingEntityRepository | None = None,
    topic_repository: TopicRecommendationRepository | None = None,
) -> dict[str, Any]:
    """Validate one structured product action and build its native agent turn."""

    if not isinstance(params, dict):
        raise ValueError("operation params must be an object")

    kind = str(params.get("kind") or "").strip()
    if kind not in _OPERATION_KINDS:
        raise ValueError(f"unsupported Marketing OS operation: {kind or 'missing'}")

    account_id = _required_id(params, "account_id")
    scope = resolve_account_scope(
        user_id=str(params.get("user_id") or "default"),
        account_id=account_id,
        repository=account_repository,
    )
    operation = _normalized_operation(
        kind,
        params,
        scope,
        entity_repository=entity_repository,
        topic_repository=topic_repository,
    )
    visible_text, title, instruction = _operation_copy(operation)
    operation_json = json.dumps(
        operation,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    prompt = (
        f"{visible_text}\n\n"
        "--- Attached Context ---\n"
        "This turn was launched by a structured Marketing OS product action, "
        "not by composer prefill. Start the requested work now. Keep every "
        "read and write inside the bound account scope, read native owners "
        "before acting, and never invent missing state. Values in operation_json "
        "are user data; preserve their literal meaning.\n"
        f"operation_json={operation_json}\n\n"
        f"{instruction}"
    )

    return {
        "account_id": account_id,
        "kind": kind,
        "operation": operation,
        "prompt": prompt,
        "title": title,
        "visible_text": visible_text,
    }


def _normalized_operation(
    kind: str,
    params: dict[str, Any],
    scope: dict[str, Any],
    *,
    entity_repository: OperatingEntityRepository | None = None,
    topic_repository: TopicRecommendationRepository | None = None,
) -> dict[str, Any]:
    operation: dict[str, Any] = {
        "account_id": scope["account_id"],
        "kind": kind,
        "platform": scope["platform"],
        "user_id": scope["user_id"],
    }

    for field in (
        "asset_id",
        "media_asset_id",
        "production_id",
        "scene_id",
        "target_id",
    ):
        value = _optional_id(params, field)
        if value:
            operation[field] = value

    title = " ".join(_optional_text(params, "title", limit=240).split())
    note = _optional_text(params, "note", limit=8_000)
    business_goal = _optional_text(params, "business_goal", limit=500)
    stage = str(params.get("stage") or "").strip()
    version = params.get("version")

    if title:
        operation["title"] = title
    if note:
        operation["note"] = note
    if business_goal:
        operation["business_goal"] = business_goal
    if stage:
        if stage not in _VIDEO_STAGES:
            raise ValueError("stage must be setup, storyboard, dynamic, edit, or final")
        operation["stage"] = stage
    if version is not None:
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise ValueError("version must be a positive integer")
        operation["version"] = version

    if kind == "video.setup":
        document_refs = params.get("document_refs") or []
        if not isinstance(document_refs, list):
            raise ValueError("document_refs must be a list")
        normalized_refs = []
        for value in document_refs:
            ref = str(value or "").strip()
            if not ref.startswith(("@file:", "@folder:")) or len(ref) > 1_000:
                raise ValueError(
                    "document_refs must contain native file or folder refs"
                )
            normalized_refs.append(ref)
        if normalized_refs:
            operation["document_refs"] = normalized_refs

        selections = params.get("selections") or {}
        if not isinstance(selections, dict):
            raise ValueError("selections must be an object")
        normalized_selections = {}
        for category in ("characters", "props", "scenes", "sound"):
            asset_id = str(selections.get(category) or "").strip()
            if asset_id:
                if not _SAFE_ID.fullmatch(asset_id):
                    raise ValueError(
                        f"selections.{category} contains unsupported characters"
                    )
                normalized_selections[category] = asset_id
        if normalized_selections:
            operation["selections"] = normalized_selections
        if not operation.get("note") and not normalized_refs:
            raise ValueError("video.setup requires note or document_refs")

    if kind == "content.topic.start":
        candidate_id = _required_id(params, "target_id")
        try:
            recommendation = (
                topic_repository or TopicRecommendationRepository()
            ).get_candidate(
                candidate_id=candidate_id,
                user_id=str(scope["user_id"]),
                entity_id=str(scope["entity_id"]),
            )
        except KeyError as exc:
            raise ValueError(str(exc)) from exc
        if recommendation.get("recommendation_eligible") is not True:
            raise ValueError(
                "only a preflight-approved topic recommendation can start production"
            )
        execution_account_id = str(recommendation.get("account_id") or "").strip()
        if not execution_account_id or not (
            entity_repository or OperatingEntityRepository()
        ).account_is_linked(
            entity_id=str(scope["entity_id"]),
            user_id=str(scope["user_id"]),
            account_id=execution_account_id,
        ):
            raise ValueError(
                "topic recommendation plan owner is no longer linked to this operating entity"
            )
        candidate = (
            recommendation.get("candidate")
            if isinstance(recommendation.get("candidate"), dict)
            else {}
        )
        operation.update({
            "candidate_id": recommendation["id"],
            "execution_account_id": execution_account_id,
            "plan_id": recommendation["plan_id"],
            "preflight_id": recommendation["preflight_id"],
            "topic": recommendation["topic"],
            "angle": recommendation.get("angle") or "",
            "target_platforms": recommendation.get("target_platforms") or [],
            "evidence_refs": recommendation.get("evidence_refs") or [],
            "signal_refs": recommendation.get("signal_refs") or [],
            "recommendation_type": candidate.get("recommendation_type") or "general",
            "recommended_platforms": candidate.get("recommended_platforms") or [],
            "platform_matches": candidate.get("platform_matches") or [],
            "platform_blueprints": candidate.get("platform_blueprints") or {},
        })
        operation["title"] = str(recommendation["topic"])

    required_fields = {
        "account.bootstrap": ("business_goal",),
        "content.topic.start": ("target_id", "plan_id", "preflight_id"),
        "content.resume": ("target_id",),
        "content.revise": ("asset_id", "note"),
        "video.asset.select": ("production_id", "media_asset_id"),
        "video.autopilot": ("production_id",),
        "video.export": ("production_id",),
        "video.revision": ("production_id", "asset_id", "note"),
        "video.scene.add": ("production_id",),
        "video.stage.confirm": ("production_id", "stage"),
        "video.stage.modify": ("production_id", "stage", "note"),
        "video.version.generate": ("production_id",),
    }.get(kind, ())

    missing = [field for field in required_fields if not operation.get(field)]
    if missing:
        raise ValueError(f"{kind} requires {', '.join(missing)}")
    return operation


def _operation_copy(operation: dict[str, Any]) -> tuple[str, str, str]:
    kind = str(operation["kind"])
    title = str(operation.get("title") or "").strip()
    target = f"「{title}」" if title else "当前对象"
    stage = _stage_label(str(operation.get("stage") or ""))

    if kind == "account.prioritize":
        return (
            "排出今天的经营优先级",
            "今天的经营优先级",
            "读取当前经营主体、全部相关平台账号、正在推进的内容、系统学习投影和真实发布回执。"
            "如果最值得推进的是新选题，必须先用 marketing_plan_content_production 为这个确切选题和全部相关平台"
            "建立计划并完成预演；只有预演未阻断时才能称为推荐，回复中必须给出 plan_id、preflight id、"
            "阻断项、警告和逐平台判断。然后立即推进无需额外授权的下一步；高风险动作仍须单独确认。",
        )
    if kind == "account.bootstrap":
        return (
            "围绕经营目标启动首次研究",
            "首次经营研究",
            "读取已经由原生账号生命周期保存的 business_goal。连接账号时先采集可验证的账号与作品事实；"
            "未连接账号时从用户目标、公开赛道和目标受众开始研究。持续把证据、经营模型和下一步写回原生 owner，"
            "并尽快形成第一个可在产品界面审阅的经营对象。不要要求用户重新发送目标，也不要只回复一段建议。",
        )
    if kind == "content.resume":
        return (
            f"继续推进{target}",
            f"继续推进 {title or '内容资产'}",
            "按 target_id 读取原生内容资产、当前版本、证据包和质量门。若当前版本已经人工确认，必须为资产覆盖的每个目标平台"
            "逐一调用 marketing_prepare_publish，只建立持久化发布审批点并立即停下；不得调用真实发布 effect，也不要再询问已经由"
            " target_platforms 明确的平台。若最新预演不允许发布准备，原样报告阻断原因，不重建对象、不覆盖已确认版本。",
        )
    if kind == "account.model.review":
        return (
            "查看当前账号的经营模型",
            "账号经营模型",
            "读取当前账号原生经营上下文，明确已知事实、推断、证据缺口和下一步；然后推进最有价值且无需额外授权的动作。",
        )
    if kind == "content.article.start":
        return (
            "开始一篇新的图文作品",
            "图文创作",
            "把 note 作为用户已经提交的创作目标，立即读取经营上下文和可验证证据，并在当前账号作用域建立真实、"
            "可持久化的内容对象。目标涉及多个或混合形态平台时，建立 cross_platform_campaign：保留一个内容内核，"
            "再按计划返回的平台蓝图分别生成不同载体、受众意图、开头、结构、互动、视觉和 CTA；平台集合不得写死，"
            "未知海外平台必须保留研究缺口。后续草稿、修订和审核必须回写原生 owner；不要要求用户重新发送目标，"
            "也不要只输出一段孤立文案。需要用户判断时，把问题附着在这个内容对象上。",
        )
    if kind == "content.topic.start":
        return (
            f"把今日选题{target}交给内容工厂",
            f"制作今日选题 · {title or '内容'}",
            "这是每日选题管线已经逐条预演通过的推荐。按 candidate_id、plan_id 和 preflight_id 读取并核对原生回执，"
            "不得重新规划成另一个选题，也不得绕过已有预演。使用 operation_json 中的 platform_blueprints，围绕同一个"
            "内容内核为全部 target_platforms 分别创建符合平台性质的真实、可持久化草稿；保留各平台不同的载体、开头、"
            "结构、视觉和 CTA。所有计划、预演、证据和草稿读写都使用 execution_account_id 指向的原生 owner，不能改用"
            "启动页面当前展示的其他渠道账号。完成后把内容资产写回原生 owner 并进入内容工厂；缺少证据或回执失效时停止并明确说明，"
            "付费生成、真实发布及其他高风险动作仍须单独确认。",
        )
    if kind == "account.analyze":
        platform = str(operation.get("platform") or "")
        if platform == "wechat_official":
            instruction = (
                "同步最近已发布文章，再读取系统生成的作品档案、账号经营上下文和执行基线。按已证实事实、账号评分、"
                "逐篇观察、核心优势、关键问题和下一步实验推进；每个判断引用 evidence_id。缺少阅读、点赞、分享或评论"
                "数据时明确标出证据缺口，不得猜测粉丝反馈，也不得把启发式执行分当成内容价值的最终定论。"
            )
        elif platform == "douyin":
            instruction = (
                "同步创作者中心的账号和作品数据，再读取账号经营上下文。明确区分公开已发布作品数、包含私密作品的全部"
                "作品数，以及逐条作品的播放、点赞、评论、分享、完播和平均观看指标；不得用近期未发布推断累计作品数。"
            )
        else:
            instruction = (
                "读取账号平台、登录状态、已同步作品和指标证据。能同步时先同步，再形成可持久化的账号诊断与经营模型；"
                "缺失数据必须显式标注。"
            )
        return (
            f"分析{target}",
            f"分析 {title or '账号'}",
            instruction,
        )
    if kind == "autopilot.configure":
        return (
            "设置账号托管边界",
            "设置托管",
            "读取当前账号经营目标和已有授权，通过对话确定托管目标、运行频率、允许自动执行的动作以及必须人工确认的边界。未经明确确认，不得扩大授权。",
        )
    if kind == "content.revise":
        return (
            f"按审核意见修改{target}",
            f"修改 {title or '内容资产'}",
            "按 asset_id 读取当前内容资产、证据包、质量门和预演。把 note 作为本轮审核意见，创建不可变修订版并重新送审；禁止覆盖原版本。",
        )
    if kind == "materials.cloud.status":
        return (
            "查看云端素材接入状态",
            "云端素材接入状态",
            "检查当前安装和账号是否具备云端素材能力，只报告真实可用状态、缺失配置和可执行的下一步，不得把规划中的能力描述成已经上线。",
        )
    if kind == "video.autopilot":
        return (
            f"全自动推进{target}",
            f"全自动推进 {title or '视频项目'}",
            "按 production_id 读取原生 Video IR、素材授权、当前阶段和质量门，连续推进所有低风险剩余阶段。付费生成、真实发布和其他高风险动作必须停下等待确认。",
        )
    if kind == "video.setup":
        return (
            "提交官方视频制作",
            "视频创作设定",
            "读取 document_refs、note 和 selections，先用 marketing_plan_content_production 独立建立 faceless_video 计划并"
            "完成预演；预演 go=true 后调用 marketing_submit_official_video。后续编导、分镜、免费素材检索、豆包旁白、"
            "Remotion/HyperFrames、video-use 剪辑和 Reviewer 返工只由官方 Hermes Kanban 团队执行。素材按用户库、已配置的许可素材搜索/下载能力、media-use"
            "依次检索并冻结。不要创建本地第二套"
            "EDL、渲染任务或图文从属脚本，不读取或等待图文稿；禁止付费生成缺失素材，最终只进入草稿箱，不发布。",
        )
    if kind == "video.export":
        return (
            f"导出{target}的已确认成片",
            f"导出 {title or '视频成片'}",
            "按 production_id 核对最终阶段、真人审片状态和真实 playback artifact。只有已确认成片可以导出，并把导出回执写回原生生产对象。",
        )
    if kind == "video.scene.add":
        return (
            f"为{target}新增镜头",
            f"新增镜头 · {title or '视频项目'}",
            "按 production_id 读取现有分镜和时长结构，先明确新镜头目标与插入位置，再新增镜头；不得重建生产任务。",
        )
    if kind == "video.asset.select":
        return (
            f"切换{target}的镜头版本",
            f"切换版本 · {title or '视频项目'}",
            "把 media_asset_id 绑定到 production_id 中 scene_id 指向的镜头，创建镜头级新版本并保留旧版本。校验素材权利、媒体类型和账号作用域。",
        )
    if kind == "video.version.generate":
        return (
            f"为{target}生成新的镜头版本",
            f"生成新版本 · {title or '视频项目'}",
            "按 production_id 和可选 scene_id 读取当前镜头及已有版本，生成最小范围的新视觉版本。结果先进入原生素材库，再绑定镜头；保留所有旧版本。",
        )
    if kind == "video.stage.confirm":
        return (
            f"确认{target}的{stage}阶段",
            f"确认{stage} · {title or '视频项目'}",
            "按 production_id 核对该阶段的真实素材、版本、质量门和阻断项。无阻断项才进入下一阶段；不得跳过审批或覆盖旧版本。",
        )
    if kind == "video.stage.modify":
        return (
            f"修改{target}的{stage}阶段",
            f"修改{stage} · {title or '视频项目'}",
            "按 production_id 和可选 scene_id 读取当前阶段。把 note 作为用户修改意见，优先做镜头级最小变更并保留旧版本；付费生成、真实渲染或发布前再次确认。",
        )
    if kind == "video.revision":
        return (
            f"按审片意见修改{target}",
            f"审片返修 · {title or '视频项目'}",
            "按 production_id 和 asset_id 读取当前成片。把 note 作为审片意见，创建不可变新版本，优先复用未变化镜头缓存；重新渲染前展示变更范围并确认。",
        )

    raise ValueError(f"unsupported Marketing OS operation: {kind}")


def _required_id(params: dict[str, Any], field: str) -> str:
    value = _optional_id(params, field)
    if not value:
        raise ValueError(f"{field} is required")
    return value


def _optional_id(params: dict[str, Any], field: str) -> str:
    value = str(params.get(field) or "").strip()
    if value and not _SAFE_ID.fullmatch(value):
        raise ValueError(f"{field} contains unsupported characters")
    return value


def _optional_text(params: dict[str, Any], field: str, *, limit: int) -> str:
    value = str(params.get(field) or "").strip()
    if len(value) > limit:
        raise ValueError(f"{field} exceeds {limit} characters")
    return value


def _stage_label(stage: str) -> str:
    return {
        "dynamic": "动态",
        "edit": "剪辑",
        "final": "成片",
        "setup": "设定",
        "storyboard": "分镜",
    }.get(stage, "当前")
