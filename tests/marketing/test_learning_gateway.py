from __future__ import annotations

import hermes_state
import pytest

from agent.marketing.domains import AccountLifecycleRepository
from agent.marketing.intelligence import OperatingLoopRepository
from agent.marketing.intelligence.learning_governance import (
    propose_weight_candidate_from_recent_retros,
)
from hermes_state import SessionDB
from tui_gateway import server


def _retro() -> dict:
    return {
        "kind": "published_metric_retro",
        "metric_labels": {
            "labels": {
                "attention": {"bucket": "high"},
                "retention": {"bucket": "low"},
                "action": {"bucket": "mid"},
                "risk": {"bucket": "low"},
            }
        },
        "retro": {"bias_direction": "over"},
        "influence_score": {"score": 52.0},
    }


def _request(method: str, params: dict, *, request_id: str) -> dict:
    return server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }
    )


def test_gateway_exposes_no_learning_candidate_read_or_decision_surface(
    tmp_path, monkeypatch
):
    state_path = tmp_path / "state.db"
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setattr(hermes_state, "DEFAULT_DB_PATH", state_path)
    db = SessionDB(db_path=state_path)
    monkeypatch.setattr(server, "_db", db)
    try:
        AccountLifecycleRepository().begin_project(
            user_id="default",
            account_id="acct-1",
            business_goal="让真实回执持续校准预演",
        )
        loop = OperatingLoopRepository()
        for index in range(3):
            loop.create_learning_candidate(
                candidate_type="memory",
                user_id="default",
                account_id="acct-1",
                platform="douyin",
                proposal=_retro(),
                evidence_refs=[f"metric-{index}"],
                confidence=0.75,
            )
        weight = propose_weight_candidate_from_recent_retros(
            loop,
            user_id="default",
            account_id="acct-1",
            platform="douyin",
        )
        weight_id = weight["weight_candidate_id"]

        with pytest.raises(PermissionError, match="native system authority"):
            loop.decide_learning_candidate(
                weight_id,
                status="accepted",
                reason="a direct caller must not govern system learning",
            )

        listed = _request(
            "marketing.learning.candidates.list",
            {"account_id": "acct-1", "candidate_type": "weight"},
            request_id="list",
        )
        refused = _request(
            "marketing.learning.candidate.decide",
            {
                "account_id": "acct-1",
                "candidate_id": weight_id,
                "decision": "accepted",
                "reason": "reviewed replay",
            },
            request_id="refused",
        )
        confirmed_attempt = _request(
            "marketing.learning.candidate.decide",
            {
                "account_id": "acct-1",
                "candidate_id": weight_id,
                "decision": "accepted",
                "reason": "three consistent real-result retrospectives",
                "confirmed": True,
            },
            request_id="confirmed-attempt",
        )

        assert listed["error"]["code"] == -32601
        assert refused["error"]["code"] == -32601
        assert confirmed_attempt["error"]["code"] == -32601
        assert loop.get_learning_candidate(weight_id)["status"] == "pending"
    finally:
        db.close()
