"""Read-only marketing monitoring over Electron-supplied snapshots.

This module never launches or controls a browser.  Electron owns platform
sessions and pushes sanitized metrics into ``accounts.json``; the marketing
engine only compares persisted snapshots and produces explainable alerts.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path


def _default_config_dir() -> Path:
    return Path.home() / "Library" / "Application Support" / "marketing-os-desktop" / "config"


CONFIG_DIR = Path(os.environ.get("MARKETING_OS_CONFIG_DIR", _default_config_dir()))
DATA_DIR = CONFIG_DIR / "monitor_data"


def _parse_number(value) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value or "").replace(",", "").replace(" ", "").strip()
    if not text:
        return 0
    try:
        if "万" in text:
            return float(text.replace("万", "")) * 10_000
        if "亿" in text:
            return float(text.replace("亿", "")) * 100_000_000
        return float(text)
    except ValueError:
        return 0


def save_monitor_snapshot(account_id: str, data: dict, data_dir: Path | None = None) -> None:
    target_dir = data_dir or DATA_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{account_id}.jsonl"
    payload = {**data, "saved_at": datetime.now().isoformat(), "source": "electron_session"}
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def load_monitor_history(account_id: str, days: int = 30, data_dir: Path | None = None) -> list[dict]:
    target = (data_dir or DATA_DIR) / f"{account_id}.jsonl"
    if not target.exists():
        return []
    cutoff = datetime.now() - timedelta(days=days)
    history = []
    for line in target.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
            stamp = item.get("updated_at") or item.get("saved_at")
            if stamp and datetime.fromisoformat(stamp) >= cutoff:
                history.append(item)
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
    return history


def analyze_account_snapshot(
    account_id: str,
    platform: str,
    current: dict,
    *,
    persist: bool = False,
    data_dir: Path | None = None,
) -> dict:
    """Compare a sanitized metric snapshot with prior persisted snapshots."""
    if not current:
        return {
            "status": "no_data",
            "account_id": account_id,
            "platform": platform,
            "alerts": [],
            "content_suggestions": [],
            "message": "尚无 Electron 会话同步的指标快照",
        }

    history = load_monitor_history(account_id, data_dir=data_dir)
    alerts: list[dict] = []
    suggestions: list[str] = []
    current_followers = _parse_number(current.get("followers"))

    comparable = [item for item in history if item.get("updated_at") != current.get("updated_at")]
    if comparable:
        previous = comparable[-1]
        previous_followers = _parse_number(previous.get("followers"))
        if previous_followers > 0:
            growth = (current_followers - previous_followers) / previous_followers
            if growth >= 0.2:
                alerts.append({
                    "level": "opportunity",
                    "message": f"粉丝较上次快照增长 {growth * 100:.1f}%",
                    "evidence": {"previous": previous_followers, "current": current_followers},
                })
                suggestions.append("复盘增长期间发布的内容，先形成候选假设，不直接归因为单一选题")
            elif growth < 0:
                alerts.append({
                    "level": "warning",
                    "message": f"粉丝较上次快照下降 {abs(growth) * 100:.1f}%",
                    "evidence": {"previous": previous_followers, "current": current_followers},
                })
                suggestions.append("检查同期发布、平台异常和统计口径，再决定是否调整内容策略")

    if persist and (not history or history[-1].get("updated_at") != current.get("updated_at")):
        save_monitor_snapshot(account_id, current, data_dir=data_dir)

    return {
        "status": "ok",
        "account_id": account_id,
        "platform": platform,
        "analyzed_at": datetime.now().isoformat(),
        "current_stats": current,
        "history_count": len(history),
        "alerts": alerts,
        "content_suggestions": suggestions,
        "source": "electron_session_snapshot",
    }


def analyze_account_trend(
    account_id: str,
    platform: str,
    _user_id: str = "",
    current: dict | None = None,
) -> dict:
    """Compatibility entrypoint; live collection must be supplied by Electron."""
    if current is None:
        return {
            "status": "error",
            "code": "electron_session_required",
            "error": "实时账号同步只能由 Electron 登录会话执行",
            "account_id": account_id,
            "platform": platform,
        }
    return analyze_account_snapshot(account_id, platform, current, persist=True)


def _read_json(name: str, fallback):
    try:
        return json.loads((CONFIG_DIR / name).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback


def monitor_account(params=None, **_kwargs) -> str:
    account_id = str((params or {}).get("account_id", "")).strip()
    account = next(
        (item for item in _read_json("accounts.json", {"accounts": []}).get("accounts", []) if item.get("id") == account_id),
        None,
    )
    if not account:
        return json.dumps({"status": "error", "error": "账号不存在"}, ensure_ascii=False)
    return json.dumps(
        analyze_account_snapshot(account_id, account.get("platform", ""), account.get("stats") or {}),
        ensure_ascii=False,
    )


def monitor_all(params=None, **_kwargs) -> str:
    accounts = _read_json("accounts.json", {"accounts": []}).get("accounts", [])
    results = [
        analyze_account_snapshot(item.get("id", ""), item.get("platform", ""), item.get("stats") or {})
        for item in accounts
        if item.get("status") in {"active", "connected"}
    ]
    alerts = [alert for result in results for alert in result.get("alerts", [])]
    suggestions = [suggestion for result in results for suggestion in result.get("content_suggestions", [])]
    return json.dumps({
        "monitored_at": datetime.now().isoformat(),
        "accounts_checked": len(results),
        "total_alerts": len(alerts),
        "alerts": alerts,
        "content_strategy_feedback": suggestions,
        "source": "persisted_snapshots",
    }, ensure_ascii=False)


def get_marketing_context(params=None, **_kwargs) -> str:
    params = params or {}
    limit = max(1, min(int(params.get("limit", 10)), 20))
    account_id = str(params.get("account_id", "")).strip() or None
    trends = _read_json("trending-cache.json", {})
    suggestions = _read_json("suggestions-cache.json", {})
    accounts = _read_json("accounts.json", {"accounts": []})
    report = _read_json("intelligence-report.json", {"status": "never_run"})
    targets = _read_json("intelligence-config.json", {})
    account_rows = accounts.get("accounts", [])
    if account_id:
        account_rows = [item for item in account_rows if item.get("id") == account_id]
    return json.dumps({
        "source": "marketing-os-desktop",
        "instruction": (
            "只基于以下持久数据回答；缺失、过期或失败必须明确说明。"
            "industries 是全局监控范围，不是账号标签；不得把未提供的内容数量、定位或活跃度写成事实。"
        ),
        "scope": {"account_id": account_id, "industries_scope": "global_monitoring_config"},
        "industries": targets.get("industries", []),
        "report": report,
        "trends": trends.get("top_trends", [])[:limit],
        "suggestions": suggestions.get("suggestions", [])[:limit],
        "accounts": [
            {
                "id": item.get("id"),
                "platform": item.get("platform"),
                "label": item.get("label"),
                "status": item.get("status"),
                "stats": item.get("stats", {}),
            }
            for item in account_rows
        ],
        "data_updated_at": trends.get("cached_at") or report.get("completed_at"),
    }, ensure_ascii=False)


TOOLS = [
    {
        "name": "monitor_account",
        "description": "读取单个账号最近的脱敏指标快照并与历史对比，不启动浏览器",
        "schema": {
            "type": "object",
            "properties": {"account_id": {"type": "string"}},
            "required": ["account_id"],
        },
        "handler": monitor_account,
    },
    {
        "name": "monitor_all",
        "description": "读取所有账号已持久化的指标快照并生成可追溯告警",
        "schema": {"type": "object", "properties": {}},
        "handler": monitor_all,
    },
    {
        "name": "get_marketing_context",
        "description": "读取行业热点、选题、巡检报告和脱敏账号指标，只读且不执行发布",
        "schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 20}},
        },
        "handler": get_marketing_context,
    },
]
