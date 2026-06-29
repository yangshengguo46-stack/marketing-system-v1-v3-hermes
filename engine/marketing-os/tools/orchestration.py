"""内容生产编排工具 — 七工具流水线调度

Phase 1: 输入抓取 (Agent Reach / Open CLI / baoyu-url-to-markdown)
Phase 2: 深度研究 (NotebookLM)
Phase 3: 内容创作 (Writer + Humanizer-zh + baoyu-illustrator)
Phase 4: 多媒体生成 (Listenhub / Remotion / aPaaS)
Phase 5: 发布分发 (baoyu-post-*)
"""

import json
import subprocess
import shutil
from datetime import datetime
from pathlib import Path


def _check_cmd(cmd: str) -> bool:
    return shutil.which(cmd) is not None


# ---- Phase 1: 输入抓取 ----

def ingest_hot_topics(params=None, **kwargs) -> str:
    """Phase 1 统一入口 — 自动选择最佳抓取工具"""
    platforms = (params or {}).get("platforms", ["douyin", "weibo", "bilibili"])
    results = {}
    from .scraping import _fetch_with_backend

    for p in platforms:
        fetched = _fetch_with_backend(p, 30)
        results[p] = {
            "backend": fetched.get("backend_used"),
            "data": fetched.get("data", []),
            **({"error": fetched["error"]} if fetched.get("error") else {}),
        }

    return json.dumps({
        "phase": "ingest",
        "timestamp": datetime.now().isoformat(),
        "platforms": platforms,
        "results": results,
    }, ensure_ascii=False)


def _ingest_via_agent_reach(platform: str) -> dict:
    import agent_reach
    result = agent_reach.search(platform=platform, mode="hot", limit=30)
    data = json.loads(result) if isinstance(result, str) else result
    items = data if isinstance(data, list) else data.get("data", data.get("list", []))
    return {"backend": "agent_reach", "count": len(items), "data": items}


