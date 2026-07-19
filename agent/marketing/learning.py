"""System-governed projection from learning into its native Hermes owner."""

from __future__ import annotations

import json

from agent.epistemic_contract import (
    EpistemicClass,
    SystemAuthority,
    require_system_authority,
)
from agent.marketing.data_paths import MarketingDataPaths
from agent.marketing.domains.account_strategy import AccountStrategyRepository
from agent.marketing.domains.knowledge_bases import KnowledgeBaseRepository
from agent.marketing.intelligence.store import OperatingLoopRepository


class SystemLearningProjector:
    """Project one system-decided candidate into its native durable owner."""

    def __init__(
        self,
        paths: MarketingDataPaths | None = None,
        *,
        authority: SystemAuthority,
    ):
        require_system_authority(authority, EpistemicClass.DERIVED_KNOWLEDGE)
        self.authority = authority
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
            raise ValueError("account learning projection requires a system decision reason")
        candidate = self.loop.get_learning_candidate(candidate_id)
        candidate_type = str(candidate.get("candidate_type") or "")
        if candidate_type == "weight":
            raise ValueError(
                "weight candidates require replay approval before strategy projection"
            )
        if candidate_type == "skill":
            skill_name, skill_content = _validated_recovery_skill(candidate)
            from tools.skill_manager_tool import skill_matches, validate_skill_create

            if skill_matches(skill_name, skill_content):
                skill_projection = {
                    "success": True,
                    "already_projected": True,
                    "name": skill_name,
                }
            else:
                validation = validate_skill_create(skill_name, skill_content, "marketing")
                if not validation.get("success"):
                    raise ValueError(
                        str(validation.get("error") or "invalid Skill candidate")
                    )
                from tools.skill_manager_tool import _system_skill_manage

                skill_projection = json.loads(
                    _system_skill_manage(
                        authority=self.authority,
                        action="create",
                        name=skill_name,
                        content=skill_content,
                        category="marketing",
                        agent_created=True,
                    )
                )
                if not skill_projection.get("success"):
                    raise RuntimeError(
                        str(skill_projection.get("error") or "native Skill projection failed")
                    )
        proposal = candidate.get("proposal") or {}
        strategy_kind = str(proposal.get("kind") or "")
        knowledge_kind = str(proposal.get("kind") or "")
        if candidate_type == "memory" and knowledge_kind == "evidence_knowledge_candidate":
            raise ValueError(
                "platform and market knowledge are system-governed and cannot be changed by user review"
            )
        if candidate_type == "strategy" and strategy_kind not in {
            "account_influence_calibration",
            "public_benchmark_account_candidate",
            "public_benchmark_observation",
        }:
            raise ValueError("unsupported strategy learning projection")
        public_benchmark_projection = None
        if candidate_type == "strategy" and strategy_kind.startswith("public_benchmark_"):
            public_benchmark_projection = self.strategy.apply_public_benchmark_learning(
                user_id=candidate["user_id"],
                account_id=candidate["account_id"],
                candidate_id=candidate["id"],
                proposal=proposal,
                evidence_refs=candidate.get("evidence_refs") or [],
                confidence=float(candidate.get("confidence") or 0),
                authority=self.authority,
            )
        accepted = self.loop.decide_learning_candidate(
            candidate_id,
            status="accepted",
            reason=reason_value,
            authority=self.authority,
        )
        result = {"candidate": accepted}
        if candidate_type == "memory":
            result["account_knowledge"] = self.knowledge.promote_account_learning(
                user_id=accepted["user_id"],
                account_id=accepted["account_id"],
                candidate_id=accepted["id"],
                topic=topic,
                authority=self.authority,
            )
        if candidate_type == "strategy":
            if public_benchmark_projection is not None:
                result["account_strategy"] = public_benchmark_projection
            else:
                result["account_strategy"] = self.strategy.apply_learning_calibration(
                    user_id=accepted["user_id"],
                    account_id=accepted["account_id"],
                    candidate_id=accepted["id"],
                    authority=self.authority,
                )
        if candidate_type == "skill":
            result["skill_projection"] = skill_projection
        return result


def _validated_recovery_skill(candidate: dict) -> tuple[str, str]:
    proposal = candidate.get("proposal") or {}
    if proposal.get("kind") != "publish_unknown_recovery_workflow":
        raise ValueError("unsupported Skill learning projection")
    pairs = proposal.get("recovery_pairs")
    steps = proposal.get("steps")
    if not isinstance(pairs, list) or len(pairs) < 3:
        raise ValueError("Skill candidate requires at least three verified recovery pairs")
    if not isinstance(steps, list) or not 3 <= len(steps) <= 20:
        raise ValueError("Skill candidate requires a bounded reusable workflow")
    receipt_refs = set(str(item) for item in (candidate.get("receipt_refs") or []))
    action_ids: set[str] = set()
    for pair in pairs:
        if not isinstance(pair, dict):
            raise ValueError("Skill recovery evidence must be structured")
        action_id = str(pair.get("action_id") or "")
        unknown_id = str(pair.get("unknown_receipt_id") or "")
        published_id = str(pair.get("published_receipt_id") or "")
        if not action_id or unknown_id not in receipt_refs or published_id not in receipt_refs:
            raise ValueError("Skill recovery pair is not backed by candidate receipts")
        action_ids.add(action_id)
    if len(action_ids) < 3:
        raise ValueError("Skill recovery evidence must cover three distinct actions")
    name = str(proposal.get("skill_name") or "").strip()
    description = str(proposal.get("description") or "").strip()
    trigger = str(proposal.get("trigger") or "").strip()
    if not name or not description or not trigger:
        raise ValueError("Skill candidate is missing its validated identity or trigger")
    clean_steps: list[str] = []
    for raw in steps:
        step = " ".join(str(raw or "").split())
        if not step or len(step) > 500:
            raise ValueError("Skill workflow steps must be non-empty and bounded")
        clean_steps.append(step)
    content = "\n".join(
        [
            "---",
            f"name: {json.dumps(name, ensure_ascii=False)}",
            f"description: {json.dumps(description, ensure_ascii=False)}",
            "version: 1.0.0",
            "---",
            f"# {name}",
            "",
            "## Trigger",
            "",
            trigger,
            "",
            "## Workflow",
            "",
            *[f"{index}. {step}" for index, step in enumerate(clean_steps, start=1)],
            "",
            "## Safety contract",
            "",
            "- Never retry an unknown external side effect before querying platform truth.",
            "- Require a verified platform post id or stable work URL before settling success.",
            "- Keep the original idempotency key, action and metric checkpoints.",
            "- This procedure was promoted from at least three receipt-backed recoveries; it contains no account content or credentials.",
            "",
        ]
    )
    return name, content
