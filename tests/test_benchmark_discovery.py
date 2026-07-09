from agent_core.benchmark_discovery import discover_benchmark_candidates
from marketing_tools.scraping_backends.bilibili_public import BilibiliPublicBackend


def _item(*, author_id="42", title="AI 教育怎么做", url="https://www.bilibili.com/video/BV1"):
    return {
        "source_platform": "bilibili", "source_backend": "bilibili_public",
        "title": title, "url": url, "video_id": url.rsplit("/", 1)[-1],
        "collected_at": "2026-07-04T10:00:00+00:00", "quality_score": 0.8,
        "author": {
            "id": author_id, "name": f"创作者{author_id}",
            "profile_url": f"https://space.bilibili.com/{author_id}",
            "bio": "专注 AI 教育与普通人学习",
        },
        "metrics": {"views": 1000},
    }


def test_discovery_requires_stable_creator_identity_and_source():
    missing_creator = _item()
    missing_creator["author"] = {}
    missing_source = _item(author_id="43")
    missing_source["url"] = ""
    result = discover_benchmark_candidates(
        query="AI 教育", items=[missing_creator, missing_source], platform="bilibili",
    )
    assert result["candidates"] == []
    assert result["skipped"]["missing_creator"] == 1
    assert result["skipped"]["missing_source"] == 1


def test_discovery_groups_samples_and_ranks_query_plus_audience_overlap():
    items = [
        _item(url="https://www.bilibili.com/video/BV1"),
        _item(title="普通人如何学会 AI", url="https://www.bilibili.com/video/BV2"),
        _item(author_id="99", title="AI 芯片新闻", url="https://www.bilibili.com/video/BV3"),
    ]
    result = discover_benchmark_candidates(
        query="AI 教育", items=items, platform="bilibili",
        audience_hypothesis={"segments": [{"label": "普通人学习 AI"}]},
    )
    assert result["candidate_count"] == 2
    assert result["candidates"][0]["account_handle"] == "42"
    assert len(result["candidates"][0]["samples"]) == 2
    assert result["candidates"][0]["matched_query_terms"] == ["ai", "教育"]
    assert result["candidates"][0]["score"] > result["candidates"][1]["score"]


def test_discovery_does_not_turn_unmatched_hot_content_into_candidate():
    result = discover_benchmark_candidates(
        query="新能源汽车", items=[_item(title="AI 教育怎么做")], platform="bilibili",
    )
    assert result["candidates"] == []
    assert "不代表账号质量" in result["limitations"][1]


def test_bilibili_keyword_search_preserves_creator_and_strips_markup(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"code": 0, "data": {"result": [{
                "mid": 42, "author": "真实作者", "bvid": "BV1",
                "title": '<em class="keyword">AI</em> 教育', "play": 100,
                "like": 10, "video_review": 3, "favorites": 5,
            }]}}

    monkeypatch.setattr("httpx.get", lambda *args, **kwargs: Response())
    items = BilibiliPublicBackend().search_content("AI 教育", count=5)
    assert items[0]["title"] == "AI 教育"
    assert items[0]["author"] == {
        "id": "42", "name": "真实作者", "profile_url": "https://space.bilibili.com/42",
    }
    assert items[0]["url"] == "https://www.bilibili.com/video/BV1"
    assert items[0]["source_backend"] == "bilibili_public"
