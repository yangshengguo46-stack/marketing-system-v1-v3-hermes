"""RUN-16: Upstream upgrade strategy tests.

Verifies:
1. Hermes commit is pinned and matches expected hash
2. Adapter contract (tool manifest) is stable and well-defined
3. Contract diff detects breaking changes (removed/changed tools)
4. Shadow eval framework compares old vs new adapter outputs
5. Upgrade evaluation produces correct recommendation
6. Rollback path exists (switch back to pinned commit)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

ENGINE_ROOT = Path(__file__).parent.parent / "engine"
SCRIPTS_ROOT = Path(__file__).parent.parent / "scripts"
for root in (ENGINE_ROOT, SCRIPTS_ROOT):
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

from upgrade_strategy import (
    PINNED_HERMES_COMMIT,
    PINNED_HERMES_PRODUCT_TREE,
    get_hermes_commit,
    verify_hermes_pin,
    get_tool_contract,
    diff_contracts,
    run_shadow_eval,
    evaluate_upgrade,
    ShadowEvalResult,
)


class TestHermesCommitPin:
    """Hermes agent must be pinned to a specific commit."""

    def test_pinned_commit_is_set(self):
        assert PINNED_HERMES_COMMIT
        assert len(PINNED_HERMES_COMMIT) == 40  # SHA-1 hash length
        assert len(PINNED_HERMES_PRODUCT_TREE) == 40

    def test_get_hermes_commit_returns_hash(self):
        commit = get_hermes_commit()
        assert len(commit) == 40
        assert all(c in "0123456789abcdef" for c in commit)

    def test_verify_hermes_pin_matches(self):
        result = verify_hermes_pin()
        assert result["matches"] is True
        assert result["pinned"] == result["current"]
        assert result["baseline_commit"] == PINNED_HERMES_COMMIT
        assert result["product_tree"] == PINNED_HERMES_PRODUCT_TREE
        assert result["dirty"] is False

    def test_verify_hermes_pin_detects_mismatch(self):
        with patch("upgrade_strategy.subprocess.run") as run:
            run.side_effect = [
                MagicMock(stdout="0" * 40 + "\n"),
                MagicMock(stdout=""),
            ]
            result = verify_hermes_pin()
            assert result["matches"] is False
            assert result["current"] == "0" * 40


class TestAdapterContract:
    """Adapter contract must be stable and well-defined."""

    def test_contract_has_tools(self):
        contract = get_tool_contract()
        assert len(contract) > 0

    def test_contract_tools_have_required_fields(self):
        contract = get_tool_contract()
        for name, spec in contract.items():
            assert "level" in spec, f"{name} missing level"
            assert "requires_approval" in spec, f"{name} missing requires_approval"
            assert "description" in spec, f"{name} missing description"
            assert "schema_properties" in spec, f"{name} missing schema_properties"

    def test_contract_tool_names_use_marketing_prefix(self):
        contract = get_tool_contract()
        for name in contract:
            assert name.startswith("marketing_"), f"Tool {name} doesn't use marketing_ prefix"

    def test_contract_is_serializable(self):
        contract = get_tool_contract()
        serialized = json.dumps(contract)
        deserialized = json.loads(serialized)
        assert deserialized == contract


class TestContractDiff:
    """Contract diff must detect breaking changes."""

    def test_identical_contracts_no_diff(self):
        c = {"marketing_read_trends": {"level": "read", "requires_approval": False}}
        diff = diff_contracts(c, c)
        assert diff["added"] == []
        assert diff["removed"] == []
        assert diff["changed"] == {}
        assert diff["is_breaking"] is False

    def test_added_tool_is_not_breaking(self):
        old = {"marketing_read_trends": {"level": "read"}}
        new = {"marketing_read_trends": {"level": "read"}, "marketing_new_tool": {"level": "read"}}
        diff = diff_contracts(old, new)
        assert "marketing_new_tool" in diff["added"]
        assert diff["is_breaking"] is False

    def test_removed_tool_is_breaking(self):
        old = {"marketing_read_trends": {"level": "read"}, "marketing_old_tool": {"level": "read"}}
        new = {"marketing_read_trends": {"level": "read"}}
        diff = diff_contracts(old, new)
        assert "marketing_old_tool" in diff["removed"]
        assert diff["is_breaking"] is True

    def test_changed_tool_is_breaking(self):
        old = {"marketing_read_trends": {"level": "read", "requires_approval": False}}
        new = {"marketing_read_trends": {"level": "controlled", "requires_approval": True}}
        diff = diff_contracts(old, new)
        assert "marketing_read_trends" in diff["changed"]
        assert diff["is_breaking"] is True

    def test_schema_property_change_is_breaking(self):
        old = {"marketing_read_trends": {"schema_properties": ["platform", "limit"]}}
        new = {"marketing_read_trends": {"schema_properties": ["platform"]}}
        diff = diff_contracts(old, new)
        assert diff["is_breaking"] is True


class TestShadowEval:
    """Shadow eval framework compares old vs new adapter."""

    def test_shadow_eval_returns_result(self):
        result = run_shadow_eval(
            "marketing_read_trends",
            {"platform": "douyin"},
            old_contract={},
            new_contract={},
        )
        assert result.tool_name == "marketing_read_trends"
        assert result.match is True

    def test_shadow_eval_with_unknown_tool_raises(self):
        with pytest.raises(ValueError, match="Tool not found"):
            run_shadow_eval("nonexistent_tool", {}, {}, {})


class TestEvaluateUpgrade:
    """Full upgrade evaluation produces recommendation."""

    def test_proceed_when_no_breaking_and_all_match(self):
        contract = get_tool_contract()
        result = evaluate_upgrade(
            old_contract=contract,
            new_contract=contract,
            test_cases=[{"tool_name": "marketing_read_trends", "params": {}}],
        )
        assert result["recommendation"] == "proceed"
        assert result["contract_diff"]["is_breaking"] is False

    def test_block_when_breaking_change(self):
        old = {"marketing_read_trends": {"level": "read"}}
        new = {"marketing_read_trends": {"level": "controlled"}}
        result = evaluate_upgrade(
            old_contract=old,
            new_contract=new,
            test_cases=[],
        )
        assert result["recommendation"] == "block"
        assert result["contract_diff"]["is_breaking"] is True

    def test_investigate_when_shadow_mismatch(self):
        contract = get_tool_contract()
        with patch("upgrade_strategy.run_shadow_eval") as mock_eval:
            mock_eval.return_value = ShadowEvalResult(
                tool_name="marketing_read_trends",
                old_result="ok",
                new_result="different",
                match=False,
                params={},
            )
            result = evaluate_upgrade(
                old_contract=contract,
                new_contract=contract,
                test_cases=[{"tool_name": "marketing_read_trends", "params": {}}],
            )
        assert result["recommendation"] == "investigate"

    def test_investigate_when_shadow_raises(self):
        contract = get_tool_contract()
        with patch("upgrade_strategy.run_shadow_eval") as mock_eval:
            mock_eval.side_effect = RuntimeError("connection failed")
            result = evaluate_upgrade(
                old_contract=contract,
                new_contract=contract,
                test_cases=[{"tool_name": "marketing_read_trends", "params": {}}],
            )
        assert result["recommendation"] == "investigate"
        assert result["shadow_results"][0]["match"] is False

    def test_eval_result_has_contract_diff(self):
        result = evaluate_upgrade({}, {}, [])
        assert "contract_diff" in result
        assert "added" in result["contract_diff"]
        assert "removed" in result["contract_diff"]

    def test_eval_result_has_shadow_results(self):
        result = evaluate_upgrade({}, {}, [])
        assert "shadow_results" in result
        assert isinstance(result["shadow_results"], list)


class TestRollbackPath:
    """Verify rollback identity includes baseline plus product patch tree."""

    def test_pinned_commit_is_documented(self):
        result = verify_hermes_pin()
        assert "pinned" in result
        assert result["pinned"] == PINNED_HERMES_PRODUCT_TREE
        assert result["baseline_commit"] == PINNED_HERMES_COMMIT

    def test_contract_snapshot_can_be_saved(self, tmp_path):
        """Contract snapshot can be saved for rollback comparison."""
        contract = get_tool_contract()
        snapshot_path = tmp_path / "contract_snapshot.json"
        snapshot_path.write_text(json.dumps(contract, indent=2))
        assert snapshot_path.exists()

        loaded = json.loads(snapshot_path.read_text())
        assert loaded == contract
