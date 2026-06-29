"""内容分析工具 — 趋势分析、选题建议、用户画像匹配"""

import json
import re
from datetime import datetime


def analyze_trends(params, **kwargs) -> str:
    """分析热点趋势：去重、分类、提取关键词

    params.hot_data: 来自 aggregate_all_trending 的聚合热点数据 (JSON string)
    返回: 分类/排序/去重后的分析结果
    """
    hot_data_str = params.get("hot_data", "{}")
    try:
        hot_data = json.loads(hot_data_str) if isinstance(hot_data_str, str) else hot_data_str
    except (json.JSONDecodeError, TypeError):
        hot_data = {}

    all_items = []

    # 标准化各平台数据为统一格式
    for platform, data in hot_data.get("results", {}).items():
        items = []
        # 处理新后端格式: {success, data: [...], ...}
        actual_data = data
        if isinstance(data, dict) and "data" in data and isinstance(data["data"], list):
            actual_data = data["data"]

        if platform == "douyin":
            items = _parse_douyin(actual_data)
        elif platform == "weibo":
            items = _parse_weibo(actual_data)
        elif platform == "bilibili":
            items = _parse_bilibili(actual_data)
        else:
            items = _parse_generic(actual_data)

        for item in items:
            item["source_platform"] = platform
            all_items.append(item)

    # 去重 (标题相似度)
    deduped = _deduplicate_by_title(all_items)

    # 分类打标签
    categorized = _categorize(deduped)

    return json.dumps({
        "analyzed_at": datetime.now().isoformat(),
        "total_raw": len(all_items),
        "total_deduped": len(deduped),
        "categories": categorized,
        "top_trends": [t for cat_items in categorized.values() for t in cat_items[:5]],
    }, ensure_ascii=False)


def _parse_douyin(data):
    items = _extract_items(data)
    return [{
        "title": it.get("title", it.get("word", "")),
        "rank": it.get("rank", 0),
        "heat": it.get("heat", it.get("heat_value", "")),
    } for it in items if it.get("title") or it.get("word")]


def _parse_weibo(data):
    items = _extract_items(data)
    return [{
        "title": it.get("title", it.get("word", "")),
        "rank": it.get("rank", 0),
        "heat": it.get("heat", it.get("num", it.get("heat_value", ""))),
    } for it in items if it.get("title") or it.get("word")]


def _parse_bilibili(data):
    items = _extract_items(data)
    return [{
        "title": it.get("title", ""),
        "rank": it.get("rank", 0),
        "heat": it.get("play", it.get("heat_value",
            it.get("stat", {}).get("view", "")
            if isinstance(it.get("stat"), dict) else "")),
    } for it in items if it.get("title")]


def _parse_generic(data):
    items = _extract_items(data)
    return [{
        "title": it.get("title", it.get("word", it.get("name", ""))),
        "rank": it.get("rank", 0),
        "heat": it.get("heat", it.get("num", it.get("heat_value", it.get("views", "")))),
    } for it in items if it.get("title") or it.get("word") or it.get("name")]


def _extract_items(data):
    """从各种格式中提取条目列表"""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        # 可能包裹在 result/data/list 等键下
        for key in ("result", "data", "list", "items"):
            val = data.get(key)
            if isinstance(val, list):
                return val
            if isinstance(val, dict):
                for subkey in ("list", "items", "realtime", "hot"):
                    subval = val.get(subkey)
                    if isinstance(subval, list):
                        return subval
    return []


def _deduplicate_by_title(items):
    """基于标题关键词去重"""
    seen = set()
    result = []
    for item in items:
        title = item.get("title", "")
        # 粗粒度去重: 取前5个字的hash
        key = title[:5] if len(title) >= 5 else title
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _categorize(items):
    """基于关键词分类"""
    categories = {
        "科技/AI": ["AI", "人工智能", "GPT", "大模型", "芯片", "机器人", "自动驾驶", "苹果", "华为", "小米", "特斯拉", "OpenAI", "DeepSeek"],
        "娱乐/影视": ["电影", "综艺", "电视剧", "明星", "偶像", "男团", "女团", "演唱会", "音乐"],
        "财经/商业": ["股市", "基金", "经济", "房价", "电商", "直播带货", "IPO", "融资", "裁员"],
        "社会/民生": ["政策", "教育", "医疗", "高考", "考研", "就业", "结婚", "生育", "房价"],
        "游戏/电竞": ["游戏", "电竞", "LOL", "王者荣耀", "原神", "黑神话", "米哈游", "网易"],
        "体育/赛事": ["足球", "篮球", "世界杯", "NBA", "奥运会", "马拉松"],
        "生活方式": ["美食", "旅游", "穿搭", "健身", "美妆", "家居", "宠物", "vlog"],
    }
    result = {cat: [] for cat in categories}
    result["其他"] = []

    for item in items:
        title = item.get("title", "")
        matched = False
        for cat, keywords in categories.items():
            if any(kw in title for kw in keywords):
                result[cat].append(item)
                matched = True
                break
        if not matched:
            result["其他"].append(item)

    return {k: v for k, v in result.items() if v}


