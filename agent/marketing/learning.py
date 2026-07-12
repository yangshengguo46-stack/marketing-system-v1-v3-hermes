"""Governed projection from reviewed learning into its native Hermes owner."""

from __future__ import annotations

from agent.marketing.data_paths import MarketingDataPaths
from agent.marketing.domains.account_strategy import AccountStrategyRepository
from agent.marketing.domains.knowledge_bases import KnowledgeBaseRepository
from agent.marketing.intelligence.store import OperatingLoopRepository


class AccountLearningGovernance:
    """Accept one reviewed candidate and route it to account truth by type."""

    def __init__(self, paths: MarketingDataPaths | None = None):
        self.paths = paths or MarketingDataPaths.from_env()
        self.loop = OperatingLoopRepository(self.paths)
        self.knowledge = KnowledgeBaseRepository(self.paths)
        self.strategy = AccountStrategyRepository(self.paths)

    def accept_and_project(
        self,
        candidate_id: str,
        *,
        reason: str,
        topic: str | None = None,
    ) -> dict:
        reason_value = str(reason or "").strip()
        if not reason_value:
            raise ValueError("account learning acceptance requires a review reason")
        candidate = self.loop.get_learning_candidate(candidate_id)
        candidate_type = str(candidate.get("candidate_type") or "")
        if candidate_type == "weight":
            raise ValueError(
                "weight candidates require replay approval before strategy projection"
            )
        if candidate_type == "skill":
            raise ValueError(
                "skill candidates require the native Skill review and write-approval flow"
            )
        proposal = candidate.get("proposal") or {}
        if candidate_type == "strategy" and proposal.get("kind") != "account_influence_calibration":
            raise ValueError("unsupported strategy learning projection")
        accepted = self.loop.decide_learning_candidate(
            candidate_id, status="accepted", reason=reason_value
        )
        result = {"candidate": accepted}
        if candidate_type == "memory":
            result["account_knowledge"] = self.knowledge.promote_account_learning(
                user_id=accepted["user_id"],
                account_id=accepted["account_id"],
                candidate_id=accepted["id"],
                topic=topic,
            )
        if candidate_type == "strategy":
            result["account_strategy"] = self.strategy.apply_learning_calibration(
                user_id=accepted["user_id"],
                account_id=accepted["account_id"],
                candidate_id=accepted["id"],
            )
        return result
