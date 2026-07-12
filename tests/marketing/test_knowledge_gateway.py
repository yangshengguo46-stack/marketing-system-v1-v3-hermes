from __future__ import annotations

import sqlite3

import hermes_state
from agent.marketing.data_paths import MarketingDataPaths
from agent.marketing.domains import KnowledgeFlywheelRepository
from hermes_state import SessionDB
from tui_gateway import server


def test_gateway_lists_scoped_consent_records_and_requires_confirmed_withdrawal(
    tmp_path, monkeypatch
):
    state_path = tmp_path / "state.db"
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setattr(hermes_state, "DEFAULT_DB_PATH", state_path)
    db = SessionDB(db_path=state_path)
    monkeypatch.setattr(server, "_db", db)
    sql = sqlite3.connect(state_path)
    try:
        sql.execute(
            """INSERT INTO marketing_learning_candidates
            (id,candidate_type,user_id,account_id,receipt_refs_json,evidence_refs_json,
             proposal_json,confidence,status,created_at)
            VALUES ('learn-gateway','strategy','default','acct-1','[]','[]','{}',0.8,
                    'accepted','t0')"""
        )
        sql.commit()
    finally:
        sql.close()
    repository = KnowledgeFlywheelRepository(
        MarketingDataPaths(tmp_path, tmp_path / "config", state_path)
    )
    contribution = repository.create_contribution(
        user_id="default",
        account_id="acct-1",
        source_candidate_id="learn-gateway",
        consent_ref="consent-gateway",
        schema_version="knowledge.v1",
        cohort={"platform": "zhihu"},
        features={"hook_type": "question"},
        outcomes={"save_rate": 0.04},
    )
    try:
        listed = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": "list-consent",
                "method": "marketing.knowledge.contributions.list",
                "params": {"account_id": "acct-1"},
            }
        )
        refused = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": "withdraw-unconfirmed",
                "method": "marketing.knowledge.contribution.withdraw",
                "params": {
                    "account_id": "acct-1",
                    "contribution_id": contribution["id"],
                },
            }
        )
        withdrawn = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": "withdraw-confirmed",
                "method": "marketing.knowledge.contribution.withdraw",
                "params": {
                    "account_id": "acct-1",
                    "contribution_id": contribution["id"],
                    "confirmed": True,
                },
            }
        )

        assert listed["result"]["total"] == 1
        assert refused["error"]["code"] == 4095
        assert withdrawn["result"]["contribution"]["status"] == "withheld"
        assert withdrawn["result"]["contribution"]["features"] == {}
    finally:
        db.close()
