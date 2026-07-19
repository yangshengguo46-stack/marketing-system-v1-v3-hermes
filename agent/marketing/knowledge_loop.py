"""Continuous, system-governed maintenance for the Marketing OS knowledge bases.

The loop performs deterministic work only: freshness enforcement, crash-safe
projection recovery, and factual aggregation of repeated public observations.
It never asks a model to invent a claim. Evidence quorum, replay, replacement
and elimination are owned by the background system; users and conversations do
not have a decision seam.
"""

from __future__ import annotations

import hashlib
import json
import statistics
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from agent.marketing.data_paths import MarketingDataPaths
from agent.marketing.domains.knowledge_bases import KnowledgeBaseRepository
from agent.marketing.domains.storage import MarketingDomainRepository
from agent.marketing.intelligence.store import OperatingLoopRepository
from agent.marketing.intelligence.learning_governance import (
    decide_weight_candidate_with_replay,
    replay_weight_candidate,
)
from agent.marketing.learning import AccountLearningGovernance


KNOWLEDGE_MAINTENANCE_VERSION = "knowledge-maintenance-v0.2"
PUBLIC_MARKET_MIN_CASES = 3


class KnowledgeMaintenanceRunner(MarketingDomainRepository):
    """Run one idempotent product-owned knowledge maintenance tick."""

    def __init__(self, paths: MarketingDataPaths | None = None):
        super().__init__(paths)
        self.knowledge = KnowledgeBaseRepository(self.paths)
        self.loop = OperatingLoopRepository(self.paths)

    def run(self, *, as_of: str | None = None) -> dict[str, Any]:
        now = _time(as_of)
        audit = self.knowledge.audit_freshness_and_conflicts(as_of=now.isoformat())
        recovered = self._recover_accepted_evidence_candidates()
        public_entries = self._refresh_public_market_knowledge(now=now)
        learning = self._govern_pending_learning()
        return {
            "version": KNOWLEDGE_MAINTENANCE_VERSION,
            "as_of": now.isoformat(),
            "audit": audit,
            "recovered_projection_ids": recovered,
            "public_market_entry_ids": public_entries,
            "learning": learning,
            "governance": (
                "System-owned only: freshness, conflicts, evidence quorum and version replacement "
                "run silently; users and conversations have no knowledge-write authority."
            ),
        }

    def _govern_pending_learning(self) -> dict[str, list[str]]:
        """Apply receipt/evidence/replay gates without exposing a user decision seam."""

        projected: list[str] = []
        rejected: list[str] = []
        waiting: list[str] = []
        governance = AccountLearningGovernance(self.paths)

        for candidate in self.loop.list_learning_candidates(
            candidate_type="memory", status="pending", limit=500
        ):
            proposal = candidate.get("proposal") or {}
            kind = str(proposal.get("kind") or "")
            if kind == "evidence_knowledge_candidate":
                continue
            eligible = kind == "published_metric_retro"
            if kind == "public_content_natural_experiment":
                eligible = self._public_case_snapshot_count(
                    str(proposal.get("case_id") or "")
                ) >= 2
            if not eligible:
                waiting.append(candidate["id"])
                continue
            governance.accept_and_project(
                candidate["id"],
                reason=(
                    "system-owned learning gate: immutable receipts/evidence and required "
                    "repeated observations verified"
                ),
            )
            projected.append(candidate["id"])

        for candidate in self.loop.list_learning_candidates(
            candidate_type="weight", status="pending", limit=500
        ):
            replay = replay_weight_candidate(self.loop, candidate["id"])
            status = str(replay.get("status") or "")
            if status == "passed":
                result = decide_weight_candidate_with_replay(
                    self.loop,
                    candidate["id"],
                    decision="accepted",
                    reason="system-owned historical replay passed every support/conflict/harm gate",
                )
                projected.append(candidate["id"])
                strategy_id = str(result.get("strategy_candidate_id") or "")
                if strategy_id:
                    self._project_system_strategy(strategy_id, governance, projected, waiting)
            elif status in {
                "failed_support",
                "failed_conflict",
                "failed_historical_harm",
                "invalid_candidate",
            }:
                self.loop.decide_learning_candidate(
                    candidate["id"],
                    status="rejected",
                    reason=f"system-owned replay eliminated candidate: {status}",
                )
                rejected.append(candidate["id"])
            else:
                waiting.append(candidate["id"])

        for candidate in self.loop.list_learning_candidates(
            candidate_type="strategy", status="pending", limit=500
        ):
            self._project_system_strategy(candidate["id"], governance, projected, waiting)

        return {
            "projected_candidate_ids": list(dict.fromkeys(projected)),
            "rejected_candidate_ids": rejected,
            "waiting_for_evidence_ids": list(dict.fromkeys(waiting)),
        }

    def _project_system_strategy(
        self,
        candidate_id: str,
        governance: AccountLearningGovernance,
        projected: list[str],
        waiting: list[str],
    ) -> None:
        candidate = self.loop.get_learning_candidate(candidate_id)
        if candidate.get("status") != "pending":
            return
        proposal = candidate.get("proposal") or {}
        kind = str(proposal.get("kind") or "")
        if kind == "account_influence_calibration":
            active = governance.strategy.get_active_project(
                user_id=str(candidate.get("user_id") or "default"),
                account_id=str(candidate.get("account_id") or ""),
            )
            if active is None:
                waiting.append(candidate_id)
                return
        elif kind in {
            "public_benchmark_account_candidate",
            "public_benchmark_observation",
        }:
            if (
                float(candidate.get("confidence") or 0) < 0.6
                or self._public_case_snapshot_count(str(proposal.get("case_id") or "")) < 2
            ):
                waiting.append(candidate_id)
                return
        else:
            waiting.append(candidate_id)
            return
        governance.accept_and_project(
            candidate_id,
            reason="system-owned strategy projection passed evidence and replay gates",
        )
        projected.append(candidate_id)

    def _public_case_snapshot_count(self, case_id: str) -> int:
        if not case_id:
            return 0
        with self._connection() as db:
            row = db.execute(
                "SELECT COUNT(*) FROM marketing_public_feedback_observations WHERE case_id=?",
                (case_id,),
            ).fetchone()
        return int(row[0]) if row else 0

    def _recover_accepted_evidence_candidates(self) -> list[str]:
        recovered: list[str] = []
        for candidate in self.loop.list_learning_candidates(
            candidate_type="memory", status="accepted", limit=500
        ):
            if (candidate.get("proposal") or {}).get("kind") != "evidence_knowledge_candidate":
                continue
            self.knowledge.project_evidence_candidate(candidate["id"])
            recovered.append(candidate["id"])
        return recovered

    def _refresh_public_market_knowledge(self, *, now: datetime) -> list[str]:
        rows = self._public_observation_rows()
        cases: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            cases[row["case_id"]].append(row)
        cohorts: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
        for observations in cases.values():
            if len(observations) < 2:
                continue
            latest = max(observations, key=lambda item: (item["observed_at"], item["observation_id"]))
            content = latest["content"]
            content_type = str(content.get("content_type") or "unknown")
            cohorts[(latest["user_id"], latest["account_id"], latest["platform"], content_type)].append(
                latest
            )

        entry_ids: list[str] = []
        for (user_id, account_id, platform, content_type), samples in sorted(cohorts.items()):
            if len(samples) < PUBLIC_MARKET_MIN_CASES:
                continue
            metric_summary = _metric_summary([item["metrics"] for item in samples])
            if not metric_summary:
                continue
            evidence_refs = sorted({item["evidence_id"] for item in samples})
            window_start = min(item["observed_at"] for item in samples)
            window_end = max(item["observed_at"] for item in samples)
            projection_summary = _projection_summary(samples)
            digest = hashlib.sha256(
                json.dumps(
                    {
                        "case_ids": sorted(item["case_id"] for item in samples),
                        "evidence_refs": evidence_refs,
                        "metrics": metric_summary,
                        "anonymous_human_projections": projection_summary,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            ).hexdigest()[:16]
            claim_key = f"public_content_cohort:{platform}:{content_type}"
            supersedes = self._active_claim_entries(
                knowledge_base="market",
                platform=platform,
                topic="public_content_benchmark",
                claim_key=claim_key,
            )
            statement = {
                "claim_key": claim_key,
                "claim_value": {
                    "case_count": len(samples),
                    "latest_metric_medians": metric_summary,
                    "anonymous_human_projections": projection_summary,
                },
                "observation_type": "repeated_public_content_cohort",
                "platform": platform,
                "content_type": content_type,
                "case_count": len(samples),
                "window_start": window_start,
                "window_end": window_end,
                "latest_metric_medians": metric_summary,
                "anonymous_human_projections": projection_summary,
                "observer_contract": {
                    "role": "marketing_observation_candidate_not_human_truth",
                    "canonical_owner": "human_observer",
                    "projection_dimensions": [
                        "maslow_need_projection",
                        "jungian_eight_functions",
                        "existence_strategy",
                        "collective_mechanism",
                    ],
                    "user_mutable": False,
                    "conversation_mutable": False,
                    "core_writeback": "one_way_system_connector_only",
                },
                "causal_status": "descriptive_association_only",
                "data_limits": [
                    "publicly_visible metrics only",
                    "distribution and paid traffic are unknown confounders",
                    "medians describe this observed sample, not the whole platform",
                    "anonymous projection clusters do not reveal individual inner states",
                    "historical crowd theories are lenses, not universal psychological laws",
                ],
            }
            candidate = self.knowledge.propose_evidence_knowledge(
                knowledge_base="market",
                user_id=user_id,
                account_id=account_id,
                platform=platform,
                region="",
                content_kind=content_type,
                topic="public_content_benchmark",
                statement=statement,
                evidence_refs=evidence_refs,
                confidence=min(0.82, 0.5 + len(samples) * 0.04),
                version=f"{window_end}:{digest}",
                valid_from=window_end,
                valid_to=(now + timedelta(days=45)).isoformat(),
                supersedes_entry_ids=supersedes,
                source_key=f"public-market:{user_id}:{account_id}:{platform}:{content_type}:{digest}",
            )
            if candidate["status"] == "pending":
                candidate = self.loop.decide_learning_candidate(
                    candidate["id"],
                    status="accepted",
                    reason=(
                        "system-owned deterministic public cohort passed minimum repeated-case "
                        f"quorum ({len(samples)} cases, two or more snapshots each)"
                    ),
                )
            if candidate["status"] == "accepted":
                entry = self.knowledge.project_evidence_candidate(candidate["id"])
                entry_ids.append(entry["id"])
        return entry_ids

    def _public_observation_rows(self) -> list[dict[str, Any]]:
        with self._connection() as db:
            rows = db.execute(
                """SELECT c.id AS case_id,c.user_id,c.account_id,c.platform,
                          o.id AS observation_id,o.evidence_id,o.observed_at,
                          o.content_json,o.metrics_json
                          ,(SELECT r.summary_json FROM marketing_receipt_refs r
                            WHERE r.source_id=o.id
                              AND r.receipt_type='public_content_natural_experiment'
                            ORDER BY r.created_at DESC,r.id DESC LIMIT 1) AS interpretation_json
                FROM marketing_public_content_cases c
                JOIN marketing_public_feedback_observations o ON o.case_id=c.id
                ORDER BY c.id,o.observed_at,o.id"""
            ).fetchall()
        return [
            {
                **dict(row),
                "content": json.loads(row["content_json"] or "{}"),
                "metrics": json.loads(row["metrics_json"] or "{}"),
                "model_observation": (
                    json.loads(row["interpretation_json"] or "{}").get("model_observation")
                    if row["interpretation_json"]
                    else None
                ),
            }
            for row in rows
        ]

    def _active_claim_entries(
        self, *, knowledge_base: str, platform: str, topic: str, claim_key: str
    ) -> list[str]:
        with self._connection() as db:
            rows = db.execute(
                """SELECT id,statement_json FROM marketing_knowledge_entries
                WHERE knowledge_base=? AND IFNULL(platform,'')=? AND topic=?
                  AND status IN ('active','conflicted')""",
                (knowledge_base, platform, topic),
            ).fetchall()
        return [
            row["id"]
            for row in rows
            if str((json.loads(row["statement_json"] or "{}")).get("claim_key") or "")
            == claim_key
        ]


def _metric_summary(samples: list[dict[str, Any]]) -> dict[str, int | float]:
    values: dict[str, list[float]] = defaultdict(list)
    for sample in samples:
        for key, raw in sample.items():
            if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                continue
            values[str(key)].append(float(raw))
    result: dict[str, int | float] = {}
    for key, items in sorted(values.items()):
        if len(items) < PUBLIC_MARKET_MIN_CASES:
            continue
        median = statistics.median(items)
        result[key] = int(median) if float(median).is_integer() else round(float(median), 4)
    return result


def _projection_summary(samples: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate only anonymous cluster projections after repeated-case quorum."""

    interpreted = [
        item for item in samples if isinstance(item.get("model_observation"), dict)
    ]
    if len(interpreted) < PUBLIC_MARKET_MIN_CASES:
        return {
            "status": "insufficient_repeated_anonymous_cases",
            "interpreted_case_count": len(interpreted),
            "minimum_case_count": PUBLIC_MARKET_MIN_CASES,
            "dimensions": {},
        }
    field_map = {
        "maslow_need_projection": "need_projection",
        "jungian_eight_functions": "cognitive_projection",
        "existence_strategy": "existence_strategy",
        "collective_mechanism": "collective_mechanism",
    }
    dimensions: dict[str, Any] = {}
    for label, field in field_map.items():
        cluster_counts: dict[str, int] = defaultdict(int)
        reaction_counts: dict[str, int] = defaultdict(int)
        for sample in interpreted:
            reaction = (sample.get("model_observation") or {}).get("reaction") or {}
            for cluster in reaction.get("clusters") or []:
                if not isinstance(cluster, dict):
                    continue
                projection = str(cluster.get(field) or "unknown")
                cluster_counts[projection] += 1
                reaction_counts[projection] += int(cluster.get("count") or 0)
        dimensions[label] = {
            "anonymous_cluster_counts": dict(sorted(cluster_counts.items())),
            "observed_reaction_counts": dict(sorted(reaction_counts.items())),
        }
    return {
        "status": "repeated_anonymous_projection_clusters",
        "interpreted_case_count": len(interpreted),
        "dimensions": dimensions,
        "generalization_limit": (
            "Calibrates cohort-level projection bundles only; it does not observe existence, "
            "diagnose a person, or establish a universal human law."
        ),
    }


def _time(value: str | None) -> datetime:
    if value:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    return datetime.now(timezone.utc)


def run_knowledge_maintenance(
    *, paths: MarketingDataPaths | None = None, as_of: str | None = None
) -> dict[str, Any]:
    return KnowledgeMaintenanceRunner(paths).run(as_of=as_of)
