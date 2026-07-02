"""pytest 共享 fixture"""

import json
import os
import sys
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("HERMES_HOME", str(PROJECT_ROOT / ".pytest-cache" / "hermes-home"))
ENGINE_ROOT = PROJECT_ROOT / "engine"
MARKETING_ROOT = ENGINE_ROOT / "marketing-os"
sys.path.insert(0, str(ENGINE_ROOT))
sys.path.insert(0, str(MARKETING_ROOT))

MOCK_TRENDS = {
    "results": {
        "douyin": {
            "success": True,
            "backend_used": "mock",
            "data": [
                {"rank": 1, "title": "AI大模型新突破引发行业震动", "heat_value": "982.3w"},
                {"rank": 2, "title": "苹果发布iOS 20", "heat_value": "876.1w"},
                {"rank": 3, "title": "高考分数线今日公布", "heat_value": "754.2w"},
                {"rank": 4, "title": "某明星演唱会门票秒光", "heat_value": "621.8w"},
                {"rank": 5, "title": "LOL世界赛中国队夺冠", "heat_value": "589.3w"},
            ],
        },
        "weibo": {
            "success": True,
            "backend_used": "mock",
            "data": [
                {"rank": 1, "title": "AI大模型新突破", "heat_value": 2840000},
                {"rank": 2, "title": "高考分数线", "heat_value": 2130000},
                {"rank": 3, "title": "某明星离婚声明", "heat_value": 1980000},
                {"rank": 4, "title": "新款特斯拉发布", "heat_value": 1650000},
                {"rank": 5, "title": "股市大涨", "heat_value": 1430000},
            ],
        },
        "bilibili": {
            "success": True,
            "backend_used": "mock",
            "data": [
                {"rank": 1, "title": "半小时搞懂Transformer架构", "heat_value": 520000},
                {"rank": 2, "title": "黑神话悟空DLC实机演示", "heat_value": 480000},
                {"rank": 3, "title": "我用AI做了一个视频生成器", "heat_value": 350000},
                {"rank": 4, "title": "高考志愿填报指南", "heat_value": 290000},
                {"rank": 5, "title": "iPhone 20深度评测", "heat_value": 260000},
            ],
        },
    },
    "platforms_scraped": ["douyin", "weibo", "bilibili"],
}


@pytest.fixture
def mock_trends():
    return json.loads(json.dumps(MOCK_TRENDS))


@pytest.fixture
def user_profile():
    return {
        "category": "科技",
        "niche": "AI应用/独立开发",
        "profession": "技术创业者",
        "interests": "AI, 大模型, 视频生成, 开源",
        "platforms": ["douyin", "bilibili"],
        "style": "教学型",
        "audience": "25-35岁科技从业者",
    }
