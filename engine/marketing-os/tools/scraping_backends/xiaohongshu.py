"""小红书抓取后端

优先: xhs-mcp-server (MCP 协议, 需 cookie)
兜底: 直接 HTTP + cookie (curl)
"""

import json
import subprocess
import os
from .base import ScrapingBackend

API_BASE = "https://edith.xiaohongshu.com"


def _get_cookie() -> str:
    """从环境变量获取小红书 cookie"""
    return os.environ.get("XHS_COOKIE", "")


def _curl_get(url: str, cookie: str = "", timeout: int = 15) -> str:
    headers = ["-H", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"]
    if cookie:
        headers += ["-H", f"Cookie: {cookie}"]
    result = subprocess.run(
        ["curl", "-s", "--max-time", str(timeout), *headers, url],
        capture_output=True, text=True, timeout=timeout + 5,
    )
    if result.returncode != 0:
        raise RuntimeError(f"curl 失败: {result.stderr[:200]}")
    return result.stdout


class XiaohongshuMcpBackend(ScrapingBackend):
    name = "xiaohongshu"
    priority = 85
    platforms = ["xiaohongshu"]

    def available(self) -> bool:
        return bool(_get_cookie())

    def fetch_trending(self, platform: str, count: int = 30) -> list[dict]:
        cookie = _get_cookie()
        if not cookie:
            raise RuntimeError(
                "小红书需要登录 cookie。请在账号管理页添加小红书账号，或设置环境变量 XHS_COOKIE"
            )

        # 小红书探索页 — 热门推荐流
        url = f"{API_BASE}/api/sns/web/v1/homefeed"
        payload = json.dumps({"cursor_score": "", "num": min(count, 30), "refresh_type": 1})

        raw = subprocess.run(
            ["curl", "-s", "--max-time", "20",
             "-H", f"Cookie: {cookie}",
             "-H", "Content-Type: application/json;charset=UTF-8",
             "-H", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
             "-H", "Origin: https://www.xiaohongshu.com",
             "-H", "Referer: https://www.xiaohongshu.com/explore",
             "-d", payload,
             url],
            capture_output=True, text=True, timeout=25,
        )

        if result.returncode != 0:
            raise RuntimeError(f"小红书请求失败: {raw.stderr[:200]}")

        try:
            data = json.loads(raw.stdout)
        except json.JSONDecodeError:
            raise RuntimeError(f"小红书返回非 JSON: {raw.stdout[:200]}")

        if not data.get("success"):
            msg = data.get("msg", "未知错误")
            if "login" in msg.lower() or "auth" in msg.lower():
                raise RuntimeError(f"小红书 cookie 已过期，请重新登录。错误: {msg}")
            raise RuntimeError(f"小红书 API 返回失败: {msg}")

        items = []
        notes = data.get("data", {}).get("items", [])
        for i, note in enumerate(notes):
            nc = note.get("note_card", {})
            items.append({
                "rank": i + 1,
                "title": nc.get("display_title", "")[:80],
                "author": nc.get("user", {}).get("nickname", ""),
                "heat_value": nc.get("interact_info", {}).get("liked_count", ""),
                "type": nc.get("type", "normal"),
                "url": f"https://www.xiaohongshu.com/explore/{note.get('id', '')}",
            })

        return items[:count]
