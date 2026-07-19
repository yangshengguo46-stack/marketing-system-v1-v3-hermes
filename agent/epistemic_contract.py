"""Native authority contract for facts, preferences, decisions, and learning.

The contract answers a question that cannot be left to prompt wording: who is
allowed to settle each kind of record?  User authority over self-description
and consequential choices is preserved without turning user opinion into
objective fact.  Evidence-backed facts and system learning remain contestable
through new evidence, but they are never accepted or rejected by conversation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final


class EpistemicClass(StrEnum):
    """Stable classes used by native owners and product guidance."""

    USER_SELF_REPORT = "user_self_report"
    STRATEGIC_CHOICE = "strategic_choice"
    EXTERNAL_ACTION = "external_action"
    OBSERVED_FACT = "observed_fact"
    DERIVED_KNOWLEDGE = "derived_knowledge"
    HUMAN_RESEARCH = "human_research"


@dataclass(frozen=True, slots=True)
class EpistemicContract:
    epistemic_class: EpistemicClass
    authority: str
    user_confirmable: bool
    user_mutable: bool
    system_governed: bool
    immutable_history: bool
    challenge_path: str
    truth_scope: str


CONTRACTS: Final[dict[EpistemicClass, EpistemicContract]] = {
    EpistemicClass.USER_SELF_REPORT: EpistemicContract(
        epistemic_class=EpistemicClass.USER_SELF_REPORT,
        authority="user",
        user_confirmable=True,
        user_mutable=True,
        system_governed=False,
        immutable_history=False,
        challenge_path="user may correct or revoke the current self-report",
        truth_scope="what the user says about their preference, goal, boundary, or identity",
    ),
    EpistemicClass.STRATEGIC_CHOICE: EpistemicContract(
        epistemic_class=EpistemicClass.STRATEGIC_CHOICE,
        authority="user_choice_with_agent_evidence",
        user_confirmable=True,
        user_mutable=True,
        system_governed=False,
        immutable_history=True,
        challenge_path="create a new version; never rewrite the decision that governed an old action",
        truth_scope="the direction the user chooses, not a claim that the market agrees",
    ),
    EpistemicClass.EXTERNAL_ACTION: EpistemicContract(
        epistemic_class=EpistemicClass.EXTERNAL_ACTION,
        authority="user_authorization_then_external_receipt",
        user_confirmable=True,
        user_mutable=False,
        system_governed=False,
        immutable_history=True,
        challenge_path="cancel before execution or reconcile the external receipt after execution",
        truth_scope="authorization permits an effect; only the receipt establishes what happened",
    ),
    EpistemicClass.OBSERVED_FACT: EpistemicContract(
        epistemic_class=EpistemicClass.OBSERVED_FACT,
        authority="verified_source_or_receipt_owner",
        user_confirmable=False,
        user_mutable=False,
        system_governed=True,
        immutable_history=True,
        challenge_path="attach contradictory evidence and supersede; never edit the observation",
        truth_scope="a bounded observation with source, time, scope, and provenance",
    ),
    EpistemicClass.DERIVED_KNOWLEDGE: EpistemicContract(
        epistemic_class=EpistemicClass.DERIVED_KNOWLEDGE,
        authority="system_evidence_replay_and_conflict_gates",
        user_confirmable=False,
        user_mutable=False,
        system_governed=True,
        immutable_history=True,
        challenge_path="new receipts, counterevidence, expiry, conflict, or failed replay",
        truth_scope="a versioned inference; never an unqualified fact or user-governed opinion",
    ),
    EpistemicClass.HUMAN_RESEARCH: EpistemicContract(
        epistemic_class=EpistemicClass.HUMAN_RESEARCH,
        authority="silent_human_observer",
        user_confirmable=False,
        user_mutable=False,
        system_governed=True,
        immutable_history=True,
        challenge_path="sealed prediction outcomes, counterevidence, cross-context evaluation, and revision",
        truth_scope="a falsifiable research lens about human behavior, never a diagnosis",
    ),
}


_AUTHORITY_SEAL: Final[object] = object()


class SystemAuthority:
    """Unforgeable-by-API capability passed between native system owners.

    Python code in the trusted runtime can deliberately mint the private
    capability.  RPCs, tools, prompts, and renderer payloads cannot construct
    one because the seal is never serialized or accepted as input.
    """

    __slots__ = ("owner", "_seal")

    def __init__(self, owner: str, seal: object):
        if seal is not _AUTHORITY_SEAL:
            raise PermissionError("system authority can only be issued by the native runtime")
        value = str(owner or "").strip()
        if not value:
            raise ValueError("system authority owner is required")
        self.owner = value
        self._seal = seal


def _issue_system_authority(owner: str) -> SystemAuthority:
    """Issue a process-local capability to a native background owner.

    This function is intentionally private and must never be registered as a
    tool, RPC, plugin hook, or renderer bridge.
    """

    return SystemAuthority(owner, _AUTHORITY_SEAL)


def require_system_authority(
    authority: SystemAuthority | None,
    epistemic_class: EpistemicClass,
) -> EpistemicContract:
    contract = CONTRACTS[epistemic_class]
    if not contract.system_governed:
        raise PermissionError(f"{epistemic_class} is not governed by a system learning owner")
    if not isinstance(authority, SystemAuthority) or authority._seal is not _AUTHORITY_SEAL:
        raise PermissionError(
            f"{epistemic_class} requires a native system authority capability"
        )
    return contract


def require_user_confirmation(
    epistemic_class: EpistemicClass,
    *,
    confirmed_by_user: bool,
) -> EpistemicContract:
    contract = CONTRACTS[epistemic_class]
    if not contract.user_confirmable:
        raise PermissionError(
            f"{epistemic_class} cannot be accepted, rejected, or rewritten by user confirmation"
        )
    if confirmed_by_user is not True:
        raise ValueError("explicit user confirmation is required")
    return contract


def contract_projection(epistemic_class: EpistemicClass) -> dict[str, object]:
    """Return a serializable read projection without any write capability."""

    contract = CONTRACTS[epistemic_class]
    return {
        "epistemic_class": contract.epistemic_class.value,
        "authority": contract.authority,
        "user_confirmable": contract.user_confirmable,
        "user_mutable": contract.user_mutable,
        "system_governed": contract.system_governed,
        "immutable_history": contract.immutable_history,
        "challenge_path": contract.challenge_path,
        "truth_scope": contract.truth_scope,
    }


__all__ = [
    "CONTRACTS",
    "EpistemicClass",
    "EpistemicContract",
    "SystemAuthority",
    "contract_projection",
    "require_system_authority",
    "require_user_confirmation",
]
