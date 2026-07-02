"""DATA-01: SourceContract normalization and validation."""

import pytest
from agent_core.models import SourceContract, SourceValidationError, validate_source_batch


class TestSourceContract:
    def test_minimal(self):
        sc = SourceContract.from_dict({
            "source": "hot_topics_api", "platform": "weibo",
            "url": "https://weibo.com/123", "title": "AI突破",
            "collected_at": "2026-07-01T10:00:00",
        })
        assert sc.source == "hot_topics_api"
        assert sc.platform == "weibo"
        assert sc.title == "AI突破"

    def test_all_fields(self):
        sc = SourceContract.from_dict({
            "source": "playwright_mcp_creator_center", "platform": "douyin",
            "url": "https://www.douyin.com/video/1", "title": "test",
            "collected_at": "2026-07-01T10:00:00", "rank": 1,
            "author": "creator1", "published_at": "2026-06-30",
            "metrics": {"views": 1000}, "query": "AI教育",
            "account_scope": "acct_1234", "raw_ref": "/fixtures/1.json",
        })
        assert sc.rank == 1
        assert sc.author == "creator1"
        assert sc.metrics == {"views": 1000}

    def test_missing_required(self):
        with pytest.raises(ValueError, match="missing"):
            SourceContract.from_dict({"source": "x"})

    def test_forbidden_url_scheme(self):
        with pytest.raises(ValueError, match="forbidden"):
            SourceContract.from_dict({
                "source": "x", "platform": "douyin",
                "url": "javascript:alert(1)", "title": "x",
                "collected_at": "2026-01-01",
            })

        with pytest.raises(ValueError, match="forbidden"):
            SourceContract.from_dict({
                "source": "x", "platform": "douyin",
                "url": "file:///etc/passwd", "title": "x",
                "collected_at": "2026-01-01",
            })

    def test_empty_title_rejected(self):
        with pytest.raises(ValueError, match="title"):
            SourceContract.from_dict({
                "source": "x", "platform": "douyin",
                "url": "https://a.com", "title": "",
                "collected_at": "2026-01-01",
            })

    def test_empty_url_rejected(self):
        with pytest.raises(ValueError, match="url"):
            SourceContract.from_dict({
                "source": "x", "platform": "douyin",
                "url": "  ", "title": "x",
                "collected_at": "2026-01-01",
            })

    def test_unknown_keys_preserved_in_additional(self):
        sc = SourceContract.from_dict({
            "source": "x", "platform": "douyin",
            "url": "https://a.com", "title": "t",
            "collected_at": "2026-01-01",
            "heat_value": 2840000, "category": "科技/AI",
        })
        assert sc.additional is not None
        assert sc.additional["heat_value"] == 2840000
        assert sc.additional["category"] == "科技/AI"

    def test_to_evidence_dict(self):
        sc = SourceContract(source="x", platform="douyin",
                            url="https://a.com", title="t",
                            collected_at="2026-01-01", rank=5, query="q")
        d = sc.to_evidence_dict()
        assert d["source"] == "x"
        assert d["rank"] == 5
        assert d["query"] == "q"
        assert "metrics" not in d

    def test_roundtrip(self):
        sc1 = SourceContract.from_dict({
            "source": "a", "platform": "b", "url": "https://c.com",
            "title": "d", "collected_at": "2026-01-01", "rank": 3,
        })
        sc2 = SourceContract.from_dict(sc1.to_dict())
        assert sc2.rank == 3


class TestValidateBatch:
    def test_valid_items_kept(self):
        items = [
            {"source": "a", "platform": "b", "url": "https://c.com",
             "title": "d", "collected_at": "2026-01-01"},
            {"source": "a2", "platform": "b2", "url": "https://c2.com",
             "title": "d2", "collected_at": "2026-01-01"},
        ]
        result = validate_source_batch(items)
        assert len(result) == 2

    def test_bad_items_dropped(self):
        items = [
            {"source": "a", "platform": "b", "url": "https://c.com",
             "title": "ok", "collected_at": "2026-01-01"},
            {"source": "x", "platform": "y", "url": "", "title": "",
             "collected_at": ""},  # dropped
        ]
        result = validate_source_batch(items)
        assert len(result) == 1
