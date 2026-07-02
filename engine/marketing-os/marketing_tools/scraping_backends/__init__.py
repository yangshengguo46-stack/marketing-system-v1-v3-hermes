"""营销数据可插拔抓取后端

每个后端实现:
  supports(platform) -> bool
  fetch_trending(platform, count) -> list[{rank, title, heat_value, url}]
"""

from .hot_topics_api import HotTopicsApiBackend
from .bilibili_public import BilibiliPublicBackend

BACKENDS = [
    # Public, cookie-free sources only. Logged-in collection is owned by the
    # Electron capability host and imported through the session endpoints.
    BilibiliPublicBackend(),
    HotTopicsApiBackend(),
]

def get_backend(platform: str):
    for b in BACKENDS:
        if b.supports(platform) and b.available():
            return b
    return None
