"""MediaCrawlerPro 后端 — 待用户网络就绪后激活

clone 后: pip install -e .
使用方式: python -m mediacrawler --platform douyin --type hot
"""

from .base import ScrapingBackend


class MediaCrawlerBackend(ScrapingBackend):
    name = "mediacrawler"
    priority = 95
    platforms = ["douyin", "weibo", "bilibili", "xiaohongshu", "kuaishou", "zhihu"]

    def available(self) -> bool:
        try:
            import mediacrawler
            return True
        except ImportError:
            return False

    def fetch_trending(self, platform: str, count: int = 30) -> list[dict]:
        import subprocess
        import json

        try:
            result = subprocess.run(
                ["python3", "-m", "mediacrawler",
                 "--platform", platform,
                 "--type", "hot",
                 "--limit", str(count),
                 "--output", "json"],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode != 0:
                raise RuntimeError(f"MediaCrawler 执行失败: {result.stderr[:200]}")

            data = json.loads(result.stdout)
            items = data if isinstance(data, list) else data.get("data", data.get("list", []))

            return [{
                "rank": it.get("rank", i + 1),
                "title": it.get("title", it.get("word", "")),
                "heat_value": it.get("heat", it.get("hot", "")),
                "url": it.get("url", ""),
            } for i, it in enumerate(items)]

        except json.JSONDecodeError:
            raise RuntimeError(f"MediaCrawler 返回非 JSON ({platform})")
        except FileNotFoundError:
            raise RuntimeError("MediaCrawlerPro 未安装，请 clone 后 pip install -e .")
