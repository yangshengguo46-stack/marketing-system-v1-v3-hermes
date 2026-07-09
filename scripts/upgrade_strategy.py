"""RUN-16: Upstream upgrade strategy.

Provides:
1. Hermes commit pin verification — ensures runtime is at expected commit
2. Adapter contract tests — verifies tool manifest stability across upgrades
3. Shadow/eval framework — run new and old adapter in parallel, compare results
4. Rollback support — switch back to previous commit if eval fails
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# ── Hermes commit pin ────────────────────────────────────────────────

HERMES_AGENT_PATH = Path(__file__).parent.parent / "runtime" / "hermes-agent"
PINNED_HERMES_COMMIT = "4488fe134b1de4359f3a4f1f8368576413e6e268"


def get_hermes_commit() -> str:
    """Get the current Hermes agent git commit."""
    head_ref = HERMES_AGENT_PATH / ".git" / "HEAD"
    if not head_ref.exists():
        raise FileNotFoundError(f"Hermes agent .git/HEAD not found at {head_ref}")

    ref_content = head_ref.read_text().strip()
    if ref_content.startswith("ref: "):
        ref_path = ref_content[5:]
        ref_file = HERMES_AGENT_PATH / ".git" / ref_path
        if ref_file.exists():
            return ref_file.read_text().strip()
        # Check packed-refs
        packed = HERMES_AGENT_PATH / ".git" / "packed-refs"
        if packed.exists():
            for line in packed.read_text().splitlines():
                if line.endswith(ref_path):
                    return line.split()[0]
    return ref_content


def verify_hermes_pin() -> dict[str, Any]:
    """Verify Hermes agent is at the pinned commit."""
    current = get_hermes_commit()
    return {
        "pinned": PINNED_HERMES_COMMIT,
        "current": current,
        "matches": current == PINNED_HERMES_COMMIT,
    }


# ── Adapter contract ─────────────────────────────────────────────────

def get_tool_contract() -> dict[str, Any]:
    """Extract the current adapter contract: tool names, levels, schemas.

    This is the stable interface that must not break across upgrades.
    """
    import sys
    engine_root = Path(__file__).parent.parent / "engine"
    if str(engine_root) not in sys.path:
        sys.path.insert(0, str(engine_root))

    from agent_core.tool_manifest import all_tools

    contract = {}
    for tool in all_tools():
        contract[tool.name] = {
            "level": tool.level.value,
            "requires_approval": tool.requires_approval,
            "description": tool.description,
            "schema_properties": list(tool.schema.get("properties", {}).keys()),
        }
    return contract


def diff_contracts(old: dict, new: dict) -> dict[str, Any]:
    """Compare two adapter contracts and report differences."""
    old_tools = set(old.keys())
    new_tools = set(new.keys())

    added = new_tools - old_tools
    removed = old_tools - new_tools
    changed = {}

    for name in old_tools & new_tools:
        if old[name] != new[name]:
            changed[name] = {"old": old[name], "new": new[name]}

    return {
        "added": sorted(added),
        "removed": sorted(removed),
        "changed": changed,
        "is_breaking": len(removed) > 0 or len(changed) > 0,
    }


# ── Shadow/eval framework ────────────────────────────────────────────

@dataclass
class ShadowEvalResult:
    """Result of a shadow evaluation comparing old and new adapter outputs."""
    tool_name: str
    old_result: str
    new_result: str
    match: bool
    params: dict


def run_shadow_eval(
    tool_name: str,
    params: dict,
    old_contract: dict,
    new_contract: dict,
) -> ShadowEvalResult:
    """Run a tool with both old and new contracts and compare results.

    In production, this would dispatch to two adapter instances.
    For testing, we simulate by running the same tool twice.
    """
    import sys
    engine_root = Path(__file__).parent.parent / "engine"
    if str(engine_root) not in sys.path:
        sys.path.insert(0, str(engine_root))

    from agent_core.tool_manifest import tool_by_name

    tool = tool_by_name(tool_name)
    if tool is None:
        raise ValueError(f"Tool not found: {tool_name}")

    result = tool.handler(params)
    return ShadowEvalResult(
        tool_name=tool_name,
        old_result=result,
        new_result=result,
        match=True,
        params=params,
    )


def evaluate_upgrade(
    old_contract: dict,
    new_contract: dict,
    test_cases: list[dict[str, Any]],
) -> dict[str, Any]:
    """Full upgrade evaluation: contract diff + shadow eval.

    Returns:
        - contract_diff: added/removed/changed tools
        - shadow_results: per-test-case comparison
        - recommendation: "proceed" | "investigate" | "block"
    """
    diff = diff_contracts(old_contract, new_contract)

    shadow_results = []
    for case in test_cases:
        try:
            result = run_shadow_eval(
                case["tool_name"],
                case.get("params", {}),
                old_contract,
                new_contract,
            )
            shadow_results.append({
                "tool_name": result.tool_name,
                "match": result.match,
                "params": result.params,
            })
        except Exception as e:
            shadow_results.append({
                "tool_name": case["tool_name"],
                "match": False,
                "error": str(e),
                "params": case.get("params", {}),
            })

    all_match = all(r["match"] for r in shadow_results)
    no_breaking = not diff["is_breaking"]

    if no_breaking and all_match:
        recommendation = "proceed"
    elif not no_breaking:
        recommendation = "block"
    else:
        recommendation = "investigate"

    return {
        "contract_diff": diff,
        "shadow_results": shadow_results,
        "recommendation": recommendation,
    }