# ---- 选题建议 ----

def generate_content_suggestions(params, **kwargs) -> str:
    """基于用户画像和热点趋势，生成短视频选题建议

    params.user_profile: 用户画像 (身份/职业/兴趣/行业)
    params.trends: 来自 analyze_trends 的热点分析结果
    """
    user_profile = params.get("user_profile", {})
    trends_str = params.get("trends", "{}")
    try:
        trends = json.loads(trends_str) if isinstance(trends_str, str) else trends_str
    except (json.JSONDecodeError, TypeError):
        trends = {}

    if isinstance(user_profile, str):
        try:
            user_profile = json.loads(user_profile)
        except (json.JSONDecodeError, TypeError):
            user_profile = {}

    category = user_profile.get("category", "")
    niche = user_profile.get("niche", "")
    profession = user_profile.get("profession", "")

    # 从趋势中筛选与用户画像匹配的热点
    top_trends = trends.get("top_trends", [])
    matched_trends = []

    for trend in top_trends:
        title = trend.get("title", "")
        score = _match_score(title, user_profile)
        if score > 0:
            trend["match_score"] = score
            matched_trends.append(trend)

    matched_trends.sort(key=lambda x: x.get("match_score", 0), reverse=True)
    # A sparse first run should still produce useful ideas instead of an empty screen.
    if not matched_trends:
        matched_trends = [{**trend, "match_score": 0} for trend in top_trends[:10]]

    # 为每个匹配热点生成选题建议
    suggestions = []
    for i, trend in enumerate(matched_trends[:10]):
        suggestions.append({
            "id": f"sug_{i+1:03d}",
            "trend": trend.get("title"),
            "trend_source": trend.get("source_platform"),
            "hot_level": "🔥" if i < 3 else "⭐" if i < 6 else "💡",
            "angles": _generate_angles(trend.get("title", ""), user_profile),
            "target_audience": _estimate_audience(user_profile),
            "estimated_traffic": "高" if i < 3 else "中" if i < 6 else "偏低",
        })

    return json.dumps({
        "generated_at": datetime.now().isoformat(),
        "user_profile_summary": f"{profession} | {category} | {niche}",
        "matched_trends_count": len(matched_trends),
        "suggestions": suggestions,
    }, ensure_ascii=False)


def _match_score(title, profile):
    """计算热点与用户画像的匹配度"""
    score = 0
    keywords = " ".join([
        profile.get("category", ""),
        profile.get("niche", ""),
        profile.get("profession", ""),
        profile.get("interests", ""),
    ])
    for kw in re.split(r"[\s,，/、;；]+", keywords):
        if kw and kw in title:
            score += 1
    return score


def _generate_angles(title, profile):
    niche = profile.get("niche", "通用")
    return [
        f"【{niche}视角解读】{title} — 挖掘背后的行业逻辑",
        f"【教学向】{title}热点的3个知识点，帮你建立专业认知",
        f"【共鸣向】{title}对普通人的影响有多大？说说你的看法",
    ]


def _estimate_audience(profile):
    return "关注科技趋势的25-35岁职场人群"


TOOLS = [
    {
        "name": "analyze_trends",
        "description": "分析聚合热点数据：去重、分类、提取关键词、按热度排序",
        "schema": {
            "type": "object",
            "properties": {
                "hot_data": {"type": "string", "description": "来自 aggregate_all_trending 的聚合热点JSON"}
            },
            "required": ["hot_data"]
        },
        "handler": analyze_trends,
    },
    {
        "name": "generate_content_suggestions",
        "description": "基于用户画像和热点趋势，生成个性化短视频选题建议",
        "schema": {
            "type": "object",
            "properties": {
                "user_profile": {"type": "object", "description": "用户画像 {category, niche, profession, interests}"},
                "trends": {"type": "object", "description": "来自 analyze_trends 的分析结果"}
            },
            "required": ["user_profile", "trends"]
        },
        "handler": generate_content_suggestions,
    },
]
