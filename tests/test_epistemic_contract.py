from __future__ import annotations

import pytest

from agent.epistemic_contract import (
    CONTRACTS,
    EpistemicClass,
    SystemAuthority,
    _issue_system_authority,
    contract_projection,
    require_system_authority,
    require_user_confirmation,
)


def test_user_authority_is_limited_to_self_report_choice_and_effect_authorization():
    user_classes = {
        item.epistemic_class for item in CONTRACTS.values() if item.user_confirmable
    }
    assert user_classes == {
        EpistemicClass.USER_SELF_REPORT,
        EpistemicClass.STRATEGIC_CHOICE,
        EpistemicClass.EXTERNAL_ACTION,
    }
    for epistemic_class in user_classes:
        assert require_user_confirmation(
            epistemic_class, confirmed_by_user=True
        ).authority
        with pytest.raises(ValueError, match="explicit user confirmation"):
            require_user_confirmation(epistemic_class, confirmed_by_user=False)


def test_user_confirmation_cannot_settle_fact_learning_or_human_research():
    for epistemic_class in (
        EpistemicClass.OBSERVED_FACT,
        EpistemicClass.DERIVED_KNOWLEDGE,
        EpistemicClass.HUMAN_RESEARCH,
    ):
        with pytest.raises(PermissionError, match="cannot be accepted"):
            require_user_confirmation(epistemic_class, confirmed_by_user=True)


def test_system_authority_is_a_non_serializable_native_capability():
    with pytest.raises(PermissionError, match="native runtime"):
        SystemAuthority("forged", object())

    authority = _issue_system_authority("epistemic_contract_test")
    contract = require_system_authority(
        authority, EpistemicClass.DERIVED_KNOWLEDGE
    )
    assert authority.owner == "epistemic_contract_test"
    assert contract.system_governed is True
    with pytest.raises(PermissionError, match="native system authority"):
        require_system_authority(None, EpistemicClass.DERIVED_KNOWLEDGE)


def test_read_projection_contains_policy_but_no_write_capability():
    projection = contract_projection(EpistemicClass.OBSERVED_FACT)
    assert projection["user_confirmable"] is False
    assert projection["immutable_history"] is True
    assert projection["challenge_path"].startswith("attach contradictory evidence")
    assert "seal" not in projection
