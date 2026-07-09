from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))

from agent_core.preflight_decision import build_preflight_decision, build_score_preflight_decision


def _score(score: float, *, risk: float = 0.0, decision: str = "strong_go") -> dict:
    return {
        "version": "influenceos-score-v0.1",
        "score": score,
        "decision": decision,
        "confidence": 0.8,
        "components": {
            "PlatformReachPotential": {"value": 0.8, "source": "test", "why": "平台适配"},
            "HumanAttentionKernel": {"value": 0.8, "source": "test", "why": "能抓注意力"},
            "RetentionDesign": {"value": 0.7, "source": "test", "why": "结构成立"},
            "BusinessValue": {"value": 0.7, "source": "test", "why": "行动路径明确"},
            "RiskPenalty": {"value": risk, "source": "test", "why": "风险"},
        },
        "missing_dimensions": [],
    }


def test_preflight_decision_maps_ready_by_stage():
    result = build_preflight_decision(
        _score(74),
        stage="publish_review",
        context={"selected_lane": "article_soft"},
    )

    assert result["version"] == "preflight-decision-v0.1"
    assert result["status"] == "ready_for_publish_review"
    assert result["go"] is True
    assert result["action"] == "prepare_publish_review"
    assert "发布" in result["next_action"]
    assert result["ui"]["tone"] == "positive"
    assert "prediction vs actual 复盘" in result["watch_metrics"]


def test_preflight_decision_hard_gates_override_high_score():
    result = build_preflight_decision(
        _score(82),
        stage="production_draft",
        context={
            "selected_lane": "article_soft",
            "blockers": ["audience_context_missing", "url_evidence_missing"],
        },
    )

    assert result["status"] == "needs_audience_context"
    assert result["go"] is False
    assert result["action"] == "collect_context"
    assert "补齐目标受众" in result["next_action"]
    assert "url_evidence_missing" in result["blockers"]


def test_preflight_decision_blocks_high_risk():
    result = build_preflight_decision(
        _score(77, risk=0.82),
        stage="launch",
        context={"selected_lane": "faceless_video"},
    )

    assert result["status"] == "blocked_by_risk"
    assert result["go"] is False
    assert result["ui"]["tone"] == "danger"
    assert "降低标题党" in result["required_next_steps"][0]


def test_score_preflight_decision_accepts_feature_payload_without_state():
    result = build_score_preflight_decision({
        "preflight_scores": {
            "platform_fit": 0.82,
            "production_feasibility": 0.78,
            "evidence_strength": 0.7,
            "audience_fit": 0.75,
            "business_value": 0.7,
            "cost_safety": 0.8,
        },
        "context": {"selected_lane": "article_soft"},
    })

    assert result["influence_score"]["version"] == "influenceos-score-v0.1"
    assert result["preflight_decision"]["version"] == "preflight-decision-v0.1"
    assert result["preflight_decision"]["status"] in {
        "ready_for_asset_draft",
        "needs_revision",
    }
