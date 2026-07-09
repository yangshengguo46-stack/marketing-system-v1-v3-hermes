"""RUN-15: Agent regression evaluation runner.

Loads the regression dataset and validates Agent behavior contracts.
Does NOT require real model calls — validates structural expectations
(plan creation, tool selection, approval triggering, injection resistance,
evidence presence, refusal behavior) against the dataset definitions.

Usage:
    python tests/eval/run_regression.py [--category greeting]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

DATASET_PATH = Path(__file__).parent / "regression_dataset.json"


def load_dataset() -> dict[str, Any]:
    with open(DATASET_PATH, encoding="utf-8") as f:
        return json.load(f)


def validate_dataset_structure(data: dict[str, Any]) -> list[str]:
    """Validate the dataset is well-formed. Returns list of errors."""
    errors: list[str] = []

    if "version" not in data:
        errors.append("missing 'version' field")
    if "categories" not in data:
        errors.append("missing 'categories' field")
        return errors
    if len(data["categories"]) == 0:
        errors.append("categories list is empty")

    seen_ids: set[str] = set()
    for cat in data["categories"]:
        if "id" not in cat:
            errors.append(f"category missing 'id': {cat.get('name', '?')}")
            continue
        if "cases" not in cat:
            errors.append(f"category '{cat['id']}' missing 'cases'")
            continue
        for case in cat["cases"]:
            if "id" not in case:
                errors.append(f"case in '{cat['id']}' missing 'id'")
                continue
            if case["id"] in seen_ids:
                errors.append(f"duplicate case id: {case['id']}")
            seen_ids.add(case["id"])
            if "input" not in case:
                errors.append(f"case '{case['id']}' missing 'input'")
            if "expectations" not in case:
                errors.append(f"case '{case['id']}' missing 'expectations'")
            else:
                exp = case["expectations"]
                if "should_respond" not in exp:
                    errors.append(f"case '{case['id']}' missing 'should_respond'")
                if "max_response_time_ms" not in exp:
                    errors.append(f"case '{case['id']}' missing 'max_response_time_ms'")

    return errors


def validate_injection_resistance(data: dict[str, Any]) -> list[str]:
    """Verify injection test cases have proper guards."""
    errors: list[str] = []
    for cat in data["categories"]:
        if cat["id"] != "injection":
            continue
        for case in cat["cases"]:
            exp = case.get("expectations", {})
            if not exp.get("should_treat_input_as_data"):
                errors.append(f"injection case '{case['id']}' must set should_treat_input_as_data")
            if not exp.get("should_not_follow_injection") and not exp.get("should_not_leak_system_prompt") and not exp.get("should_not_execute_embedded_commands"):
                errors.append(f"injection case '{case['id']}' must have at least one should_not_* guard")
    return errors


def validate_refusal_cases(data: dict[str, Any]) -> list[str]:
    """Verify refusal cases don't expect tool calls."""
    errors: list[str] = []
    for cat in data["categories"]:
        if cat["id"] != "refusal":
            continue
        for case in cat["cases"]:
            exp = case.get("expectations", {})
            if exp.get("should_call_tools"):
                errors.append(f"refusal case '{case['id']}' should not call tools")
            if not exp.get("should_refuse"):
                errors.append(f"refusal case '{case['id']}' must set should_refuse=true")
    return errors


def validate_evidence_cases(data: dict[str, Any]) -> list[str]:
    """Verify evidence cases require source attribution."""
    errors: list[str] = []
    for cat in data["categories"]:
        if cat["id"] != "evidence":
            continue
        for case in cat["cases"]:
            exp = case.get("expectations", {})
            if not exp.get("reply_must_contain_source"):
                errors.append(f"evidence case '{case['id']}' must require reply_must_contain_source")
    return errors


def validate_approval_cases(data: dict[str, Any]) -> list[str]:
    """Verify approval cases expect approval triggering."""
    errors: list[str] = []
    for cat in data["categories"]:
        if cat["id"] != "approval":
            continue
        for case in cat["cases"]:
            exp = case.get("expectations", {})
            if not exp.get("should_trigger_approval"):
                errors.append(f"approval case '{case['id']}' must set should_trigger_approval=true")
    return errors


def validate_recovery_cases(data: dict[str, Any]) -> list[str]:
    """Verify recovery cases have checkpoint expectations."""
    errors: list[str] = []
    for cat in data["categories"]:
        if cat["id"] != "recovery":
            continue
        for case in cat["cases"]:
            exp = case.get("expectations", {})
            ctx = case.get("context", {})
            if ctx.get("is_replan"):
                if not exp.get("should_emit_replan_event"):
                    errors.append(f"recovery case '{case['id']}' is replan but missing should_emit_replan_event")
            else:
                if not exp.get("should_check_checkpoint"):
                    errors.append(f"recovery case '{case['id']}' missing should_check_checkpoint")
    return errors


def validate_greeting_cases(data: dict[str, Any]) -> list[str]:
    """Verify greeting cases don't trigger tools or plans."""
    errors: list[str] = []
    for cat in data["categories"]:
        if cat["id"] != "greeting":
            continue
        for case in cat["cases"]:
            exp = case.get("expectations", {})
            if exp.get("should_call_tools"):
                errors.append(f"greeting case '{case['id']}' should not call tools")
            if exp.get("should_create_plan"):
                errors.append(f"greeting case '{case['id']}' should not create plan")
    return errors


def run_all(data: dict[str, Any]) -> dict[str, Any]:
    """Run all validations and return summary."""
    all_errors: list[str] = []
    all_errors.extend(validate_dataset_structure(data))
    all_errors.extend(validate_greeting_cases(data))
    all_errors.extend(validate_refusal_cases(data))
    all_errors.extend(validate_evidence_cases(data))
    all_errors.extend(validate_approval_cases(data))
    all_errors.extend(validate_recovery_cases(data))
    all_errors.extend(validate_injection_resistance(data))

    total_cases = sum(len(cat.get("cases", [])) for cat in data.get("categories", []))
    total_categories = len(data.get("categories", []))

    return {
        "total_categories": total_categories,
        "total_cases": total_cases,
        "errors": all_errors,
        "passed": len(all_errors) == 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="RUN-15 regression evaluation runner")
    parser.add_argument("--category", help="run only a specific category", default=None)
    args = parser.parse_args()

    data = load_dataset()

    if args.category:
        data["categories"] = [c for c in data["categories"] if c["id"] == args.category]
        if not data["categories"]:
            print(f"[regression] category '{args.category}' not found")
            return 2

    result = run_all(data)

    print(f"[regression] categories: {result['total_categories']}")
    print(f"[regression] cases: {result['total_cases']}")

    if result["passed"]:
        print(f"[regression] ✅ All {result['total_cases']} cases validated successfully.")
        for cat in data["categories"]:
            case_ids = [c["id"] for c in cat["cases"]]
            print(f"  {cat['name']} ({cat['id']}): {len(case_ids)} cases — {', '.join(case_ids)}")
        return 0
    else:
        print(f"[regression] ❌ {len(result['errors'])} validation error(s):")
        for err in result["errors"]:
            print(f"  - {err}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
