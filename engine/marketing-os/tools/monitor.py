"""账号监控工具 — CDP 拉取 + 历史对比 + 反馈闭环

SocialOp Persona 专用:
  1. CDP 拉取账号实时数据
  2. 历史数据对比, 异常检测
  3. 反馈内容策略调整建议
"""

import json
import subprocess
import os
import time
from pathlib import Path
from datetime import datetime, timedelta

CHROME_WS = str(Path.home() / ".agents/skills/browsing/chrome-ws")
DATA_DIR = Path(os.environ.get(
    "MARKETING_OS_CONFIG_DIR",
    Path.home() / ".hermes" / "plugins" / "marketing-os" / "config",
)) / "monitor_data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

PLATFORM_SCRAPERS = {
    "douyin": {
        "profile_url_tpl": "https://www.douyin.com/user/{user_id}",
        "wait_s": 5,
        "extract_js": """
(() => {
    const stats = {};
    // 粉丝数
    const followerEl = document.querySelector('[data-e2e="follower-count"], .follower-count, [class*="follower"] span');
    if (followerEl) stats.followers = followerEl.textContent.trim();
    // 获赞
    const likeEl = document.querySelector('[data-e2e="like-count"], .like-count, [class*="like"] span');
    if (likeEl) stats.total_likes = likeEl.textContent.trim();
    // 最近视频
    const videos = [];
    document.querySelectorAll('[data-e2e="user-post-item"], .video-card, [class*="post-item"]').forEach((el, i) => {
        if (i >= 10) return;
        const title = el.querySelector('[data-e2e="post-desc"], .title, .desc')?.textContent?.trim();
        const views = el.querySelector('[data-e2e="post-view"], .play-count, [class*="play"]')?.textContent?.trim();
        const likes = el.querySelector('[data-e2e="post-like"], .like-count')?.textContent?.trim();
        if (title) videos.push({ title: title.substring(0, 60), views, likes });
    });
    stats.recent_videos = videos;
    return JSON.stringify(stats);
})()
"""
    },
    "bilibili": {
        "profile_url_tpl": "https://space.bilibili.com/{user_id}",
        "wait_s": 4,
        "extract_js": """
(() => {
    try {
        const stats = {};
        // B站空间页数据在 #app 的初始化数据里
        const appData = document.querySelector('#app')?.__vue__?.$store?.state;
        // 或者从页面 JSON 数据提取
        const scripts = document.querySelectorAll('script');
        scripts.forEach(s => {
            const m = s.textContent.match(/window\\.__INITIAL_STATE__\\s*=\\s*({.+?});/);
            if (m) {
                const data = JSON.parse(m[1]);
                const card = data?.card || {};
                stats.followers = card.fans || card.follower || '';
                stats.total_plays = card.archive?.view || '';
                stats.total_likes = card.likes || '';
            }
        });
        // 备选: 从页面文本提取
        if (!stats.followers) {
            const followerEl = document.querySelector('.h-fans, [class*=\"fans\"], [class*=\"follower\"]');
            if (followerEl) stats.followers = followerEl.textContent.trim();
        }
        return JSON.stringify(stats);
    } catch(e) { return JSON.stringify({error: e.message}); }
})()
"""
    },
}


