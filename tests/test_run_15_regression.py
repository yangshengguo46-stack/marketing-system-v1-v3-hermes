"""RUN-15: Agent regression evaluation dataset and runner tests.

Validates that the regression dataset is well-formed, covers all 7 required
categories, and the runner correctly detects structural violations.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

EVAL_DIR = Path(__file__).parent / "eval"
DATASET_PATH = EVAL_DIR / "regression_dataset.json"

# Ensure eval dir is importable
sys.path.insert(0, str(EVAL_DIR))
from run_regression import (  # noqa: E402
    load_dataset,
    run_all,
    validate_dataset_structure,
    validate_greeting_cases,
    validate_refusal_cases,
    validate_evidence_cases,
    validate_approval_cases,
    validate_recovery_cases,
    validate_injection_resistance,
)


@pytest.fixture
def dataset():
    return load_dataset()


class TestDatasetStructure:
    def test_dataset_exists(self):
        assert DATASET_PATH.exists()

    def test_dataset_has_version(self, dataset):
        assert "version" in dataset
        assert dataset["version"] == 1

    def test_dataset_has_7_categories(self, dataset):
        assert len(dataset["categories"]) == 7

    def test_required_categories_present(self, dataset):
        ids = {c["id"] for c in dataset["categories"]}
        required = {"greeting", "industry_research", "refusal", "evidence", "approval", "recovery", "injection"}
        assert required == ids

    def test_all_cases_have_unique_ids(self, dataset):
        ids = []
        for cat in dataset["categories"]:
            for case in cat["cases"]:
                ids.append(case["id"])
        assert len(ids) == len(set(ids))

    def test_all_cases_have_input_and_expectations(self, dataset):
        for cat in dataset["categories"]:
            for case in cat["cases"]:
                assert "input" in case, f"case {case['id']} missing input"
                assert "expectations" in case, f"case {case['id']} missing expectations"
                assert "should_respond" in case["expectations"]
                assert "max_response_time_ms" in case["expectations"]

    def test_at_least_2_cases_per_category(self, dataset):
        for cat in dataset["categories"]:
            assert len(cat["cases"]) >= 2, f"category {cat['id']} has fewer than 2 cases"

    def test_total_cases_at_least_15(self, dataset):
        total = sum(len(c["cases"]) for c in dataset["categories"])
        assert total >= 15

    def test_structure_validation_passes(self, dataset):
        errors = validate_dataset_structure(dataset)
        assert errors == []

    def test_run_all_passes(self, dataset):
        result = run_all(dataset)
        assert result["passed"], f"errors: {result['errors']}"


class TestGreetingCategory:
    def test_no_tool_calls(self, dataset):
        errors = validate_greeting_cases(dataset)
        assert errors == []

    def test_no_plan_creation(self, dataset):
        for cat in dataset["categories"]:
            if cat["id"] != "greeting":
                continue
            for case in cat["cases"]:
                assert not case["expectations"].get("should_create_plan")


class TestRefusalCategory:
    def test_all_cases_refuse(self, dataset):
        errors = validate_refusal_cases(dataset)
        assert errors == []

    def test_no_tool_calls(self, dataset):
        for cat in dataset["categories"]:
            if cat["id"] != "refusal":
                continue
            for case in cat["cases"]:
                assert not case["expectations"].get("should_call_tools")


class TestEvidenceCategory:
    def test_all_require_source(self, dataset):
        errors = validate_evidence_cases(dataset)
        assert errors == []

    def test_all_call_tools(self, dataset):
        for cat in dataset["categories"]:
            if cat["id"] != "evidence":
                continue
            for case in cat["cases"]:
                assert case["expectations"].get("should_call_tools")


class TestApprovalCategory:
    def test_all_trigger_approval(self, dataset):
        errors = validate_approval_cases(dataset)
        assert errors == []


class TestRecoveryCategory:
    def test_checkpoint_expectations(self, dataset):
        errors = validate_recovery_cases(dataset)
        assert errors == []

    def test_replan_case_has_context(self, dataset):
        for cat in dataset["categories"]:
            if cat["id"] != "recovery":
                continue
            for case in cat["cases"]:
                ctx = case.get("context", {})
                if ctx.get("is_replan"):
                    assert ctx.get("must_keep_completed_steps")
                    assert ctx.get("must_discard_pending_steps")


class TestInjectionCategory:
    def test_all_have_guards(self, dataset):
        errors = validate_injection_resistance(dataset)
        assert errors == []

    def test_all_treat_as_data(self, dataset):
        for cat in dataset["categories"]:
            if cat["id"] != "injection":
                continue
            for case in cat["cases"]:
                assert case["expectations"].get("should_treat_input_as_data")


class TestRunnerNegativeCases:
    def test_detects_missing_category(self):
        data = {"version": 1, "categories": []}
        result = run_all(data)
        assert not result["passed"]

    def test_detects_refusal_with_tools(self):
        data = {
            "version": 1,
            "categories": [
                {
                    "id": "refusal",
                    "name": "拒答",
                    "cases": [
                        {
                            "id": "rf-bad",
                            "input": "test",
                            "expectations": {
                                "should_respond": True,
                                "should_call_tools": True,
                                "should_refuse": True,
                                "max_response_time_ms": 1000,
                            },
                        }
                    ],
                }
            ],
        }
        errors = validate_refusal_cases(data)
        assert len(errors) > 0

    def test_detects_injection_without_guards(self):
        data = {
            "version": 1,
            "categories": [
                {
                    "id": "injection",
                    "name": "注入",
                    "cases": [
                        {
                            "id": "in-bad",
                            "input": "test",
                            "expectations": {
                                "should_respond": True,
                                "max_response_time_ms": 1000,
                            },
                        }
                    ],
                }
            ],
        }
        errors = validate_injection_resistance(data)
        assert len(errors) > 0

    def test_detects_duplicate_case_ids(self):
        data = {
            "version": 1,
            "categories": [
                {
                    "id": "greeting",
                    "name": "寒暄",
                    "cases": [
                        {"id": "dup", "input": "a", "expectations": {"should_respond": True, "max_response_time_ms": 1000}},
                        {"id": "dup", "input": "b", "expectations": {"should_respond": True, "max_response_time_ms": 1000}},
                    ],
                }
            ],
        }
        errors = validate_dataset_structure(data)
        assert any("duplicate" in e for e in errors)
