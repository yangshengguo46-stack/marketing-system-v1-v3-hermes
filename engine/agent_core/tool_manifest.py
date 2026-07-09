"""Minimal marketing-desktop tool manifest.

Only capabilities that are both implemented and safe are registered.  Product
writes and Electron-owned actions stay absent until the durable approval/effect
bridge can execute them without bypassing the capability boundary.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any, Callable

from .models import CapabilityLevel


@dataclass(frozen=True)
class ToolSpec:
    name: str
    level: CapabilityLevel
    description: str
    schema: dict[str, Any]
    handler: Callable[[dict], str]
    requires_approval: bool = False


def _schema(properties: dict | None = None) -> dict:
    return {"type": "object", "properties": properties or {}, "additionalProperties": False}


def _ensure_marketing_path() -> None:
    path = Path(__file__).resolve().parents[1] / "marketing-os"
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


def _server_read(function_name: str, *, pass_params: bool = False):
    def handler(params: dict) -> str:
        _ensure_marketing_path()
        server = import_module("server")
        function = getattr(server, function_name)
        result = function(params) if pass_params else function()
        return json.dumps(result, ensure_ascii=False, default=str)
    return handler


def _tool_read(module_name: str, function_name: str):
    def handler(params: dict) -> str:
        _ensure_marketing_path()
        module = import_module(f"marketing_tools.{module_name}")
        result = getattr(module, function_name)(params)
        return result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, default=str)
    return handler


def _content_production_plan_handler(params: dict) -> str:
    from .content_production import build_content_production_plan

    return json.dumps(build_content_production_plan(params), ensure_ascii=False, default=str)


def _server_action(function_name: str):
    def handler(params: dict) -> str:
        _ensure_marketing_path()
        server = import_module("server")
        result = getattr(server, function_name)(params)
        return result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, default=str)
    return handler


READ_TOOLS: list[ToolSpec] = [
    ToolSpec("marketing_read_context", CapabilityLevel.READ_ONLY,
             "读取最新行业目标、热点、选题、巡检报告和脱敏账号指标；数据缺失时保留真实状态",
             _schema({"limit": {"type": "integer", "minimum": 1, "maximum": 20}}),
             _tool_read("monitor", "get_marketing_context")),
    ToolSpec("marketing_research_web_search", CapabilityLevel.READ_ONLY,
             "使用已配置的 Firecrawl 免费云额度或本地自托管服务搜索公开网页，返回来源 URL 与正文证据；不登录平台、不操作页面",
             _schema({
                 "query": {"type": "string", "description": "行业、事件或竞品研究问题"},
                 "limit": {"type": "integer", "minimum": 1, "maximum": 20, "default": 8},
             }), _tool_read("firecrawl_provider", "search_for_agent")),
    ToolSpec("marketing_read_trends", CapabilityLevel.READ_ONLY,
             "搜索已缓存热点趋势，按关键词、平台筛选本地缓存（非实时网络抓取）；"
             "结果保留来源、采集时间、URL 等完整证据",
             _schema({
                 "query": {"type": "string",
                           "description": "搜索关键词（匹配标题和分类，如 AI/教育/财经），留空返回全部"},
                 "platform": {"type": "string",
                              "description": "平台筛选：douyin / bilibili / xiaohongshu / kuaishou / zhihu"},
                 "limit": {"type": "integer", "minimum": 1, "maximum": 30, "default": 30},
             }),
             _server_read("query_trending_cache", pass_params=True)),
    ToolSpec("marketing_read_accounts", CapabilityLevel.READ_ONLY,
             "读取账号脱敏元信息和最近指标快照，不读取 Cookie",
             _schema(), _server_read("get_accounts_for_tool", pass_params=True)),
    ToolSpec("marketing_read_suggestions", CapabilityLevel.READ_ONLY,
             "读取已有选题建议及其依据和置信度",
             _schema(), _server_read("get_suggestions")),
    ToolSpec("marketing_read_dashboard", CapabilityLevel.READ_ONLY,
             "读取营销概览的真实持久数据",
             _schema(), _server_read("dashboard_overview")),
    ToolSpec("marketing_read_profiles", CapabilityLevel.READ_ONLY,
             "读取用户画像配置",
             _schema(), _server_read("get_profiles")),
    ToolSpec("marketing_read_intelligence_report", CapabilityLevel.READ_ONLY,
             "读取最近巡检步骤、错误、降级和证据",
             _schema(), _server_read("intelligence_report")),
    ToolSpec("marketing_read_analytics", CapabilityLevel.READ_ONLY,
             "读取发布分析汇总；无真实数据时返回空状态",
             _schema(), _server_read("analytics_summary")),
    ToolSpec("marketing_read_publishing_tasks", CapabilityLevel.READ_ONLY,
             "读取 SQL 发布任务、发布回执、指标回收 checkpoint 和已采集快照，不执行发布或删除",
             _schema({
                 "status": {"type": "string", "description": "可选状态筛选：queued/executing/published/metrics_collected/failed"},
                 "platform": {"type": "string", "description": "可选平台筛选"},
             }), _server_read("agent_publishing_tasks", pass_params=True)),
    ToolSpec("marketing_read_workflow_status", CapabilityLevel.READ_ONLY,
             "读取巡检计划与最近运行状态",
             _schema(), _server_read("workflow_status")),
    ToolSpec("marketing_read_intelligence_config", CapabilityLevel.READ_ONLY,
             "读取巡检行业、平台和账号同步配置",
             _schema(), _server_read("intelligence_config")),
    ToolSpec("marketing_read_memory_list", CapabilityLevel.READ_ONLY,
             "读取已有记忆（用户画像、账号DNA、项目上下文、结果记录），支持按类型和账号筛选",
             _schema({
                 "kind": {"type": "string", "description": "记忆类型：user/account/episodic/semantic/procedural"},
                 "account_id": {"type": "string", "description": "按账号ID筛选"},
                 "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 20},
             }),
             _server_read("get_memories", pass_params=True)),
    ToolSpec("marketing_read_content_list", CapabilityLevel.READ_ONLY,
             "列出内容资产（选题、脚本、视频、封面），支持按状态、类型、账号筛选",
             _schema({
                 "status": {"type": "string", "description": "状态：draft/review/approved/published"},
                 "type": {"type": "string", "description": "类型：script/video/image/caption"},
                 "account_id": {"type": "string", "description": "按账号ID筛选"},
             }),
             _server_read("get_content_assets", pass_params=True)),
    ToolSpec("marketing_plan_content_production", CapabilityLevel.READ_ONLY,
             "根据用户目标生成内容生产工单，自动选择知乎/公众号软文、不露脸素材拼接视频、真人/数字人高质量视频三条路线之一；"
             "只生成计划和质量门，不写草稿、不下载素材、不调用付费视频 API",
             _schema({
                 "objective": {"type": "string", "description": "用户原始内容生产目标"},
                 "kind": {
                     "type": "string",
                     "enum": ["auto", "article_soft", "faceless_video", "premium_human_video"],
                     "description": "可选；auto 时由平台和语义判断",
                 },
                 "platforms": {
                     "type": "array",
                     "items": {
                         "type": "string",
                         "enum": ["douyin", "bilibili", "xiaohongshu", "kuaishou", "zhihu", "wechat_channels", "wechat_official", "tiktok", "youtube"],
                     },
                     "description": "目标平台",
                 },
                 "account_id": {"type": "string", "description": "可选账号 ID"},
             }),
             _content_production_plan_handler),
    ToolSpec("marketing_prepare_faceless_render", CapabilityLevel.READ_ONLY,
             "读取不露脸视频内容资产的 EDL 和本地素材状态，准备确定性 ffmpeg 渲染命令；"
             "不执行渲染、不写文件、素材未齐时返回 blocked",
             _schema({
                 "asset_id": {"type": "string", "description": "不露脸视频内容资产 ID"},
                 "project_dir": {"type": "string", "description": "视频项目素材目录；应包含 videos/{shot_id}.mp4"},
                 "output_path": {"type": "string", "description": "可选输出路径，仅用于命令生成"},
                 "ffmpeg_path": {"type": "string", "description": "可选 ffmpeg 路径"},
                 "ffprobe_path": {"type": "string", "description": "可选 ffprobe 路径"},
             }),
             _server_read("prepare_faceless_render", pass_params=True)),
    ToolSpec("marketing_read_learning_status", CapabilityLevel.READ_ONLY,
             "读取当前用户/账号的数据飞轮状态：内容评分、盲预测、复盘、对标账号和发布节奏；不生成虚构结论",
             _schema({
                 "account_id": {"type": "string", "description": "可选账号 ID"},
             }),
             _server_read("learning_status", pass_params=True)),
    ToolSpec("marketing_read_learning_candidates", CapabilityLevel.READ_ONLY,
             "读取发布后指标对账生成的待治理学习候选；pending 候选只代表系统观察，不会静默改变记忆或策略权重",
             _schema({
                 "account_id": {"type": "string", "description": "可选账号 ID"},
                 "platform": {"type": "string", "description": "可选平台"},
                 "candidate_type": {"type": "string", "enum": ["memory", "strategy", "weight"]},
                 "status": {"type": "string", "enum": ["pending", "accepted", "rejected", "superseded"]},
                 "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 50},
             }),
             _server_read("learning_candidates", pass_params=True)),
    ToolSpec("marketing_read_weight_candidate_replay", CapabilityLevel.READ_ONLY,
             "对权重学习候选做历史回放：检查支持样本、反例比例和可能误伤，不改变候选状态或永久策略权重",
             _schema({
                 "candidate_id": {"type": "string", "description": "weight 类型学习候选 ID"},
                 "window": {"type": "integer", "minimum": 1, "maximum": 500, "default": 50},
                 "min_support": {"type": "integer", "minimum": 1, "maximum": 20},
             }),
             _server_read("weight_candidate_replay", pass_params=True)),
    ToolSpec("marketing_read_influence_score", CapabilityLevel.READ_ONLY,
             "读取指定内容资产的 InfluenceOS Score v0：可解释分项、风险扣分、缺失维度和建议决策；只读不改权重",
             _schema({
                 "asset_id": {"type": "string", "description": "内容资产 ID；传入时读取最新评分/预演/指标标签计算"},
                 "metric_labels": {"type": "object", "description": "可选；发布后指标标签，用于复盘分"},
                 "content_score": {"type": "object", "description": "可选；无 asset_id 时传入内容评分"},
                 "preflight_scores": {"type": "object", "description": "可选；无 asset_id 时传入预演分项"},
             }),
             _server_read("influence_score", pass_params=True)),
    ToolSpec("marketing_read_preflight_decision", CapabilityLevel.READ_ONLY,
             "读取统一 PreflightDecision：把 InfluenceOS Score 转成可生产/先改稿/补证据/换素材/不开机/可发布等产品动作；只读不写记录",
             _schema({
                 "asset_id": {"type": "string", "description": "可选内容资产 ID；传入时读取资产最新分数再生成决策"},
                 "stage": {
                     "type": "string",
                     "enum": ["production_draft", "render_prepare", "publish_review", "launch"],
                     "description": "决策所处阶段；默认 production_draft",
                 },
                 "context": {"type": "object", "description": "可选硬性门槛：blockers/warnings/selected_lane"},
                 "metric_labels": {"type": "object", "description": "可选发布后指标标签"},
                 "content_score": {"type": "object", "description": "无 asset_id 时可传内容评分"},
                 "preflight_scores": {"type": "object", "description": "无 asset_id 时可传预演分项"},
             }),
             _server_read("preflight_decision", pass_params=True)),
    ToolSpec("marketing_read_account_lifecycle", CapabilityLevel.READ_ONLY,
             "读取指定账号的经营生命周期、已确认目标受众、数据缺口和确定性的下一步；没有项目时返回 not_started，不会伪造画像",
             _schema({"account_id": {"type": "string", "description": "目标账号 ID"}}),
             _server_read("account_lifecycle_status", pass_params=True)),
    ToolSpec("marketing_read_benchmark_research", CapabilityLevel.READ_ONLY,
             "读取当前账号项目已经选择的对标账号和带来源的观察证据；公开观察、模型推断和用户输入保持不同 provenance",
             _schema({
                 "account_id": {"type": "string"},
                 "project_id": {"type": "string", "description": "可选；默认当前活动项目"},
             }), _server_read("benchmark_research", pass_params=True)),
    ToolSpec("marketing_read_account_positioning", CapabilityLevel.READ_ONLY,
             "读取账号定位版本和当前生效的兼容 DNA 投影；没有批准版本时如实返回空",
             _schema({"account_id": {"type": "string"}, "project_id": {"type": "string"}}),
             _server_read("positioning_versions", pass_params=True)),
    ToolSpec("marketing_read_audience_snapshots", CapabilityLevel.READ_ONLY,
             "读取平台官方 API 或创作者中心 MCP 写入的真实粉丝画像时间序列；职业、收入等缺失字段保持未知",
             _schema({
                 "account_id": {"type": "string"}, "project_id": {"type": "string"},
                 "platform": {"type": "string"},
                 "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
             }), _server_read("audience_snapshots", pass_params=True)),
    ToolSpec("marketing_read_account_experiments", CapabilityLevel.READ_ONLY,
             "读取账号内容实验；指定 experiment_id 时返回假设、资产、评分、盲预测、发布回执、指标和复盘时间线",
             _schema({
                 "account_id": {"type": "string"}, "project_id": {"type": "string"},
                 "experiment_id": {"type": "string"},
             }), _server_read("account_experiments", pass_params=True)),
    ToolSpec("marketing_read_audience_gap", CapabilityLevel.READ_ONLY,
             "比较已确认目标受众、最新真实粉丝快照和对标受众观察；事实、推断和未知分开展示，差距只用于提出实验",
             _schema({"account_id": {"type": "string"}, "project_id": {"type": "string"}}),
             _server_read("audience_gap", pass_params=True)),
    ToolSpec("marketing_read_strategy_candidates", CapabilityLevel.READ_ONLY,
             "读取账号策略修订候选及其证据、置信度和用户决定；pending 候选尚未改变定位或权重",
             _schema({
                 "account_id": {"type": "string"}, "project_id": {"type": "string"},
                 "status": {"type": "string", "enum": ["pending", "accepted", "rejected"]},
             }), _server_read("strategy_candidates", pass_params=True)),
]

def _noop(params: dict) -> str:
    return json.dumps({"status": "ok", "note": "handler intercepted by gateway"}, ensure_ascii=False)


CONTROLLED_TOOLS: list[ToolSpec] = [
    ToolSpec("marketing_trending_search", CapabilityLevel.CONTROLLED_RESOURCE,
             "使用平台登录会话搜索行业关键词内容，需要用户授权",
             _schema({
                 "platform": {"type": "string", "description": "平台标识", "enum": ["douyin"]},
                 "keyword": {"type": "string", "description": "搜索关键词"},
             }),
             _noop,
             requires_approval=True),
    ToolSpec("marketing_session_login", CapabilityLevel.CONTROLLED_RESOURCE,
             "打开平台登录窗口完成认证，需要用户授权",
             _schema({
                 "platform": {"type": "string", "description": "平台标识",
                              "enum": ["douyin", "bilibili", "xiaohongshu",
                                       "kuaishou", "zhihu", "wechat_channels", "wechat_official"]},
             }),
             _noop,
             requires_approval=True),
    ToolSpec("marketing_accounts_sync", CapabilityLevel.CONTROLLED_RESOURCE,
             "同步指定账号的最新指标（粉丝、点赞、播放），需要用户授权",
             _schema({
                 "platform": {"type": "string", "description": "平台", "enum": ["douyin", "bilibili"]},
                 "username": {"type": "string", "description": "账号 ID"},
             }),
             _noop,
             requires_approval=True),
    ToolSpec("marketing_publish_prepare", CapabilityLevel.CONTROLLED_RESOURCE,
             "只打开指定账号的官方发布页并读取可见控件，不上传文件、不填写内容、不提交发布",
             _schema({
                 "platform": {"type": "string", "description": "平台", "enum": ["douyin"]},
                 "account_id": {"type": "string", "description": "已连接账号 ID"},
                 "asset_id": {"type": "string", "description": "待发布内容资产 ID"},
             }),
             _noop,
             requires_approval=True),
    ToolSpec("marketing_publish_query", CapabilityLevel.CONTROLLED_RESOURCE,
             "反查发布任务是否已经在官方作品列表中出现；只有稳定 URL 或 post_id 才写 verified receipt，不执行发布",
             _schema({
                 "task_id": {"type": "string", "description": "SQL 发布任务 ID"},
                 "refresh": {"type": "boolean", "description": "是否允许刷新创作者中心作品列表", "default": False},
             }),
             _noop,
             requires_approval=True),
]

def _plan_declare_handler(params: dict) -> str:
    """RUN-01: deterministic structured plan protocol.

    The model declares its plan through this tool instead of prose.  Steps
    are validated against the tool manifest; completed steps of an existing
    plan are always preserved.
    """
    from .plan_protocol import declare_plan

    return declare_plan(params)


def _decompose_handler(params: dict) -> str:
    """UPGRADE-04: Content matrix decomposition — 1→N platform adaptation."""
    from .content_matrix import decompose_content

    asset_id = params.get("asset_id", "")
    platforms = params.get("platforms", [])
    if not asset_id:
        return json.dumps({"error": "asset_id required"}, ensure_ascii=False)
    if not platforms:
        return json.dumps({"error": "at least one platform required"}, ensure_ascii=False)

    _ensure_marketing_path()
    server = import_module("server")
    asset = server.get_content_asset({"asset_id": asset_id})
    if not asset:
        return json.dumps({"error": f"asset not found: {asset_id}"}, ensure_ascii=False)

    variants = decompose_content(asset, platforms)
    return json.dumps({
        "parent_id": asset_id,
        "variant_count": len(variants),
        "variants": variants,
    }, ensure_ascii=False, default=str)


DRAFT_TOOLS: list[ToolSpec] = [
    ToolSpec("marketing_plan_declare", CapabilityLevel.REVERSIBLE_WRITE,
             "声明或更新当前任务的结构化执行计划。开始调用其他工具前必须先声明计划；"
             "每步给出描述，若该步骤将调用某个工具则填写准确的 tool_name",
             _schema({
                 "steps": {
                     "type": "array",
                     "minItems": 1,
                     "maxItems": 12,
                     "items": {
                         "type": "object",
                         "properties": {
                             "description": {"type": "string", "description": "步骤描述"},
                             "tool_name": {"type": "string",
                                           "description": "该步骤要调用的工具名，纯思考/综合步骤留空"},
                         },
                         "required": ["description"],
                         "additionalProperties": False,
                     },
                 },
             }),
             _plan_declare_handler,
             ),
    ToolSpec("marketing_draft_memory_add", CapabilityLevel.REVERSIBLE_WRITE,
             "写入一条长期结构化记忆（用户偏好、账号DNA、项目上下文、复盘规律），自动过滤秘密信息；不要用它保存一次性脚本/完整文案草稿，内容草稿请使用 marketing_draft_content_create",
             _schema({
                 "kind": {"type": "string", "enum": ["user", "account", "episodic", "semantic", "procedural"]},
                 "content": {"type": "string", "description": "记忆内容"},
                 "account_id": {"type": "string", "description": "关联的账号ID"},
                 "platform": {"type": "string", "description": "关联的平台"},
                 "confidence": {"type": "number", "minimum": 0, "maximum": 1, "default": 0.8},
             }),
             _server_action("add_memory"),
             ),
    ToolSpec("marketing_draft_content_create", CapabilityLevel.REVERSIBLE_WRITE,
             "创建内容草稿（选题/脚本/视频/封面），可指定平台和账号",
             _schema({
                 "title": {"type": "string", "description": "内容标题"},
                 "type": {"type": "string", "enum": ["script", "video", "image", "caption"], "default": "script"},
                 "platform": {"type": "string", "description": "目标平台"},
                 "account_id": {"type": "string", "description": "关联的账号ID"},
                 "content": {"type": "object", "description": "内容正文/URL等"},
             }),
             _server_action("create_content_asset"),
             ),
    ToolSpec("marketing_draft_content_preflight", CapabilityLevel.REVERSIBLE_WRITE,
             "在内容生产前保存总预演记录：判断受众、证据、平台、成本和生产可行性；"
             "真人/数字人高质量视频只记录需要独立片子预演，不替代 video_core 的影像预演 Agent",
             _schema({
                 "objective": {"type": "string", "description": "用户原始内容生产目标"},
                 "kind": {
                     "type": "string",
                     "enum": ["auto", "article_soft", "faceless_video", "premium_human_video"],
                 },
                 "platforms": {
                     "type": "array",
                     "items": {
                         "type": "string",
                         "enum": ["douyin", "bilibili", "xiaohongshu", "kuaishou", "zhihu", "wechat_channels", "wechat_official", "tiktok", "youtube"],
                     },
                 },
                 "account_id": {"type": "string"},
                 "audience_context": {"type": "object"},
                 "evidence": {"type": "array", "items": {"type": "object"}},
                 "memory_refs": {"type": "array", "items": {"type": "string"}},
                 "receipt_refs": {"type": "array", "items": {"type": "string"}},
                 "asset_id": {"type": "string", "description": "可选；已有内容资产时绑定"},
             }),
             _server_action("create_content_preflight"),
             ),
    ToolSpec("marketing_draft_soft_article_create", CapabilityLevel.REVERSIBLE_WRITE,
             "根据软文生产工单生成并保存知乎/微信公众号长文资产：包含父稿、平台变体、证据状态、配图需求和发布前预测；"
             "会先运行统一总预演 PreflightDecision，不通过时只保存阻断草稿、不写发布前预测；"
             "不联网、不调用付费 API、不伪造证据，证据不足会标记 needs_evidence",
             _schema({
                 "objective": {"type": "string", "description": "用户原始软文目标或选题"},
                 "topic": {"type": "string", "description": "可选主题"},
                 "title": {"type": "string", "description": "可选标题"},
                 "platforms": {
                     "type": "array",
                     "items": {"type": "string", "enum": ["zhihu", "wechat_official"]},
                     "description": "目标平台，默认知乎和公众号",
                 },
                 "account_id": {"type": "string", "description": "可选账号 ID"},
                 "audience_context": {"type": "object", "description": "目标读者、痛点、承诺、CTA 等上下文"},
                 "memory_refs": {"type": "array", "items": {"type": "string"}},
                 "evidence": {
                     "type": "array",
                     "description": "已验证证据列表，至少应包含 title/summary/url；缺 URL 会被标记为待补证据",
                     "items": {"type": "object"},
                 },
             }),
             _server_action("create_soft_article_asset"),
             ),
    ToolSpec("marketing_draft_faceless_video_create", CapabilityLevel.REVERSIBLE_WRITE,
             "根据不露脸素材视频工单生成并保存视频草稿资产：包含旁白脚本、镜头清单、素材检索包、缺口生成请求、EDL 草案和发布前预测；"
             "会先运行统一总预演 PreflightDecision，不通过时只保存阻断草稿、不写发布前预测；"
             "不下载素材、不注册假附件、不渲染成片，素材和证据不足会阻断发布审核",
             _schema({
                 "objective": {"type": "string", "description": "用户原始视频目标或选题"},
                 "topic": {"type": "string", "description": "可选主题"},
                 "title": {"type": "string", "description": "可选标题"},
                 "platforms": {
                     "type": "array",
                     "items": {"type": "string", "enum": ["douyin", "wechat_channels", "bilibili"]},
                     "description": "目标平台，默认抖音/视频号/B站",
                 },
                 "account_id": {"type": "string", "description": "可选账号 ID"},
                 "audience_context": {"type": "object", "description": "目标观众、痛点、承诺、CTA 等上下文"},
                 "memory_refs": {"type": "array", "items": {"type": "string"}},
                 "evidence": {
                     "type": "array",
                     "description": "已验证证据列表，至少应包含 title/summary/url；缺 URL 会被标记为待补证据",
                     "items": {"type": "object"},
                 },
             }),
             _server_action("create_faceless_video_asset"),
             ),
    ToolSpec("marketing_draft_content_from_experiment", CapabilityLevel.REVERSIBLE_WRITE,
             "从账号内容实验生成生产草稿：读取实验假设、账号定位和受众上下文，自动选择软文或不露脸素材视频路线，"
             "创建内容资产并挂回 experiment；不发布、不下载素材、不调用付费视频 API，高阶视频会要求先走独立片子预演",
             _schema({
                 "account_id": {"type": "string", "description": "账号 ID"},
                 "project_id": {"type": "string", "description": "账号策略项目 ID；可留空使用当前 active project"},
                 "experiment_id": {"type": "string", "description": "账号内容实验 ID"},
                 "kind": {
                     "type": "string",
                     "enum": ["auto", "article_soft", "faceless_video", "premium_human_video"],
                     "description": "可选；auto 时根据实验指标和平台判断",
                 },
                 "platforms": {
                     "type": "array",
                     "items": {"type": "string", "enum": ["zhihu", "wechat_official", "douyin", "wechat_channels", "bilibili"]},
                     "description": "目标平台；不传则按 lane 默认",
                 },
                 "objective": {"type": "string", "description": "可选；覆盖由实验假设生成的生产目标"},
                 "topic": {"type": "string", "description": "可选主题"},
                 "title": {"type": "string", "description": "可选标题"},
                 "audience_context": {"type": "object", "description": "可选；覆盖账号生命周期推导出的受众上下文"},
                 "evidence": {
                     "type": "array",
                     "description": "可选证据列表；至少应包含 URL，否则生产草稿会被预演门阻断",
                     "items": {"type": "object"},
                 },
             }),
             _server_action("create_content_from_experiment"),
             ),
    ToolSpec("marketing_draft_content_decompose", CapabilityLevel.REVERSIBLE_WRITE,
             "将一条内容资产拆解为多平台适配版本（1→N）：自动调整标题长度、标签数量、CTA风格；"
             "返回各平台变体的适配参数和调整说明，不直接创建资产",
             _schema({
                 "asset_id": {"type": "string", "description": "源内容资产ID"},
                 "platforms": {
                     "type": "array",
                     "description": "目标平台列表",
                     "items": {"type": "string", "enum": ["douyin", "bilibili", "xiaohongshu", "kuaishou", "zhihu", "wechat_official"]},
                     "minItems": 1,
                     "maxItems": 6,
                 },
             }),
             _decompose_handler,
             ),
    ToolSpec("marketing_draft_content_review", CapabilityLevel.REVERSIBLE_WRITE,
             "对已有内容资产执行发布前结构化评分，并可写入不可变盲预测；只记录评审，不会自动发布或修改策略权重",
             _schema({
                 "asset_id": {"type": "string", "description": "内容资产 ID"},
                 "scores": {
                     "type": "object",
                     "description": "7 维评分，均为 0-10 整数",
                     "properties": {
                         "hook": {"type": "integer", "minimum": 0, "maximum": 10},
                         "topic": {"type": "integer", "minimum": 0, "maximum": 10},
                         "emotion": {"type": "integer", "minimum": 0, "maximum": 10},
                         "density": {"type": "integer", "minimum": 0, "maximum": 10},
                         "pacing": {"type": "integer", "minimum": 0, "maximum": 10},
                         "viewpoint": {"type": "integer", "minimum": 0, "maximum": 10},
                         "cta": {"type": "integer", "minimum": 0, "maximum": 10},
                         "title_bait_risk": {"type": "integer", "minimum": 0, "maximum": 10},
                         "controversy_overload_risk": {"type": "integer", "minimum": 0, "maximum": 10},
                     },
                     "required": ["hook", "topic", "emotion", "density", "pacing", "viewpoint", "cta", "title_bait_risk", "controversy_overload_risk"],
                     "additionalProperties": False,
                 },
                 "prediction": {
                     "type": "object",
                     "description": "发布前预测，如 expected_views/expected_completion_rate/expected_engagement_rate 的 low/mid/high 区间",
                 },
                 "notes": {"type": "string"},
             }),
             _server_action("review_content_asset"),
             ),
    ToolSpec("marketing_draft_weight_candidate_decide", CapabilityLevel.REVERSIBLE_WRITE,
             "接受或拒绝权重学习候选；接受前必须通过历史回放闸门，只改变候选状态，不直接改永久策略权重",
             _schema({
                 "candidate_id": {"type": "string", "description": "weight 类型学习候选 ID"},
                 "decision": {"type": "string", "enum": ["accepted", "rejected"]},
                 "reason": {"type": "string", "description": "用户/审阅者给出的原因"},
                 "window": {"type": "integer", "minimum": 1, "maximum": 500, "default": 50},
                 "min_support": {"type": "integer", "minimum": 1, "maximum": 20},
             }),
             _server_action("decide_weight_candidate"),
             ),
    ToolSpec("marketing_draft_audience_hypothesis", CapabilityLevel.REVERSIBLE_WRITE,
             "为指定账号建立或修订目标受众假设草案。只写草案，不把模型推断当真实粉丝画像；首次建立时需要 business_goal",
             _schema({
                 "account_id": {"type": "string"},
                 "business_goal": {"type": "string", "description": "首次建立账号战略时必填"},
                 "constraints": {"type": "object"},
                 "segments": {"type": "array", "minItems": 1, "items": {"type": "object"}},
                 "pains": {"type": "array", "items": {"type": "string"}},
                 "scenarios": {"type": "array", "items": {"type": "string"}},
                 "exclusions": {"type": "array", "items": {"type": "string"}},
                 "data_gaps": {"type": "array", "items": {"type": "string"}},
             }),
             _server_action("draft_audience_hypothesis")),
    ToolSpec("marketing_draft_bind_prospect_strategy", CapabilityLevel.REVERSIBLE_WRITE,
             "在用户明确确认后，把登录前通过自然对话形成的起号项目完整绑定到已连接账号；"
             "目标账号已有经营项目时拒绝覆盖，不会自动合并两套定位",
             _schema({
                 "account_id": {"type": "string", "description": "已连接的目标账号 ID"},
                 "project_id": {"type": "string", "description": "待绑定的 prospect 项目 ID"},
                 "prospect_account_id": {"type": "string", "description": "可选；默认当前用户的 prospect workspace"},
             }),
             _server_action("bind_prospect_strategy")),
    ToolSpec("marketing_draft_audience_confirm", CapabilityLevel.REVERSIBLE_WRITE,
             "确认用户已经看过并同意的目标受众草案；确认后旧版本保留并可由新版本取代，不能静默调用",
             _schema({
                 "account_id": {"type": "string"},
                 "project_id": {"type": "string"},
                 "hypothesis_id": {"type": "string"},
             }),
             _server_action("confirm_audience_hypothesis")),
    ToolSpec("marketing_draft_benchmark_add", CapabilityLevel.REVERSIBLE_WRITE,
             "向当前账号项目添加对标账号，必须说明选择理由和可追溯来源；不等于已经完成对标研究",
             _schema({
                 "account_id": {"type": "string"}, "project_id": {"type": "string"},
                 "platform": {"type": "string"}, "account_handle": {"type": "string"},
                 "account_name": {"type": "string"},
                 "relation": {"type": "string", "enum": ["direct", "adjacent", "aspirational", "negative"]},
                 "selection_reason": {"type": "string"}, "source_ref": {"type": "string"},
                 "selection_status": {"type": "string", "enum": ["candidate", "selected"], "default": "candidate"},
             }), _server_action("add_benchmark_account")),
    ToolSpec("marketing_draft_benchmark_discover", CapabilityLevel.REVERSIBLE_WRITE,
             "从产品已采集且带稳定作者身份的真实内容证据中发现对标候选；保存匹配依据和样本，"
             "不把热点标题冒充账号，不自动选中，也不自动指定 negative 对标",
             _schema({
                 "account_id": {"type": "string"}, "project_id": {"type": "string"},
                 "query": {"type": "string", "description": "行业、细分方向或受众关键词"},
                 "platform": {"type": "string", "enum": ["douyin", "bilibili"]},
                 "limit": {"type": "integer", "minimum": 1, "maximum": 20, "default": 10},
             }), _server_action("discover_benchmarks")),
    ToolSpec("marketing_draft_benchmark_decide", CapabilityLevel.REVERSIBLE_WRITE,
             "将对标候选标记为选中或拒绝；只有 selected 对标的观察可以推进账号定位",
             _schema({
                 "account_id": {"type": "string"}, "project_id": {"type": "string"},
                 "benchmark_account_id": {"type": "string"},
                 "decision": {"type": "string", "enum": ["selected", "rejected"]},
                 "relation": {"type": "string", "enum": ["direct", "adjacent", "aspirational", "negative"]},
             }), _server_action("decide_benchmark_account")),
    ToolSpec("marketing_draft_benchmark_observation", CapabilityLevel.REVERSIBLE_WRITE,
             "为已选对标账号记录一条结构化观察，必须携带来源、采集时间和置信度；模型推断不能冒充公开事实",
             _schema({
                 "account_id": {"type": "string"}, "project_id": {"type": "string"},
                 "benchmark_account_id": {"type": "string"},
                 "dimension": {"type": "string", "enum": ["audience", "positioning", "content_pillar", "format", "hook", "tone", "cadence", "engagement", "conversion", "gap"]},
                 "value": {"type": "object"}, "provenance": {"type": "object"},
                 "confidence": {"type": "number", "minimum": 0, "maximum": 1},
             }), _server_action("add_benchmark_observation")),
    ToolSpec("marketing_draft_benchmark_sample", CapabilityLevel.REVERSIBLE_WRITE,
             "为已选对标账号保存一个具体内容样本及其来源；样本是观察结论的证据，不下载媒体文件",
             _schema({
                 "account_id": {"type": "string"}, "project_id": {"type": "string"},
                 "benchmark_account_id": {"type": "string"}, "video_id": {"type": "string"},
                 "title": {"type": "string"}, "transcript": {"type": "string"},
                 "metrics": {"type": "object"}, "provenance": {"type": "object"},
             }), _server_action("add_benchmark_sample")),
    ToolSpec("marketing_draft_account_positioning", CapabilityLevel.REVERSIBLE_WRITE,
             "依据已确认受众和达标对标证据起草账号定位；必须引用本账号项目内的观察 ID，不会自动生效",
             _schema({
                 "account_id": {"type": "string"}, "project_id": {"type": "string"},
                 "positioning": {"type": "object"},
                 "evidence_refs": {"type": "array", "items": {"type": "string"}, "minItems": 1},
             }), _server_action("draft_positioning")),
    ToolSpec("marketing_draft_account_positioning_approve", CapabilityLevel.REVERSIBLE_WRITE,
             "确认用户已经审阅并同意的账号定位草案；生效后生成兼容 DNA，旧版本保留",
             _schema({
                 "account_id": {"type": "string"}, "project_id": {"type": "string"},
                 "positioning_id": {"type": "string"},
             }), _server_action("approve_positioning")),
    ToolSpec("marketing_draft_account_positioning_rollback", CapabilityLevel.REVERSIBLE_WRITE,
             "回滚到一个历史定位的内容，但创建新的回滚版本而不覆盖历史",
             _schema({
                 "account_id": {"type": "string"}, "project_id": {"type": "string"},
                 "target_positioning_id": {"type": "string"},
             }), _server_action("rollback_positioning")),
    ToolSpec("marketing_draft_account_experiment", CapabilityLevel.REVERSIBLE_WRITE,
             "在已批准账号定位下创建可证伪内容实验，必须明确单一变量、发布前预测和成功标准",
             _schema({
                 "account_id": {"type": "string"}, "project_id": {"type": "string"},
                 "hypothesis": {"type": "string"}, "variable": {"type": "object"},
                 "prediction": {"type": "object"}, "success_criteria": {"type": "object"},
             }), _server_action("create_account_experiment")),
    ToolSpec("marketing_draft_account_experiment_attach", CapabilityLevel.REVERSIBLE_WRITE,
             "将本账号内容资产绑定到一个实验；同一资产不能跨实验或跨账号复用",
             _schema({
                 "account_id": {"type": "string"}, "project_id": {"type": "string"},
                 "experiment_id": {"type": "string"}, "asset_id": {"type": "string"},
             }), _server_action("attach_account_experiment_asset")),
    ToolSpec("marketing_draft_strategy_candidate", CapabilityLevel.REVERSIBLE_WRITE,
             "基于实验复盘、受众差距、用户反馈或失败恢复提出策略候选；只提议，不直接修改定位和权重",
             _schema({
                 "account_id": {"type": "string"}, "project_id": {"type": "string"},
                 "trigger": {
                     "type": "string",
                     "enum": [
                         "experiment_retro", "audience_gap", "user_feedback",
                         "failure_recovery", "weight_candidate_replay",
                     ],
                 },
                 "proposal": {"type": "object"},
                 "evidence_refs": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                 "confidence": {"type": "number", "minimum": 0, "maximum": 1},
             }), _server_action("propose_strategy_candidate")),
    ToolSpec("marketing_draft_strategy_decide", CapabilityLevel.REVERSIBLE_WRITE,
             "记录用户对策略候选的接受或拒绝；拒绝必须保留原因，接受也不会绕过定位版本审批",
             _schema({
                 "account_id": {"type": "string"}, "project_id": {"type": "string"},
                 "candidate_id": {"type": "string"},
                 "decision": {"type": "string", "enum": ["accepted", "rejected"]},
                 "reason": {"type": "string"},
             }), _server_action("decide_strategy_candidate")),
]

EFFECT_TOOLS: list[ToolSpec] = [
    ToolSpec("marketing_effect_publish", CapabilityLevel.EXTERNAL_EFFECT,
             "将内容资产正式发布到目标平台；"
             "每次都需要用户逐次确认，不可被 session/永久授权跳过",
             _schema({
                 "asset_id": {"type": "string", "description": "发布的内容资产ID"},
                 "platform": {"type": "string", "description": "目标平台",
                              "enum": ["douyin", "bilibili", "xiaohongshu"]},
             }),
             _noop,
             requires_approval=True),
]


def all_tools() -> list[ToolSpec]:
    return [*READ_TOOLS, *DRAFT_TOOLS, *CONTROLLED_TOOLS, *EFFECT_TOOLS]


def tool_by_name(name: str) -> ToolSpec | None:
    return next((tool for tool in all_tools() if tool.name == name), None)