def _ingest_via_opencli(platform: str) -> dict:
    cmd = ["npx", "opencli", platform, "--hot", "--limit", "30", "--json"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode == 0:
        data = json.loads(result.stdout)
        return {"backend": "opencli", "count": len(data) if isinstance(data, list) else 0, "data": data}
    return {"backend": "opencli", "error": result.stderr[:200]}


# ---- Phase 2: 深度研究 ----

def deep_research_notebooklm(params=None, **kwargs) -> str:
    """Phase 2: 调用 NotebookLM 深度研究热点

    params.topics: 热点列表
    params.user_profile: 用户画像
    """
    topics = (params or {}).get("topics", [])
    if isinstance(topics, str):
        topics = json.loads(topics)

    # 检查 notebooklm-py 可用性
    if _check_cmd("notebooklm"):
        return _research_via_notebooklm_cli(topics)
    else:
        return json.dumps({
            "phase": "research",
            "status": "not_available",
            "message": "notebooklm-py 未安装: pip install notebooklm-py",
            "topics_count": len(topics),
        }, ensure_ascii=False)


def _research_via_notebooklm_cli(topics):
    results = []
    for t in topics[:5]:  # 限制深度研究数量
        try:
            r = subprocess.run(
                ["notebooklm", "research", "--query", t.get("title", ""), "--format", "brief"],
                capture_output=True, text=True, timeout=120,
            )
            results.append({
                "topic": t.get("title"),
                "status": "done" if r.returncode == 0 else "failed",
                "brief": r.stdout[:500] if r.returncode == 0 else r.stderr[:200],
            })
        except Exception as e:
            results.append({"topic": t.get("title"), "error": str(e)})

    return json.dumps({
        "phase": "research",
        "tool": "notebooklm",
        "results": results,
    }, ensure_ascii=False)


# ---- Phase 3: 内容创作 ----

def create_content_pipeline(params=None, **kwargs) -> str:
    """Phase 3: Writer + Humanizer-zh + baoyu 配图 统一流水线

    params.script: 脚本文本
    params.style: 内容风格
    params.humanize: 是否去AI味 (默认true)
    params.illustrate: 是否配图 (默认true)
    """
    script = (params or {}).get("script", "")
    style = (params or {}).get("style", "教学型")
    humanize = (params or {}).get("humanize", True)
    illustrate = (params or {}).get("illustrate", True)

    pipeline_result = {"phase": "creation", "steps": []}

    # Step 1: Writer Persona 生成初稿 (由 agent 通过 generate_content_suggestions 完成)
    pipeline_result["steps"].append({"step": "writer_draft", "status": "pending_agent"})

    # Step 2: Humanizer-zh 去AI味
    if humanize and script:
        pipeline_result["steps"].append({
            "step": "humanize",
            "instruction": f"使用 humanizer-zh skill 处理以下文本:\\n```\\n{script[:500]}\\n```\\n\\n要求: 评分≥40分，重点优化节奏和真实性维度",
            "tool": "humanizer-zh",
            "install": "npx skills add https://github.com/op7418/Humanizer-zh.git",
        })

    # Step 3: baoyu 配图
    if illustrate:
        pipeline_result["steps"].append({
            "step": "illustrate",
            "tool": "baoyu-article-illustrator",
            "instruction": "为主题生成配图和信息图",
            "install": "npx skills add jimliu/baoyu-skills --skill baoyu-article-illustrator",
        })
        pipeline_result["steps"].append({
            "step": "cover_image",
            "tool": "baoyu-cover-image",
            "instruction": f"生成{style}风格封面图",
            "install": "npx skills add jimliu/baoyu-skills --skill baoyu-cover-image",
        })

    return json.dumps(pipeline_result, ensure_ascii=False)


# ---- Phase 4: 多媒体生成 ----

def generate_media(params=None, **kwargs) -> str:
    """Phase 4: 多媒体生成路由

    根据内容类型自动选择: Listenhub(播客/TTS) / Remotion(代码视频) / aPaaS(短视频)
    """
    media_type = (params or {}).get("type", "podcast")
    content = (params or {}).get("content", "")

    if media_type == "podcast":
        return _generate_podcast(content)
    elif media_type == "tts":
        return _generate_tts(content)
    elif media_type == "video_remotion":
        return _generate_video_remotion(content)
    elif media_type == "video_short":
        return _generate_video_apaas(content)
    else:
        return json.dumps({"error": f"未知媒体类型: {media_type}"}, ensure_ascii=False)


def _generate_podcast(content):
    if _check_cmd("listenhub"):
        return json.dumps({
            "tool": "listenhub",
            "command": f"listenhub podcast create --query '{content[:200]}' --language zh --mode deep",
            "status": "ready_to_execute",
        }, ensure_ascii=False)
    return json.dumps({
        "tool": "listenhub",
        "status": "not_installed",
        "install": "npm install -g @marswave/listenhub-cli",
    }, ensure_ascii=False)


def _generate_tts(content):
    if _check_cmd("listenhub"):
        return json.dumps({
            "tool": "listenhub",
            "command": f"listenhub tts create --text '{content[:200]}' --language zh",
            "status": "ready_to_execute",
        }, ensure_ascii=False)
    return json.dumps({"tool": "listenhub", "status": "not_installed"}, ensure_ascii=False)


def _generate_video_remotion(content):
    return json.dumps({
        "tool": "remotion",
        "status": "needs_agent_execution",
        "instruction": f"使用 Remotion (React) 创建视频: {content[:200]}",
        "install": "npx create-video@latest",
    }, ensure_ascii=False)


def _generate_video_apaas(content):
    """ACP 协议调用 aPaaS 短视频智能体"""
    return json.dumps({
        "tool": "apaas",
        "protocol": "ACP",
        "status": "reserved",
        "instruction": f"通过 ACP 委托 aPaaS 短视频生成: {content[:200]}",
    }, ensure_ascii=False)


# ---- Phase 5: 发布分发 ----

def publish_content(params=None, **kwargs) -> str:
    """Phase 5: 多平台发布

    params.platforms: 目标平台
    params.content: 发布内容
    params.images: 配图列表
    """
    platforms = (params or {}).get("platforms", [])
    content = (params or {}).get("content", "")
    images = (params or {}).get("images", [])

    publish_plan = []

    for p in platforms:
        if p == "wechat":
            publish_plan.append({
                "platform": "wechat",
                "tool": "baoyu-post-to-wechat",
                "install": "npx skills add jimliu/baoyu-skills --skill baoyu-post-to-wechat",
            })
        elif p == "weibo":
            publish_plan.append({
                "platform": "weibo",
                "tool": "baoyu-post-to-weibo",
                "install": "npx skills add jimliu/baoyu-skills --skill baoyu-post-to-weibo",
            })
        elif p in ("douyin", "bilibili"):
            publish_plan.append({
                "platform": p,
                "tool": "manual",
                "note": "短视频平台需在创作工作台手动发布或通过 aPaaS 自动发布",
            })

    return json.dumps({
        "phase": "publish",
        "plan": publish_plan,
        "content_length": len(content),
        "images_count": len(images),
        "timestamp": datetime.now().isoformat(),
    }, ensure_ascii=False)


# ---- 流水线状态查询 ----

def pipeline_status(params=None, **kwargs) -> str:
    """查询整条生产流水线的工具可用性"""
    tools_status = {
        "phase1_ingest": {
            "agent_reach": _check_import("agent_reach"),
            "open_cli": _check_cmd("npx"),
            "marketing_os_backends": True,  # 内置
        },
        "phase2_research": {
            "notebooklm_cli": _check_cmd("notebooklm"),
            "open_notebook": _check_cmd("docker"),  # open-notebook 需 Docker
        },
        "phase3_creation": {
            "humanizer_zh": _check_cmd("npx"),  # npx skills add ...
            "baoyu_skills": _check_cmd("npx"),
            "marketing_os_writer": True,  # 内置
        },
        "phase4_media": {
            "listenhub": _check_cmd("listenhub"),
            "remotion": _check_cmd("npx"),
            "apaas": "reserved",  # ACP 预留
        },
        "phase5_publish": {
            "baoyu_post": _check_cmd("npx"),
            "socialop_monitor": True,  # 内置
        },
        "checked_at": datetime.now().isoformat(),
    }
    return json.dumps(tools_status, ensure_ascii=False)


def _check_import(module_name: str) -> bool:
    try:
        __import__(module_name)
        return True
    except ImportError:
        return False


TOOLS = [
    {
        "name": "ingest_hot_topics",
        "description": "Phase 1: 自动选择最佳后端(Agent Reach > Open CLI > 内置)抓取多平台热搜",
        "schema": {
            "type": "object",
            "properties": {
                "platforms": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "目标平台列表"
                }
            }
        },
        "handler": ingest_hot_topics,
    },
    {
        "name": "deep_research_notebooklm",
        "description": "Phase 2: 使用 NotebookLM 对热点进行深度研究",
        "schema": {
            "type": "object",
            "properties": {
                "topics": {"type": "array", "items": {"type": "object"}, "description": "热点列表"},
            }
        },
        "handler": deep_research_notebooklm,
    },
    {
        "name": "create_content_pipeline",
        "description": "Phase 3: Writer + Humanizer-zh + baoyu配图 内容创作流水线",
        "schema": {
            "type": "object",
            "properties": {
                "script": {"type": "string", "description": "脚本文本"},
                "style": {"type": "string", "description": "内容风格"},
                "humanize": {"type": "boolean", "description": "是否去AI味"},
                "illustrate": {"type": "boolean", "description": "是否配图"},
            }
        },
        "handler": create_content_pipeline,
    },
    {
        "name": "generate_media",
        "description": "Phase 4: 多媒体生成路由 (Listenhub/Remotion/aPaaS)",
        "schema": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": ["podcast", "tts", "video_remotion", "video_short"]},
                "content": {"type": "string"},
            },
            "required": ["type", "content"]
        },
        "handler": generate_media,
    },
    {
        "name": "publish_content",
        "description": "Phase 5: 多平台一键发布 (baoyu-post)",
        "schema": {
            "type": "object",
            "properties": {
                "platforms": {"type": "array", "items": {"type": "string"}},
                "content": {"type": "string"},
                "images": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["platforms", "content"]
        },
        "handler": publish_content,
    },
    {
        "name": "pipeline_status",
        "description": "查询整条生产流水线的工具可用性状态",
        "schema": {"type": "object", "properties": {}},
        "handler": pipeline_status,
    },
]
