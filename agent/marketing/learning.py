"""Governed bridge from accepted learning into account knowledge."""

from __future__ import annotations

from agent.marketing.data_paths import MarketingDataPaths
from agent.marketing.domains.knowledge_bases import KnowledgeBaseRepository
from agent.marketing.intelligence.store import OperatingLoopRepository


class AccountLearningGovernance:
    """Accept and project one reviewed candidate as a single product action."""

    def __init__(self, paths: MarketingDataPaths | None = None):
        self.paths = paths or MarketingDataPaths.from_env()
        self.loop = OperatingLoopRepository(self.paths)
        self.knowledge = KnowledgeBaseRepository(self.paths)

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
        accepted = self.loop.decide_learning_candidate(
            candidate_id, status="accepted", reason=reason_value
        )
        entry = self.knowledge.promote_account_learning(
            user_id=accepted["user_id"],
            account_id=accepted["account_id"],
            candidate_id=accepted["id"],
            topic=topic,
        )
        return {"candidate": accepted, "account_knowledge": entry}
