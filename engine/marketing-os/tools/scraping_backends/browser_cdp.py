"""Browser CDP 后端 — 复用用户 Chrome (superpowers-chrome)

chrome-ws 通过 CDP 协议直连 Chrome :9222，零依赖，自带 cookie/登录态。
"""

import json
import subprocess
import os
import time
from pathlib import Path
from .base import ScrapingBackend

CHROME_WS = str(Path.home() / ".agents/skills/browsing/chrome-ws")

SCRAPE_CONFIG = {
    "douyin": {
        "url": "https://www.douyin.com/hot",
        "wait_s": 6,
        "extract_js": """
(() => {
    const links = document.querySelectorAll('a[href*="/video/"], a[href*="/note/"]');
    const results = [];
    links.forEach((a, i) => {
        if (results.length >= 30) return;
        const text = a.textContent.trim();
        if (text.length < 10) return;
        const m = text.match(/^(\\d{2}:\\d{2})\\s*([\\d.]+万?)?\\s*(.+?)(?:@(\\S+?))?(?:\\s*·\\s*(.+))?$/);
        if (m) results.push({ rank: i + 1, title: (m[3] || text).substring(0, 60).trim(), views: m[2] || '', author: m[4] || '', date: m[5] || '' });
    });
    return JSON.stringify(results);
})()
"""
    },
    "weibo": {
        "url": "https://weibo.com/ajax/side/hotSearch",
        "wait_s": 3,
        "extract_js": """
(() => {
    try {
        const data = JSON.parse(document.body.innerText || document.body.textContent || '{}');
        const items = data.data?.realtime || [];
        return JSON.stringify(items.slice(0, 50).map((it, i) => ({ rank: i + 1, title: it.word || it.title, heat: it.num, tag: it.label_name || '' })));
    } catch(e) { return '[]'; }
})()
"""
    },
    "bilibili": {
        "url": "https://api.bilibili.com/x/web-interface/popular?ps=50",
        "wait_s": 3,
        "extract_js": """
(() => {
    try {
        const data = JSON.parse(document.body.innerText || document.body.textContent || '{}');
        const list = data.data?.list || [];
        return JSON.stringify(list.slice(0, 30).map((v, i) => ({ rank: i + 1, title: v.title, play: v.stat?.view || '', author: v.owner?.name || '', bvid: v.bvid || '' })));
    } catch(e) { return '[]'; }
})()
"""
    },
    "xiaohongshu": {
        "url": "https://www.xiaohongshu.com/explore",
        "wait_s": 6,
        "extract_js": """
(() => {
    const results = [];
    // 小红书探索页 — 瀑布流笔记卡片
    document.querySelectorAll('.note-item, [class*=\"note\"][class*=\"item\"], section.note-item, .feeds-page .note-item').forEach((el, i) => {
        if (results.length >= 30) return;
        const title = el.querySelector('.title, .note-title, [class*=\"title\"]')?.textContent?.trim();
        const author = el.querySelector('.author .name, .nickname, [class*=\"author\"] [class*=\"name\"], [class*=\"nick\"]')?.textContent?.trim();
        const likes = el.querySelector('.like-count, .count, [class*=\"like\"], [class*=\"count\"]')?.textContent?.trim();
        const link = el.querySelector('a[href*=\"/explore/\"]')?.getAttribute('href') || '';
        if (title) results.push({ rank: results.length + 1, title: title.substring(0, 60), author, likes, url: 'https://www.xiaohongshu.com' + link });
    });
    // 备选: 从服务端渲染数据提取
    if (!results.length) {
        const scripts = document.querySelectorAll('script');
        scripts.forEach(s => {
            const m = s.textContent.match(/window\\.__INITIAL_STATE__\\s*=\\s*(.+?)</);
            if (m) {
                try {
                    const data = JSON.parse(m[1].replace(/undefined/g, 'null'));
                    const notes = data?.note?.noteDetailMap || data?.note?.notesMap || {};
                    Object.values(notes).forEach((n, i) => {
                        if (results.length >= 30) return;
                        const note = n.note || n;
                        results.push({ rank: results.length + 1, title: (note.title || note.desc || '').substring(0, 60), author: note.user?.nickname || '', likes: note.interactInfo?.likedCount || '' });
                    });
                } catch(e) {}
            }
        });
    }
    return JSON.stringify(results);
})()
"""
    },
    "kuaishou": {
        "url": "https://www.kuaishou.com/new-reco",
        "wait_s": 5,
        "extract_js": """
(() => {
    const results = [];
    // 快手推荐页视频卡片
    document.querySelectorAll('.video-card, [class*=\"video-card\"], .card-item, [class*=\"card\"]').forEach((el, i) => {
        if (results.length >= 30) return;
        const title = el.querySelector('.video-title, .title, [class*=\"title\"], .work-info')?.textContent?.trim();
        const author = el.querySelector('.author-name, .name, [class*=\"author\"], [class*=\"name\"]')?.textContent?.trim();
        const views = el.querySelector('.play-count, .count, [class*=\"play\"], [class*=\"count\"]')?.textContent?.trim();
        if (title) results.push({ rank: results.length + 1, title: title.substring(0, 60), author, views });
    });
    return JSON.stringify(results);
})()
"""
    },
    "zhihu": {
        "url": "https://www.zhihu.com/hot",
        "wait_s": 4,
        "extract_js": """
(() => {
    const results = [];
    // 知乎热榜
    document.querySelectorAll('.HotList-item, .hot-list-item, [class*=\"HotList\"] [class*=\"item\"]').forEach((el, i) => {
        if (results.length >= 30) return;
        const titleEl = el.querySelector('h2, .HotList-itemTitle, [class*=\"title\"] a, a[href*=\"/question/\"]');
        const title = titleEl?.textContent?.trim() || '';
        const heatEl = el.querySelector('[class*=\"metrics\"], [class*=\"heat\"], [class*=\"hot\"]');
        const heat = heatEl?.textContent?.trim() || '';
        if (title) results.push({ rank: results.length + 1, title: title.substring(0, 60), heat, url: titleEl?.getAttribute('href') || '' });
    });
    return JSON.stringify(results);
})()
"""
    },
    "weibo": {
        "url": "https://weibo.com/ajax/side/hotSearch",
        "wait_s": 3,
        "extract_js": """
(() => {
    try {
        const data = JSON.parse(document.body.innerText || document.body.textContent || '{}');
        const items = data.data?.realtime || [];
        return JSON.stringify(items.slice(0, 50).map((it, i) => ({ rank: i + 1, title: it.word || it.title, heat: it.num, tag: it.label_name || '' })));
    } catch(e) { return '[]'; }
})()
"""
    },
    "wechat_article": {
        "url": "https://weixin.qq.com/cgi-bin/readtemplate?t=wz/xsj/index",
        "wait_s": 4,
        "extract_js": """
(() => {
    const results = [];
    document.querySelectorAll('.item, [class*=\"item\"], .card, .article-item').forEach((el, i) => {
        if (results.length >= 30) return;
        const title = el.querySelector('.title, h3, [class*=\"title\"]')?.textContent?.trim();
        const author = el.querySelector('.name, .author, [class*=\"author\"]')?.textContent?.trim();
        if (title) results.push({ rank: results.length + 1, title: title.substring(0, 60), author });
    });
    return JSON.stringify(results);
})()
"""
    },
    "tiktok": {
        "url": "https://www.tiktok.com/trending",
        "wait_s": 5,
        "extract_js": """
(() => {
    const results = [];
    document.querySelectorAll('[data-e2e=\"trending-item\"], .video-card, [class*=\"video\"]').forEach((el, i) => {
        if (results.length >= 30) return;
        const title = el.querySelector('[data-e2e=\"video-desc\"], .desc, [class*=\"desc\"]')?.textContent?.trim();
        const author = el.querySelector('[data-e2e=\"video-author\"], .author, [class*=\"author\"]')?.textContent?.trim();
        const views = el.querySelector('[data-e2e=\"video-views\"], .views, [class*=\"view\"]')?.textContent?.trim();
        if (title) results.push({ rank: results.length + 1, title: title.substring(0, 60), author, views });
    });
    return JSON.stringify(results);
})()
"""
    },
    "youtube": {
        "url": "https://www.youtube.com/feed/trending",
        "wait_s": 5,
        "extract_js": """
(() => {
    const results = [];
    document.querySelectorAll('ytd-video-renderer, ytd-rich-item-renderer').forEach((el, i) => {
        if (results.length >= 30) return;
        const title = el.querySelector('#video-title, .title')?.textContent?.trim();
        const channel = el.querySelector('#channel-name, .channel-name a, ytd-channel-name')?.textContent?.trim();
        const views = el.querySelector('#metadata-line span:first-child, .metadata span')?.textContent?.trim();
        if (title) results.push({ rank: results.length + 1, title: title.substring(0, 60), author: channel, views });
    });
    return JSON.stringify(results);
})()
"""
    },
    "twitter": {
        "url": "https://x.com/explore/tabs/trending",
        "wait_s": 5,
        "extract_js": """
(() => {
    const results = [];
    document.querySelectorAll('[data-testid=\"trend\"], [role=\"article\"]').forEach((el, i) => {
        if (results.length >= 30) return;
        const title = el.querySelector('span, [dir=\"ltr\"]')?.textContent?.trim();
        const count = el.querySelector('span + span')?.textContent?.trim();
        if (title && title.length > 3 && !title.startsWith('·')) {
            results.push({ rank: results.length + 1, title: title.substring(0, 60), heat: count || '' });
        }
    });
    // 备选: 从 trending 列表提取
    if (!results.length) {
        document.querySelectorAll('div[data-testid=\"trend\"]').forEach((el, i) => {
            if (results.length >= 30) return;
            const spans = el.querySelectorAll('span');
            spans.forEach(s => {
                const text = s.textContent.trim();
                if (text.length > 5 && !text.match(/^(Trending|·|\\d)/)) {
                    const exists = results.find(r => r.title === text.substring(0, 60));
                    if (!exists) results.push({ rank: results.length + 1, title: text.substring(0, 60), heat: '' });
                }
            });
        });
    }
    return JSON.stringify(results);
})()
"""
    },
}


