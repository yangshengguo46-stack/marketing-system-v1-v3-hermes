from __future__ import annotations

import json

import hermes_state

from agent.marketing.data_paths import MarketingDataPaths
from agent.marketing.domains.account_portfolio import (
    PORTFOLIO_SCHEMA,
    AccountPortfolioRepository,
    decode_browser_portfolio_result,
)
from agent.marketing.evidence_capture import enrich_tool_result_with_evidence
from hermes_state import SessionDB


def _repository(tmp_path):
    state_path = tmp_path / "state.db"
    owner = SessionDB(db_path=state_path)
    owner.close()
    return AccountPortfolioRepository(
        MarketingDataPaths(
            user_data=tmp_path,
            config_dir=tmp_path / "config",
            agent_db=state_path,
        )
    )


def _payload():
    articles = []
    for index, day in enumerate((1, 8, 15), start=1):
        articles.append(
            {
                "source_item_id": f"article-{index}",
                "source_url": f"https://mp.weixin.qq.com/s/article-{index}",
                "title": f"一个创作者如何建立长期内容系统（{index}）",
                "digest": "这是文章摘要",
                "cover_url": "https://mp.weixin.qq.com/cover.jpg",
                "published_at": f"2026-07-{day:02d}T08:00:00+00:00",
                "body_text": "长期内容经营需要证据、定位和复盘。" * 80,
                "character_count": 1_120,
                "paragraph_count": 18,
                "image_count": 3,
                "metrics": {},
            }
        )
    return {
        "schema": PORTFOLIO_SCHEMA,
        "platform": "wechat_official",
        "observed_at": "2026-07-13T08:00:00+00:00",
        "account": {"name": "经营实验室"},
        "articles": articles,
        "collection": {"requested": 20, "returned": 3, "body_count": 3, "metrics_count": 0},
        "data_gaps": ["article_response_metrics_unavailable"],
    }


def test_owned_portfolio_capture_creates_article_evidence_and_honest_score(tmp_path):
    repository = _repository(tmp_path)
    result = repository.capture_browser_result(
        user_id="default",
        account_id="acct-wechat",
        payload=_payload(),
        session_id="session-1",
        tool_call_id="call-1",
    )

    assert result["article_count"] == 3
    assert len(result["evidence_ids"]) == 3
    assert result["scorecard"]["observed_execution_score"] is not None
    assert result["scorecard"]["dimensions"]["publishing_consistency"]["score"] is not None
    assert result["scorecard"]["dimensions"]["audience_response"]["score"] is None
    assert "audience_response_metrics_unavailable" in result["scorecard"]["data_gaps"]

    latest = repository.latest(user_id="default", account_id="acct-wechat")
    assert latest["status"] == "ready"
    assert latest["account_name"] == "经营实验室"
    assert len(latest["articles"]) == 3
    assert all(item["evidence_id"].startswith("evidence_") for item in latest["articles"])
    assert "not a universal" in latest["scorecard"]["semantics"]


def test_portfolio_decoder_and_post_tool_seam_are_account_scoped(tmp_path, monkeypatch):
    state_path = tmp_path / "state.db"
    monkeypatch.setenv("MARKETING_OS_AGENT_DB", str(state_path))
    monkeypatch.setenv("MARKETING_OS_USER_DATA", str(tmp_path))
    monkeypatch.setenv("MARKETING_OS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setattr(hermes_state, "DEFAULT_DB_PATH", state_path)
    owner = SessionDB(db_path=state_path)
    owner.create_session(
        "session-1",
        "tui",
        marketing_user_id="default",
        marketing_account_id="acct-wechat",
    )
    owner.close()
    payload = _payload()
    wrapped = "### WeChat Official Account portfolio\n" + json.dumps(payload, ensure_ascii=False)

    assert decode_browser_portfolio_result(wrapped) == payload
    result = enrich_tool_result_with_evidence(
        tool_name="mcp_marketing_browser_browser_collect_wechat_official_portfolio",
        args={},
        result=wrapped,
        task_id="session-1",
        session_id="session-1",
        tool_call_id="browser-call-1",
    )

    assert "Marketing OS owned-account capture" in result
    assert AccountPortfolioRepository().latest(
        user_id="default", account_id="acct-wechat"
    )["source_count"] == 3
    assert AccountPortfolioRepository().latest(
        user_id="default", account_id="other-account"
    )["status"] == "not_collected"
