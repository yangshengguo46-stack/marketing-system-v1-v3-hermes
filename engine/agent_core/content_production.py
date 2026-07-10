"""Legacy compatibility planner for the old FastAPI desktop path.

New product behavior belongs to the Hermes-native implementation under
``runtime/hermes-agent/marketing_os/domains``. Keep this module stable only
until the old ``/agent/*`` desktop path is retired; do not add new production
policy, tools or state ownership here.

This module is deliberately deterministic and side-effect free.  It does not
call models, scrape the web, download assets, render media, or write the store.
Its job is to turn a user request into an auditable production work order that
the Hermes agent, the content factory UI, and future video providers can share.

The product has three delivery lanes, but they are not three isolated pipes.
They all draw from the same production capability pool:

1. ``article_soft`` — Zhihu / WeChat Official Account long-form soft articles.
2. ``faceless_video`` — no-face videos assembled from licensed web/stock assets.
3. ``premium_human_video`` — high-quality real/digital/AI-human videos backed by
   the independent ``video_core`` project canvas.

For example, a soft article can request a licensed cover image or a generated
illustration; a faceless video can ask the premium video lane to generate a
missing shot; and premium video can still use stock/reference materials for
B-roll.  The plan returned by this module therefore contains both the selected
lane and its shared capability pool.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from .content_skill_registry import recommended_skills_for_lane

ContentProductionKind = Literal[
    "article_soft",
    "faceless_video",
    "premium_human_video",
]

VALID_KINDS: set[str] = {"article_soft", "faceless_video", "premium_human_video"}

ARTICLE_PLATFORMS = {"zhihu", "wechat_official"}
SHORT_VIDEO_PLATFORMS = {
    "douyin", "bilibili", "xiaohongshu", "kuaishou",
    "wechat_channels", "tiktok", "youtube",
}
VALID_PLATFORMS = ARTICLE_PLATFORMS | SHORT_VIDEO_PLATFORMS


@dataclass(frozen=True)
class ProductionStep:
    id: str
    title: str
    owner: str
    purpose: str
    output: str
    tool_name: str | None = None
    status: str = "pending"
    approval: str = "none"


@dataclass(frozen=True)
class ProductionGate:
    name: str
    rule: str
    blocks_if_missing: bool = True


@dataclass(frozen=True)
class ProductionCapability:
    id: str
    label: str
    purpose: str
    registered_tools: list[str] = field(default_factory=list)
    backend_interfaces: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    cost: Literal["free_or_local", "may_need_key", "paid"] = "free_or_local"
    approval: str = "none"
    maturity: Literal["ready", "partial", "planned"] = "partial"


@dataclass(frozen=True)
class ProductionPlan:
    status: str
    kind: ContentProductionKind
    kind_label: str
    objective: str
    target_platforms: list[str]
    account_id: str | None
    content_asset_type: Literal["script", "video"]
    content_format: str
    recommended_next_action: str
    tool_sequence: list[str]
    capability_pool: dict[str, Any] = field(default_factory=dict)
    lane_contract: dict[str, Any] = field(default_factory=dict)
    steps: list[ProductionStep] = field(default_factory=list)
    gates: list[ProductionGate] = field(default_factory=list)
    outputs: dict[str, Any] = field(default_factory=dict)
    material_policy: dict[str, Any] = field(default_factory=dict)
    cost_policy: dict[str, Any] = field(default_factory=dict)
    recommended_skills: list[dict[str, Any]] = field(default_factory=list)
    fallback: dict[str, Any] = field(default_factory=dict)
    alternatives: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["steps"] = [asdict(step) for step in self.steps]
        data["gates"] = [asdict(gate) for gate in self.gates]
        return data


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _normalise_platforms(platforms: Any, kind: str | None = None) -> list[str]:
    if isinstance(platforms, str):
        raw = re.split(r"[,，、/\s]+", platforms)
    elif isinstance(platforms, (list, tuple, set)):
        raw = [str(item) for item in platforms]
    else:
        raw = []

    alias = {
        "公众号": "wechat_official",
        "微信公众号": "wechat_official",
        "微信公号": "wechat_official",
        "知乎": "zhihu",
        "抖音": "douyin",
        "b站": "bilibili",
        "哔哩哔哩": "bilibili",
        "视频号": "wechat_channels",
        "小红书": "xiaohongshu",
        "快手": "kuaishou",
    }
    result: list[str] = []
    for item in raw:
        value = alias.get(item.strip().lower(), item.strip().lower())
        if value in VALID_PLATFORMS and value not in result:
            result.append(value)

    if result:
        return result
    if kind == "article_soft":
        return ["zhihu", "wechat_official"]
    if kind in {"faceless_video", "premium_human_video"}:
        return ["douyin", "wechat_channels", "bilibili"]
    return []


def infer_content_kind(params: dict[str, Any] | str) -> ContentProductionKind:
    """Infer the production lane from request text, explicit kind and platform.

    Explicit ``kind`` wins.  Otherwise platform hints win for article platforms,
    then semantic hints.  The default is ``article_soft`` because it is the
    lowest-cost lane that can close a real draft loop before video providers are
    fully wired.
    """

    if isinstance(params, str):
        objective = params
        requested = ""
        platforms: list[str] = []
    else:
        requested = _text(params.get("kind") or params.get("content_kind")).lower()
        objective = _text(params.get("objective") or params.get("brief") or params.get("topic"))
        platforms = _normalise_platforms(params.get("platforms") or params.get("platform"))

    kind_aliases = {
        "article": "article_soft",
        "article_soft": "article_soft",
        "soft_article": "article_soft",
        "long_article": "article_soft",
        "soft": "article_soft",
        "faceless": "faceless_video",
        "faceless_video": "faceless_video",
        "material_video": "faceless_video",
        "compilation": "faceless_video",
        "premium": "premium_human_video",
        "premium_video": "premium_human_video",
        "premium_human_video": "premium_human_video",
        "human_video": "premium_human_video",
        "digital_human": "premium_human_video",
        "avatar_video": "premium_human_video",
    }
    if requested in kind_aliases:
        return kind_aliases[requested]  # type: ignore[return-value]

    text = objective.lower()
    if platforms and set(platforms).issubset(ARTICLE_PLATFORMS):
        return "article_soft"
    if any(marker in text for marker in ("知乎", "公众号", "公号", "软文", "长文", "文章", "推文")):
        return "article_soft"
    if any(marker in text for marker in ("数字人", "真人", "ai人", "ai 人", "口播", "高质量视频", "真人视频", "虚拟人")):
        return "premium_human_video"
    if any(marker in text for marker in ("不露脸", "找素材", "素材拼接", "混剪", "无脸", "空镜", "图库", "素材视频")):
        return "faceless_video"
    if platforms and any(platform in SHORT_VIDEO_PLATFORMS for platform in platforms):
        return "faceless_video"
    return "article_soft"


def _topic_terms(objective: str) -> list[str]:
    text = _text(objective)
    terms: list[str] = []
    for token in re.findall(r"[A-Za-z][A-Za-z0-9+\-.]{1,24}|[\u4e00-\u9fff]{2,12}", text):
        if token not in terms and token not in {"帮我", "生成", "制作", "内容", "视频", "文章", "一个", "一条"}:
            terms.append(token)
    return terms[:8] or ["账号定位", "行业热点", "用户痛点"]


def _base_alternatives(kind: str) -> list[dict[str, Any]]:
    labels = {
        "article_soft": "知乎/公众号软文",
        "faceless_video": "不露脸素材拼接视频",
        "premium_human_video": "真人/数字人高质量视频",
    }
    return [
        {"kind": candidate, "label": labels[candidate], "selected": candidate == kind}
        for candidate in ("article_soft", "faceless_video", "premium_human_video")
    ]


SHARED_CAPABILITIES: dict[str, ProductionCapability] = {
    "audience_context": ProductionCapability(
        "audience_context",
        "账号/受众上下文",
        "读取账号生命周期、定位、粉丝画像和历史偏好；没有账号时转自然对话补齐目标用户假设。",
        registered_tools=[
            "marketing_read_account_lifecycle",
            "marketing_read_account_positioning",
            "marketing_read_audience_snapshots",
            "marketing_read_memory_list",
        ],
        outputs=["target_reader", "account_dna", "positioning_gap"],
        maturity="ready",
    ),
    "evidence_research": ProductionCapability(
        "evidence_research",
        "证据/趋势研究",
        "用本地热点缓存、Firecrawl 和资料库生成可回链的事实证据，不用模型脑补数据。",
        registered_tools=["marketing_read_trends", "marketing_research_web_search"],
        backend_interfaces=["marketing_tools.firecrawl_provider"],
        outputs=["evidence_pack", "trend_context", "source_urls"],
        cost="may_need_key",
        maturity="ready",
    ),
    "copywriting": ProductionCapability(
        "copywriting",
        "文案/脚本写作",
        "把目标受众、证据和平台规则转成父稿、平台变体、旁白脚本和 CTA。",
        registered_tools=["marketing_draft_content_create", "marketing_draft_content_decompose"],
        outputs=["article_draft", "platform_variants", "voiceover_script", "shot_list"],
        maturity="partial",
    ),
    "stock_material": ProductionCapability(
        "stock_material",
        "授权素材检索",
        "优先找可授权图片、视频、音效和引用材料；保留 provider/source_url/author/license/hash。",
        registered_tools=["marketing_research_web_search"],
        backend_interfaces=["marketing_tools.stock_images", "Pexels/Pixabay/Unsplash/Freesound"],
        outputs=["licensed_images", "licensed_videos", "licensed_audio", "provenance"],
        cost="may_need_key",
        approval="license_check",
        maturity="partial",
    ),
    "generated_image": ProductionCapability(
        "generated_image",
        "生图/封面补齐",
        "当授权图不贴题或需要品牌化封面时，生成插图、封面、分镜参考图。",
        backend_interfaces=["future_image_generation_provider", "video_generate_image"],
        outputs=["cover_image", "inline_illustration", "storyboard_frame"],
        cost="paid",
        approval="cost_or_provider",
        maturity="planned",
    ),
    "generated_video": ProductionCapability(
        "generated_video",
        "生视频/缺口镜头补齐",
        "素材视频缺关键镜头时，按 EDL 只生成缺口镜头，而不是把整条视频都交给付费模型。",
        backend_interfaces=["engine.video_core", "video_submit_shot", "video_render"],
        outputs=["generated_shots", "animatic", "rendered_clip"],
        cost="paid",
        approval="cost_and_rights",
        maturity="planned",
    ),
    "audio_track": ProductionCapability(
        "audio_track",
        "配音/音乐/音效",
        "生成或检索旁白、BGM、音效点，和 EDL 时间轴绑定。",
        backend_interfaces=["future_tts_provider", "Freesound"],
        outputs=["voiceover_audio", "bgm", "sfx"],
        cost="may_need_key",
        approval="voice_or_music_rights",
        maturity="planned",
    ),
    "edl_render": ProductionCapability(
        "edl_render",
        "EDL/渲染",
        "把脚本、镜头、素材、字幕、音频组织成可恢复的时间线，并在 renderer 可用时输出 mp4。",
        backend_interfaces=["engine.video_core.edl", "FFmpeg/MoviePy renderer"],
        outputs=["edl", "animatic", "final_mp4"],
        maturity="partial",
    ),
    "review_learning": ProductionCapability(
        "review_learning",
        "质量评分/盲预测/学习",
        "发布前保存评分和不可变预测；发布后用真实指标校准账号偏好和策略权重。",
        registered_tools=["marketing_draft_content_review", "marketing_read_learning_status"],
        outputs=["rubric_score", "immutable_prediction", "learning_signal"],
        maturity="ready",
    ),
    "publish_feedback": ProductionCapability(
        "publish_feedback",
        "发布/回执/指标回收",
        "进入发布审批、保存回执、按 checkpoint 回收指标，把结果反馈给内容策略。",
        registered_tools=["marketing_read_publishing_tasks"],
        outputs=["publish_receipt", "metric_checkpoint", "retro_note"],
        approval="publish_action",
        maturity="partial",
    ),
}


LANE_CAPABILITY_MAP: dict[str, dict[str, list[str]]] = {
    "article_soft": {
        "required": ["audience_context", "evidence_research", "copywriting", "review_learning"],
        "optional": ["stock_material", "generated_image", "publish_feedback"],
    },
    "faceless_video": {
        "required": [
            "audience_context",
            "evidence_research",
            "copywriting",
            "stock_material",
            "edl_render",
            "review_learning",
        ],
        "optional": ["generated_image", "generated_video", "audio_track", "publish_feedback"],
    },
    "premium_human_video": {
        "required": [
            "audience_context",
            "copywriting",
            "generated_image",
            "generated_video",
            "edl_render",
            "review_learning",
        ],
        "optional": ["evidence_research", "stock_material", "audio_track", "publish_feedback"],
    },
}


def _capability_pool(kind: str) -> dict[str, Any]:
    lane = LANE_CAPABILITY_MAP[kind]
    ids = lane["required"] + [item for item in lane["optional"] if item not in lane["required"]]
    return {
        "model": "shared_capability_pool",
        "required": lane["required"],
        "optional": lane["optional"],
        "capabilities": {capability_id: asdict(SHARED_CAPABILITIES[capability_id]) for capability_id in ids},
        "composition_rules": [
            "内容资产是唯一交付真相源：脚本、文章、图片、素材、EDL、回执都挂到 content_assets。",
            "软文可以调用 stock_material 或 generated_image 补封面/插图，但必须记录来源或生成参数。",
            "素材视频优先用授权素材；缺关键镜头时才请求 generated_image/generated_video 补齐，不整条烧钱。",
            "高级视频可复用 evidence_research 和 stock_material 做参考/B-roll，但正片生成必须走成本和权利审批。",
            "完整草稿不进入长期记忆；长期记忆只沉淀偏好、账号 DNA、成功流程和失败恢复方式。",
        ],
    }


def _lane_contract(kind: str) -> dict[str, Any]:
    return {
        "selected_lane": kind,
        "is_silo": False,
        "shared_flow": [
            "audience_context",
            "evidence_or_reference",
            "draft_or_script",
            "visual_or_media_support",
            "review_prediction",
            "publish_feedback",
        ],
        "handoff_policy": {
            "article_to_visual": "软文需要封面/配图时先找授权素材，再考虑生图。",
            "faceless_to_generated_media": "素材视频缺镜头时只生成缺口镜头，并保留成本/授权记录。",
            "premium_to_stock": "高级视频可用授权素材做参考或 B-roll，不把外部素材伪装成原创生成。",
        },
        "shared_editing_engine": {
            "applies_to": ["faceless_video", "premium_human_video"],
            "module": "engine.video_core.editing_engine",
            "single_source_of_truth": "EDL",
            "rule": "素材/AI 生成镜头/代码视觉素材都先转为素材资产引用，再填入同一条时间线。",
        },
    }


def _article_plan(objective: str, platforms: list[str], account_id: str | None) -> ProductionPlan:
    terms = _topic_terms(objective)
    steps = [
        ProductionStep(
            "A1", "确认读者与转化目标", "Agent",
            "先读取账号生命周期/定位；没有账号时用自然对话补齐目标读者、信任背书和转化动作。",
            "target_reader + promise + CTA", "marketing_read_account_lifecycle",
        ),
        ProductionStep(
            "A2", "检索公开证据", "Researcher",
            "用 Firecrawl 或本地资料库找行业事实、案例、产品页和可引用数据；只保留带 URL 的证据。",
            "evidence_pack", "marketing_research_web_search",
        ),
        ProductionStep(
            "A3", "搭软文骨架", "Writer",
            "按痛点/误区/方法/案例/行动建议组织，不直接硬广；知乎更重论证，公众号更重信任。",
            "outline",
        ),
        ProductionStep(
            "A4", "判断封面与插图需求", "Visual researcher",
            "软文不是纯文字烟囱：需要封面、产品图或解释图时，先找授权图；找不到再生成插图/封面。",
            "visual_brief + cover_or_inline_visuals", "marketing_research_web_search",
        ),
        ProductionStep(
            "A5", "写平台初稿", "Writer",
            "先产一篇父稿，再生成知乎版和公众号版标题、摘要、正文、CTA，并保存为可审稿内容资产。",
            "draft_body + platform_variants + content_asset", "marketing_draft_soft_article_create",
        ),
        ProductionStep(
            "A6", "拆成平台变体", "Agent",
            "用平台矩阵规则限制标题长度、标签、CTA 语气，避免一稿硬贴所有平台。",
            "zhihu/wechat_official variants", "marketing_draft_content_decompose",
        ),
        ProductionStep(
            "A7", "发布前评分与预测", "Blind reviewer",
            "写入 7 维评分、负面风险和发布前预测；后续发布后才能复盘校准。",
            "rubric_score + immutable_prediction", "marketing_draft_content_review",
        ),
    ]
    gates = [
        ProductionGate("事实证据门", "涉及数据、案例、产品承诺时必须有 evidence URL；无证据就改成观点或删除。"),
        ProductionGate("平台语气门", "知乎不得过度销售；公众号可以转化但必须先建立信任。"),
        ProductionGate("记忆边界门", "完整软文草稿保存到 content_assets，不写入长期记忆。"),
    ]
    return ProductionPlan(
        status="ready",
        kind="article_soft",
        kind_label="知乎/公众号软文",
        objective=objective,
        target_platforms=platforms or ["zhihu", "wechat_official"],
        account_id=account_id,
        content_asset_type="script",
        content_format="long_article",
        recommended_next_action="先跑软文，因为它成本最低、最快能形成真实可审稿资产。",
        tool_sequence=[
            "marketing_read_account_lifecycle",
            "marketing_research_web_search",
            "marketing_draft_soft_article_create",
            "marketing_draft_content_decompose",
            "marketing_draft_content_review",
        ],
        capability_pool=_capability_pool("article_soft"),
        lane_contract=_lane_contract("article_soft"),
        steps=steps,
        gates=gates,
        outputs={
            "asset_content_shape": {
                "production_kind": "article_soft",
                "topic_terms": terms,
                "outline": [],
                "draft_body": "",
                "platform_variants": ["zhihu", "wechat_official"],
                "evidence_refs": [],
                "visual_brief": "",
                "cover_image": {},
                "inline_image_requirements": [],
            }
        },
        material_policy={
            "external_materials": "text evidence + optional licensed/generative images",
            "requires_license_check": True,
            "license_check_scope": "only when cover/inline images/audio/video are attached",
            "optional_visual_sources": ["stock_material", "generated_image"],
        },
        cost_policy={"paid_api_required": False, "expected_cash_cost": 0},
        recommended_skills=recommended_skills_for_lane("article_soft"),
        fallback={"if_no_account": "通过自然对话先确认目标读者和变现假设，不要求登录。"},
        alternatives=_base_alternatives("article_soft"),
    )


def _faceless_plan(objective: str, platforms: list[str], account_id: str | None) -> ProductionPlan:
    terms = _topic_terms(objective)
    material_queries = [f"{term} 竖屏 素材" for term in terms[:4]]
    steps = [
        ProductionStep(
            "F1", "确认账号定位与选题证据", "Agent",
            "读取账号生命周期、热点和历史表现；没有定位时先按探索池生成，不冒充适合当前账号。",
            "brief + evidence_pack", "marketing_read_account_lifecycle",
        ),
        ProductionStep(
            "F2", "写 45-90 秒脚本", "Screenwriter",
            "按开头钩子、三段论、反转/利益点、CTA 写旁白；每 3-5 秒一个画面需求。",
            "voiceover_script",
        ),
        ProductionStep(
            "F3", "生成素材检索包", "Material researcher",
            "把每个镜头拆成可检索的关键词；优先 Pexels/Pixabay/Unsplash/Freesound 等可授权来源，缺关键镜头再申请生图/生视频补齐。",
            "material_query_pack", "marketing_research_web_search",
        ),
        ProductionStep(
            "F4", "导入素材并保留凭证", "Asset manager",
            "图片/视频必须有 provider、source_url、author、license、download hash；禁止从社交平台盗搬。",
            "licensed_media_attachments", "marketing_draft_content_create",
        ),
        ProductionStep(
            "F5", "生成 EDL 草案", "Editor",
            "按旁白时间轴排镜头、字幕、BGM、音效点和缺口镜头；先产可读 EDL，再由渲染器合成。",
            "edl_draft + generated_asset_requests",
        ),
        ProductionStep(
            "F6", "保存视频资产草稿", "Agent",
            "把脚本、素材清单、EDL 和缺口保存为 video content asset；渲染未完成时不伪造成片。",
            "video_asset_draft", "marketing_draft_faceless_video_create",
        ),
        ProductionStep(
            "F7", "评分与盲预测", "Blind reviewer",
            "发布前记录钩子、节奏、信息密度、风险和预测，后续指标回收才有校准意义。",
            "rubric_score + immutable_prediction", "marketing_draft_content_review",
        ),
    ]
    gates = [
        ProductionGate("版权/来源门", "每个外部素材必须有授权来源和可回链 URL；没有凭证不能进入资产。"),
        ProductionGate("素材适配门", "素材必须服务旁白，不允许只堆漂亮空镜。"),
        ProductionGate("渲染诚实门", "FFmpeg/Renderer 未产出文件前，只能称为视频草稿/EDL，不称为成片。"),
    ]
    return ProductionPlan(
        status="ready",
        kind="faceless_video",
        kind_label="不露脸素材拼接视频",
        objective=objective,
        target_platforms=platforms or ["douyin", "wechat_channels", "bilibili"],
        account_id=account_id,
        content_asset_type="video",
        content_format="faceless_compilation",
        recommended_next_action="先把脚本、素材检索包和 EDL 做出来；真实渲染器/图库视频源接上后即可合成。",
        tool_sequence=[
            "marketing_read_account_lifecycle",
            "marketing_read_trends",
            "marketing_research_web_search",
            "marketing_draft_faceless_video_create",
            "marketing_draft_content_review",
        ],
        capability_pool=_capability_pool("faceless_video"),
        lane_contract=_lane_contract("faceless_video"),
        steps=steps,
        gates=gates,
        outputs={
            "asset_content_shape": {
                "production_kind": "faceless_video",
                "topic_terms": terms,
                "script": "",
                "shot_list": [],
                "material_queries": material_queries,
                "licensed_assets": [],
                "generated_asset_requests": [],
                "b_roll_strategy": "licensed stock first; generated shots only for missing critical scenes",
                "edl": {},
            }
        },
        material_policy={
            "external_materials": "free/licensed stock + cited public web + optional generated gap-fill shots",
            "requires_license_check": True,
            "default_queries": material_queries,
            "optional_generated_sources": ["generated_image", "generated_video"],
        },
        cost_policy={"paid_api_required": False, "expected_cash_cost": 0, "may_need_stock_api_key": True},
        recommended_skills=recommended_skills_for_lane("faceless_video"),
        fallback={"if_no_stock_key": "先保存脚本、镜头清单和素材关键词；用户配置图库 Key 后补素材。"},
        alternatives=_base_alternatives("faceless_video"),
    )


def _premium_plan(objective: str, platforms: list[str], account_id: str | None) -> ProductionPlan:
    terms = _topic_terms(objective)
    steps = [
        ProductionStep(
            "P1", "创建视频项目画布", "Director",
            "在 video_core Project 中保存 brief、目标平台、时长、风格和账号上下文；项目可恢复、可接管。",
            "video_project_canvas",
        ),
        ProductionStep(
            "P2", "剧组制分工", "Director",
            "调度编剧、剪辑师、美术、音效、制片人、摄影、场记等角色，只通过画布通信。",
            "crew_plan",
        ),
        ProductionStep(
            "P3", "先出动态样片", "Editor + Art",
            "低成本出 script、storyboard、TTS、animatic，不直接烧钱生成正片。",
            "animatic_v0",
        ),
        ProductionStep(
            "P4", "预算与一次审批", "Producer",
            "估算 Seedream/Seedance/TTS/重试预算；用户看样片和预算后再进入正片。",
            "budget + approval_request",
        ),
        ProductionStep(
            "P5", "批量生成镜头", "Cinematographer",
            "按时间线 fan-out 提交图生/文生/参考图视频任务，Poller fan-in 收割。",
            "generated_shots",
        ),
        ProductionStep(
            "P6", "盲评与连续性检查", "Continuity",
            "独立检查单镜头质量、人物/场景一致性、相邻镜头穿帮。",
            "qc_report",
        ),
        ProductionStep(
            "P7", "终剪与反馈定位", "Editor + Director",
            "渲染 final mp4；用户反馈按 EDL/shot/asset/structure 四级定位，最小成本修改。",
            "final_video + revision_plan",
        ),
    ]
    gates = [
        ProductionGate("成本审批门", "进入 Seedream/Seedance 正片前必须有预算和用户批准。"),
        ProductionGate("肖像/声音权利门", "真人/数字人/AI 人涉及肖像、声音、素材授权，必须逐项确认。"),
        ProductionGate("Provider 校准门", "VolcengineAdapter 真实字段和价格未校准前不能声称可生成成片。"),
    ]
    return ProductionPlan(
        status="blocked_on_provider_calibration",
        kind="premium_human_video",
        kind_label="真人/数字人高质量视频",
        objective=objective,
        target_platforms=platforms or ["douyin", "wechat_channels", "bilibili"],
        account_id=account_id,
        content_asset_type="video",
        content_format="premium_human_video_project",
        recommended_next_action="先产视频项目画布与动态样片；真实 API Key/价格/字段校准后再开放正片生成。",
        tool_sequence=[
            "video_project_read/write",
            "video_estimate_cost",
            "video_gate_request",
            "video_generate_image",
            "video_submit_shot",
            "video_render",
        ],
        capability_pool=_capability_pool("premium_human_video"),
        lane_contract=_lane_contract("premium_human_video"),
        steps=steps,
        gates=gates,
        outputs={
            "asset_content_shape": {
                "production_kind": "premium_human_video",
                "topic_terms": terms,
                "video_project_id": "",
                "animatic_path": "",
                "budget": {},
                "reference_assets": [],
                "generated_asset_plan": {},
                "final_path": "",
            }
        },
        material_policy={
            "external_materials": "licensed/user-supplied reference assets + optional stock B-roll + generated shots",
            "requires_license_check": True,
            "requires_portrait_voice_rights": True,
            "optional_reference_sources": ["evidence_research", "stock_material"],
        },
        cost_policy={"paid_api_required": True, "requires_human_approval": True, "provider": "volcengine/seedance"},
        recommended_skills=recommended_skills_for_lane("premium_human_video"),
        fallback={"if_provider_unavailable": "降级为 faceless_video：保留脚本、EDL、授权素材，先交付不露脸版本。"},
        alternatives=_base_alternatives("premium_human_video"),
    )


def build_content_production_plan(params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a production work order for one of the three product lanes."""

    params = dict(params or {})
    objective = _text(
        params.get("objective")
        or params.get("brief")
        or params.get("topic")
        or "生产一条可发布内容"
    )
    kind = infer_content_kind(params)
    platforms = _normalise_platforms(params.get("platforms") or params.get("platform"), kind)
    account_id = _text(params.get("account_id")) or None

    if kind == "article_soft":
        plan = _article_plan(objective, platforms, account_id)
    elif kind == "faceless_video":
        plan = _faceless_plan(objective, platforms, account_id)
    else:
        plan = _premium_plan(objective, platforms, account_id)
    return plan.to_dict()