class BrowserCDPBackend(ScrapingBackend):
    name = "browser_cdp"
    engine = "chrome_ws"
    priority = 85
    platforms = ["douyin", "weibo", "bilibili", "xiaohongshu", "kuaishou", "zhihu",
                 "wechat_article", "tiktok", "youtube", "twitter"]

    def available(self) -> bool:
        try:
            r = subprocess.run([CHROME_WS, "tabs"], capture_output=True, text=True, timeout=5)
            return r.returncode == 0
        except Exception:
            return False

    def fetch_trending(self, platform: str, count: int = 30) -> list[dict]:
        config = SCRAPE_CONFIG.get(platform)
        if not config:
            raise RuntimeError(f"CDP 不支持: {platform}")

        url = config["url"]
        wait = config["wait_s"]

        # Step 1: 新标签页打开，捕获 WebSocket URL
        tab_out = subprocess.run(
            [CHROME_WS, "new", url],
            capture_output=True, text=True, timeout=15,
        )
        if tab_out.returncode != 0:
            raise RuntimeError(f"chrome-ws new 失败: {tab_out.stderr[:200]}")

        ws_url = tab_out.stdout.strip()
        if not ws_url.startswith("ws://"):
            raise RuntimeError(f"chrome-ws 返回异常: {ws_url[:100]}")

        time.sleep(wait)

        # Step 2: 执行 JS — 直接传参，subprocess 自动处理转义
        result = subprocess.run(
            [CHROME_WS, "eval", ws_url, config["extract_js"]],
            capture_output=True, text=True, timeout=20,
        )

        # Step 3: 关闭标签页
        subprocess.run([CHROME_WS, "close", ws_url], capture_output=True, timeout=5)

        if result.returncode != 0:
            raise RuntimeError(f"chrome-ws eval 失败: {result.stderr[:200]}")

        items = _parse(result.stdout)
        if not items:
            raise RuntimeError(f"{platform} 返回空数据, 页面可能需要登录或结构已变")

        return items[:count]


def _parse(raw: str) -> list[dict]:
    raw = raw.strip()
    try:
        data = json.loads(raw)
        # chrome-ws eval 返回的是 JSON 字符串，可能双编码
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except (json.JSONDecodeError, TypeError):
                pass
        if isinstance(data, list): return data
        if isinstance(data, dict): return [data]
    except json.JSONDecodeError:
        pass
    return []
