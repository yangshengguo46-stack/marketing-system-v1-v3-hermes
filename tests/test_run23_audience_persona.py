"""RUN-23: Audience persona derivation tests."""

import pytest
from engine.agent_core.audience_persona import (
    AudiencePersona,
    derive_personas,
    persona_to_dict,
    personas_to_inference_candidate,
    personas_to_dna,
    _detect_age_range,
    _detect_interests,
    _detect_sentiment,
    _detect_language,
)


class TestDetectAgeRange:
    def test_00s(self):
        assert _detect_age_range("作为00后大学生深有同感") == "00后"

    def test_90s(self):
        assert _detect_age_range("打工人996太累了") == "90后"

    def test_80s(self):
        assert _detect_age_range("房贷压力太大了") == "80后"

    def test_none(self):
        assert _detect_age_range("说得好") is None


class TestDetectInterests:
    def test_tech(self):
        assert "科技" in _detect_interests("AI大模型太强了")

    def test_startup(self):
        assert "创业" in _detect_interests("想搞副业赚钱")

    def test_multiple(self):
        interests = _detect_interests("AI创业公司面试经验")
        assert "科技" in interests
        assert "创业" in interests
        assert "职场" in interests

    def test_none(self):
        assert _detect_interests("今天天气不错") == []


class TestDetectSentiment:
    def test_positive(self):
        assert _detect_sentiment("说得太对了，学到了") == "positive"

    def test_negative(self):
        assert _detect_sentiment("纯属胡说，营销号") == "negative"

    def test_neutral(self):
        assert _detect_sentiment("这个观点值得思考") == "neutral"


class TestDetectLanguage:
    def test_chinese(self):
        assert _detect_language("这是一个中文评论") == "zh"

    def test_english(self):
        assert _detect_language("This is an English comment") == "en"

    def test_mixed(self):
        assert _detect_language("用AI做内容创作很有意思") == "zh"


class TestDerivePersonas:
    def test_empty_comments(self):
        assert derive_personas([]) == []

    def test_single_cluster(self):
        comments = [
            {"text": "00后大学生觉得AI太强了", "likes": 10},
            {"text": "作为学生党支持AI发展", "likes": 5},
            {"text": "00后学AI编程有感", "likes": 3},
        ]
        personas = derive_personas(comments, min_cluster_size=2)
        assert len(personas) >= 1
        assert personas[0].size >= 2
        assert personas[0].age_range == "00后"
        assert "科技" in personas[0].interests

    def test_multiple_clusters(self):
        comments = [
            {"text": "00后大学生觉得AI太强了", "likes": 10},
            {"text": "00后学生党支持AI发展", "likes": 5},
            {"text": "00后学AI编程有感", "likes": 3},
            {"text": "80后房贷压力大想搞副业", "likes": 8},
            {"text": "80后中年人想创业赚钱", "likes": 6},
            {"text": "80后搞副业搞钱", "likes": 4},
        ]
        personas = derive_personas(comments, min_cluster_size=2)
        assert len(personas) >= 2
        # Larger cluster first
        assert personas[0].size >= personas[1].size

    def test_min_cluster_size_filter(self):
        comments = [
            {"text": "00后大学生觉得AI太强了", "likes": 10},
            {"text": "80后房贷压力大想搞副业", "likes": 8},
        ]
        personas = derive_personas(comments, min_cluster_size=3)
        assert len(personas) == 0

    def test_raw_comments_are_not_retained(self):
        comments = [
            {"text": "00后大学生觉得AI太强了", "likes": 10},
            {"text": "00后学生党支持AI发展", "likes": 5},
            {"text": "00后学AI编程有感", "likes": 3},
        ]
        personas = derive_personas(comments, min_cluster_size=2)
        serialized = persona_to_dict(personas[0])
        assert "representative_comments" not in serialized
        assert "AI太强了" not in str(serialized)

    def test_keywords_extracted(self):
        comments = [
            {"text": "人工智能AI发展太快了", "likes": 5},
            {"text": "AI人工智能改变世界", "likes": 3},
            {"text": "AI人工智能是未来", "likes": 2},
        ]
        personas = derive_personas(comments, min_cluster_size=2)
        if personas:
            assert len(personas[0].keywords) > 0

    def test_other_cluster(self):
        """Comments without clear age/interest markers go to 'other'."""
        comments = [
            {"text": "说得好有道理", "likes": 5},
            {"text": "确实如此", "likes": 3},
            {"text": "深有同感", "likes": 2},
        ]
        personas = derive_personas(comments, min_cluster_size=2)
        assert len(personas) >= 1
        assert personas[0].age_range is None
        assert "other" in personas[0].label


class TestPersonaSerialization:
    def test_persona_to_dict(self):
        persona = AudiencePersona(
            label="00后-科技",
            size=10,
            age_range="00后",
            interests=["科技", "创业"],
            language="zh",
            sentiment="positive",
            keywords=[("AI", 5), ("人工智能", 3)],
        )
        d = persona_to_dict(persona)
        assert d["label"] == "00后-科技"
        assert d["size"] == 10
        assert d["age_range"] == "00后"
        assert "科技" in d["interests"]
        assert d["sentiment"] == "positive"
        assert d["is_first_party_audience_fact"] is False
        assert "representative_comments" not in d

    def test_personas_to_dna(self):
        personas = [
            AudiencePersona(label="00后-科技", size=10, age_range="00后", interests=["科技"]),
            AudiencePersona(label="80后-创业", size=5, age_range="80后", interests=["创业"]),
        ]
        candidate = personas_to_dna(personas)
        assert candidate == personas_to_inference_candidate(personas)
        assert candidate["kind"] == "audience_inference_candidate"
        assert candidate["status"] == "pending"
        assert candidate["total_clusters"] == 2
        assert candidate["total_comments"] == 15
        assert "00后" in candidate["dominant_age_ranges"]
        assert "80后" in candidate["dominant_age_ranges"]
        assert "科技" in candidate["dominant_interests"]
        assert "创业" in candidate["dominant_interests"]
        assert "zh" in candidate["dominant_languages"]
        assert candidate["can_update_actual_audience_snapshot"] is False
        assert candidate["raw_comments_retained"] is False
