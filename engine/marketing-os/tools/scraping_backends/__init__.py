"""可插拔抓取后端

每个后端实现:
  supports(platform) -> bool
  fetch_trending(platform, count) -> list[{rank, title, heat_value, url}]
"""

from .hot_topics_api import HotTopicsApiBackend
from .agent_reach import AgentReachBackend
from .xiaohongshu import XiaohongshuMcpBackend
from .mediacrawler import MediaCrawlerBackend
from .browser_cdp import BrowserCDPBackend

BACKENDS = [
    BrowserCDPBackend(),      # p=85 — chrome-ws, 复用用户 Chrome, cookie/登录态全保留
    AgentReachBackend(),      # p=90
    HotTopicsApiBackend(),    # p=80
    XiaohongshuMcpBackend(),  # p=85
    MediaCrawlerBackend(),    # p=95
]

def get_backend(platform: str):
    for b in BACKENDS:
        if b.supports(platform) and b.available():
            return b
    return BrowserCDPBackend()  # 兜底