def _cdp_fetch(ws_url: str, js: str, timeout: int = 20) -> str:
    """通过 chrome-ws 在标签页执行 JS"""
    result = subprocess.run(
        [CHROME_WS, "eval", ws_url, js],
        capture_output=True, text=True, timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(f"CDP eval 失败: {result.stderr[:200]}")
    raw = result.stdout.strip()
    try:
        data = json.loads(raw)
        if isinstance(data, str):
            data = json.loads(data)
    except (json.JSONDecodeError, TypeError):
        data = {}
    return data if isinstance(data, dict) else {}


def fetch_account_stats(platform: str, user_id: str) -> dict:
    """CDP 拉取账号实时数据"""
    config = PLATFORM_SCRAPERS.get(platform)
    if not config:
        return {"error": f"不支持的平台: {platform}"}

    url = config["profile_url_tpl"].format(user_id=user_id)

    ws = subprocess.run(
        [CHROME_WS, "new", url],
        capture_output=True, text=True, timeout=15,
    ).stdout.strip()

    if not ws.startswith("ws://"):
        return {"error": f"chrome-ws 连接失败: {ws[:100]}"}

    time.sleep(config["wait_s"])
    stats = _cdp_fetch(ws, config["extract_js"])
    subprocess.run([CHROME_WS, "close", ws], capture_output=True, timeout=5)

    stats["platform"] = platform
    stats["fetched_at"] = datetime.now().isoformat()
    return stats


def save_monitor_snapshot(account_id: str, data: dict):
    """保存监控快照"""
    file = DATA_DIR / f"{account_id}.jsonl"
    data["saved_at"] = datetime.now().isoformat()
    with open(file, "a") as f:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")


def load_monitor_history(account_id: str, days: int = 7) -> list[dict]:
    """加载历史监控数据"""
    file = DATA_DIR / f"{account_id}.jsonl"
    if not file.exists():
        return []
    cutoff = datetime.now() - timedelta(days=days)
    history = []
    with open(file) as f:
        for line in f:
            try:
                entry = json.loads(line)
                ts = entry.get("fetched_at", entry.get("saved_at", ""))
                if ts and datetime.fromisoformat(ts) > cutoff:
                    history.append(entry)
            except (json.JSONDecodeError, ValueError):
                continue
    return history


def analyze_account_trend(account_id: str, platform: str, user_id: str) -> dict:
    """分析账号趋势 — SocialOp 核心逻辑"""
    current = fetch_account_stats(platform, user_id)
    if "error" in current:
        return {"status": "error", **current}

    save_monitor_snapshot(account_id, current)

    history = load_monitor_history(account_id)
    alerts = []
    suggestions = []

    if len(history) >= 2:
        prev = history[-2]
        cur_followers = _parse_number(current.get("followers", "0"))
        prev_followers = _parse_number(prev.get("followers", "0"))

        if prev_followers > 0:
            growth = (cur_followers - prev_followers) / prev_followers
            if growth > 0.5:
                alerts.append({"level": "viral", "msg": f"粉丝暴涨 {growth*100:.0f}%，建议趁热点加大发布频率"})
                suggestions.append("【短期策略】趁流量红利期, 日更 3-5 条, 内容往热门方向靠")
            elif growth < 0:
                alerts.append({"level": "warning", "msg": f"粉丝下降 {abs(growth)*100:.1f}%"})
                suggestions.append("【止损策略】回顾近期内容质量, 暂停低互动内容线, 回归爆款公式")

        # 连续下降检测
        if len(history) >= 4:
            recent_4 = [_parse_number(h.get("followers", "0")) for h in history[-4:]]
            if all(recent_4[i] > recent_4[i+1] for i in range(3)):
                alerts.append({"level": "critical", "msg": "粉丝连续 4 次下降！需要立即调整策略"})
                suggestions.append("【紧急】暂停所有自动发布, 人工审核内容方向, 回看爆款视频特征")

        # 视频表现分析
        cur_videos = current.get("recent_videos", [])
        prev_videos = prev.get("recent_videos", [])
        if cur_videos and prev_videos:
            cur_avg = _avg_views(cur_videos)
            prev_avg = _avg_views(prev_videos)
            if prev_avg > 0 and cur_avg < prev_avg * 0.7:
                alerts.append({"level": "warning", "msg": f"近期视频播放量下降 {(1-cur_avg/prev_avg)*100:.0f}%"})
                suggestions.append("【内容策略】推荐回归以下方向: 教程类/共鸣类/热点解读类, 时长控制在 15-30s")

    return {
        "account_id": account_id,
        "platform": platform,
        "analyzed_at": datetime.now().isoformat(),
        "current_stats": current,
        "history_count": len(history),
        "alerts": alerts,
        "content_suggestions": suggestions,
    }


def _parse_number(s) -> float:
    """解析 '1.2万' '3,456' 等格式为数字"""
    if isinstance(s, (int, float)):
        return float(s)
    s = str(s).replace(",", "").replace(" ", "").strip()
    if not s:
        return 0
    try:
        if "万" in s:
            return float(s.replace("万", "")) * 10000
        if "亿" in s:
            return float(s.replace("亿", "")) * 100000000
        return float(s)
    except ValueError:
        return 0


def _avg_views(videos: list) -> float:
    views = [_parse_number(v.get("views", "0")) for v in videos]
    return sum(views) / len(views) if views else 0


# ---- Hermes 工具注册 ----

def monitor_account(params=None, **kwargs) -> str:
    """SocialOp: 监控单个账号"""
    p = params or {}
    result = analyze_account_trend(
        p.get("account_id", "unknown"),
        p.get("platform", "douyin"),
        p.get("user_id", ""),
    )
    return json.dumps(result, ensure_ascii=False)


def monitor_all(params=None, **kwargs) -> str:
    """SocialOp: 全量账号巡检"""
    from .account import _read_accounts_db
    db = _read_accounts_db()
    results = []
    for acct in db.get("accounts", []):
        uid = acct.get("user_id", acct.get("username", ""))
        if acct["status"] == "active" and uid:
            try:
                r = analyze_account_trend(acct["id"], acct["platform"], uid)
                results.append(r)
            except Exception as e:
                results.append({"account_id": acct["id"], "error": str(e)})

    # 汇总所有告警
    all_alerts = []
    all_suggestions = []
    for r in results:
        all_alerts.extend(r.get("alerts", []))
        all_suggestions.extend(r.get("content_suggestions", []))

    return json.dumps({
        "monitored_at": datetime.now().isoformat(),
        "accounts_checked": len(results),
        "total_alerts": len(all_alerts),
        "alerts": all_alerts,
        "content_strategy_feedback": all_suggestions,
    }, ensure_ascii=False)


def get_marketing_context(params=None, **kwargs) -> str:
    """Return the latest persisted desktop intelligence for chat channels."""
    config_dir = Path(os.environ.get(
        "MARKETING_OS_CONFIG_DIR",
        Path.home() / ".hermes" / "plugins" / "marketing-os" / "config",
    ))

    def read(name, fallback):
        try:
            return json.loads((config_dir / name).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return fallback

    limit = max(1, min(int((params or {}).get("limit", 10)), 20))
    trends = read("trending-cache.json", {})
    suggestions = read("suggestions-cache.json", {})
    accounts = read("accounts.json", {"accounts": []})
    report = read("intelligence-report.json", {"status": "never_run"})
    targets = read("intelligence-config.json", {})
    return json.dumps({
        "source": "marketing-os-desktop",
        "instruction": "基于以下真实数据回答；数据缺失或巡检失败时必须明确说明，不能编造。",
        "industries": targets.get("industries", []),
        "report": report,
        "trends": trends.get("top_trends", [])[:limit],
        "suggestions": suggestions.get("suggestions", [])[:limit],
        "accounts": [
            {
                "platform": item.get("platform"),
                "label": item.get("label"),
                "status": item.get("status"),
                "stats": item.get("stats", {}),
            }
            for item in accounts.get("accounts", [])
        ],
        "data_updated_at": trends.get("cached_at") or report.get("completed_at"),
    }, ensure_ascii=False)


TOOLS = [
    {
        "name": "monitor_account",
        "description": "SocialOp: CDP 拉取账号实时数据 + 历史对比 + 趋势分析 + 内容策略建议",
        "schema": {
            "type": "object",
            "properties": {
                "account_id": {"type": "string"},
                "platform": {"type": "string", "enum": ["douyin", "bilibili"]},
                "user_id": {"type": "string"},
            },
            "required": ["account_id", "platform", "user_id"],
        },
        "handler": monitor_account,
    },
    {
        "name": "monitor_all",
        "description": "SocialOp: 全量账号巡检, 生成告警 + 内容策略反馈",
        "schema": {"type": "object", "properties": {}},
        "handler": monitor_all,
    },
    {
        "name": "get_marketing_context",
        "description": "读取智能营销桌面端最新的行业热点、选题、巡检报告和账号指标。用户在微信/飞书询问今日热点、营销方案、账号异常或数据依据时，必须先调用此工具。只读，不执行发布。",
        "schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 20}},
        },
        "handler": get_marketing_context,
    },
]
