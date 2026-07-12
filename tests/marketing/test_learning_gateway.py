from __future__ import annotations

import hermes_state

from agent.marketing.domains import AccountLifecycleRepository, AccountStrategyRepository
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


def test_gateway_lists_and_projects_learning_only_after_scoped_confirmation(
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
        cross_account = _request(
            "marketing.learning.candidate.decide",
            {
                "account_id": "acct-other",
                "candidate_id": weight_id,
                "decision": "accepted",
                "reason": "wrong scope",
                "confirmed": True,
            },
            request_id="cross-account",
        )
        replayed = _request(
            "marketing.learning.candidate.decide",
            {
                "account_id": "acct-1",
                "candidate_id": weight_id,
                "decision": "accepted",
                "reason": "three consistent real-result retrospectives",
                "confirmed": True,
            },
            request_id="replayed",
        )
        strategy_id = replayed["result"]["strategy_candidate_id"]
        projected = _request(
            "marketing.learning.candidate.decide",
            {
                "account_id": "acct-1",
                "candidate_id": strategy_id,
                "decision": "accepted",
                "reason": "approved bounded retention calibration",
                "confirmed": True,
            },
            request_id="projected",
        )

        assert listed["result"]["total"] == 1
        assert listed["result"]["candidates"][0]["id"] == weight_id
        assert refused["error"]["code"] == 4095
        assert cross_account["error"]["code"] == 4044
        assert replayed["result"]["replay"]["status"] == "passed"
        assert projected["result"]["account_strategy"]["status"] == "active"
        calibration = AccountStrategyRepository().get_active_influence_calibration(
            user_id="default", account_id="acct-1"
        )
        assert calibration["source_candidate_id"] == strategy_id
        assert calibration["weights"]["RetentionDesign"] > 0.16
    finally:
        db.close()
