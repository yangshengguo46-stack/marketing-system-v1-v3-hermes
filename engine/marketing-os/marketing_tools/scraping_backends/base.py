"""营销抓取后端抽象基类"""

from abc import ABC, abstractmethod


class ScrapingBackend(ABC):
    name: str = "base"
    priority: int = 0  # 数字越大优先级越高
    platforms: list[str] = []

    def supports(self, platform: str) -> bool:
        return platform in self.platforms

    @abstractmethod
    def available(self) -> bool:
        """检查此后端是否可用"""

    @abstractmethod
    def fetch_trending(self, platform: str, count: int = 30) -> list[dict]:
        """抓取热搜榜，返回 [{rank, title, heat_value, url}]"""
