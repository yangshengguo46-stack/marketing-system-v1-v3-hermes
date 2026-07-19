"""The creator operating model for one long-running social account.

This is not a questionnaire store and not an Electron workflow.  It owns the
versioned strategic artifacts Hermes needs to act like a creator agency:
creator assets, market-route hypotheses, benchmark relationships, positioning,
content systems, and falsifiable content experiments.

Observed facts must cite EvidenceRecord IDs.  User/model interpretations remain
hypotheses until explicitly selected or approved; no method writes platform,
market, content, or account knowledge directly.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

from agent.marketing.data_paths import MarketingDataPaths
from agent.marketing.domains.evidence import EvidenceRepository
from agent.marketing.domains.storage import MarketingDomainRepository
from agent.marketing.domains.human_model import (
    build_human_projection_model,
)
from agent.marketing.intelligence.influence_score import (
    INFLUENCE_SCORE_VERSION,
    apply_influence_weight_adjustment,
)


PROFILE_STATUSES = {"draft", "confirmed", "superseded"}
MARKET_ROUTE_STATUSES = {"draft", "selected", "rejected", "superseded"}
BENCHMARK_ROLES = {
    "direct",
    "topic",
    "format",
    "trust",
    "business",
    "cross_lane",
    "negative",
}
BENCHMARK_DIMENSIONS = {
    "audience",
    "positioning",
    "content_pillar",
    "format",
    "hook",
    "tone",
    "cadence",
    "engagement",
    "retention",
    "conversion",
    "business_model",
    "trust",
    "bgm",
    "gap",
}
MATCH_DIMENSIONS = {
    "audience_overlap",
    "business_model_similarity",
    "lifecycle_similarity",
    "format_fit",
    "creator_resource_fit",
    "platform_fit",
    "performance_relevance",
}
POSITIONING_REQUIRED = {
    "promise",
    "differentiation",
    "persona",
    "audience_summary",
    "proof_mechanism",
    "content_pillars",
    "tone",
    "taboos",
    "recurring_formats",
    "commercial_path",
    "monetization_boundary",
}
CONTENT_SYSTEM_REQUIRED = {
    "acquisition_lanes",
    "trust_lanes",
    "action_lanes",
    "recurring_series",
    "platform_expression",
    "production_workflow",
    "publishing_cadence",
    "measurement_plan",
    "exploration_policy",
    "commercial_boundaries",
}


class AccountStrategyRepository(MarketingDomainRepository):
    """Own versioned strategy artifacts in the Hermes ``state.db``."""

    def get_active_project(self, *, user_id: str, account_id: str) -> dict[str, Any] | None:
        with self._connection() as db:
            row = db.execute(
                """SELECT * FROM account_strategy_projects
                WHERE user_id=? AND account_id=? AND status='active'""",
                (user_id, account_id),
            ).fetchone()
        return _project(row) if row is not None else None

    def get_project(
        self, *, user_id: str, account_id: str, project_id: str
    ) -> dict[str, Any]:
        with self._connection() as db:
            row = _require_project(
                db, user_id=user_id, account_id=account_id, project_id=project_id
            )
        return _project(row)

    # ------------------------------------------------------------------
    # Creator asset map: confirmed user operating input, never knowledge.
    # ------------------------------------------------------------------

    def draft_creator_profile(
        self,
        *,
        user_id: str,
        account_id: str,
        project_id: str,
        profile: dict[str, Any],
        source_refs: list[str] | None = None,
    ) -> dict[str, Any]:
        payload = _creator_profile(profile)
        refs = _string_list(source_refs or [], field="source_refs", limit=30)
        with self._transaction() as db:
            _require_project(db, user_id=user_id, account_id=account_id, project_id=project_id)
            version = _next_version(db, "creator_operating_profiles", project_id)
            profile_id = _id("creator")
            db.execute(
                """INSERT INTO creator_operating_profiles
                (id,project_id,user_id,account_id,version,profile_json,source_refs_json,
                 status,created_at)
                VALUES (?,?,?,?,?,?,?,'draft',?)""",
                (
                    profile_id,
                    project_id,
                    user_id,
                    account_id,
                    version,
                    _json(payload, field="profile", limit=48_000),
                    _json(refs, field="source_refs", limit=8_000),
                    _now(),
                ),
            )
        return self.get_creator_profile(
            user_id=user_id, account_id=account_id, project_id=project_id, profile_id=profile_id
        )

    def confirm_creator_profile(
        self,
        *,
        user_id: str,
        account_id: str,
        project_id: str,
        profile_id: str,
        confirmed_by_user: bool,
    ) -> dict[str, Any]:
        if confirmed_by_user is not True:
            raise ValueError("explicit user confirmation is required")
        now = _now()
        with self._transaction() as db:
            _require_project(db, user_id=user_id, account_id=account_id, project_id=project_id)
            row = db.execute(
                """SELECT status FROM creator_operating_profiles
                WHERE id=? AND project_id=? AND user_id=? AND account_id=?""",
                (profile_id, project_id, user_id, account_id),
            ).fetchone()
            if row is None:
                raise KeyError("creator profile not found in account scope")
            if row["status"] == "confirmed":
                return self.get_creator_profile(
                    user_id=user_id, account_id=account_id, project_id=project_id,
                    profile_id=profile_id,
                )
            if row["status"] != "draft":
                raise ValueError("only a draft creator profile can be confirmed")
            db.execute(
                """UPDATE creator_operating_profiles SET status='superseded'
                WHERE project_id=? AND status='confirmed'""",
                (project_id,),
            )
            db.execute(
                """UPDATE creator_operating_profiles
                SET status='confirmed',confirmed_at=? WHERE id=?""",
                (now, profile_id),
            )
            _advance_stage(db, project_id, "creator_model_ready", now)
        return self.get_creator_profile(
            user_id=user_id, account_id=account_id, project_id=project_id, profile_id=profile_id
        )

    def get_creator_profile(
        self,
        *,
        user_id: str,
        account_id: str,
        project_id: str,
        profile_id: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        query = """SELECT * FROM creator_operating_profiles
        WHERE project_id=? AND user_id=? AND account_id=?"""
        params: list[Any] = [project_id, user_id, account_id]
        if profile_id:
            query += " AND id=?"
            params.append(profile_id)
        if status:
            if status not in PROFILE_STATUSES:
                raise ValueError("invalid creator profile status")
            query += " AND status=?"
            params.append(status)
        query += " ORDER BY version DESC LIMIT 1"
        with self._connection() as db:
            row = db.execute(query, params).fetchone()
        if row is None:
            raise KeyError("creator profile not found in account scope")
        return _creator_record(row)

    # ---------------------------------------------------------------
    # Market routes: account-scoped hypotheses, not Market KB truth.
    # ---------------------------------------------------------------

    def draft_market_route(
        self,
        *,
        user_id: str,
        account_id: str,
        project_id: str,
        route: dict[str, Any],
        evidence_refs: list[str] | None = None,
        confidence: float = 0.3,
    ) -> dict[str, Any]:
        payload = _market_route(route)
        refs = self._verified_evidence(
            user_id=user_id, account_id=account_id, evidence_refs=evidence_refs or []
        )
        confidence_value = _confidence(confidence)
        if not refs:
            confidence_value = min(confidence_value, 0.45)
        with self._transaction() as db:
            _require_project(db, user_id=user_id, account_id=account_id, project_id=project_id)
            _require_confirmed_profile(db, project_id, user_id, account_id)
            version = _next_version(db, "market_route_hypotheses", project_id)
            route_id = _id("route")
            db.execute(
                """INSERT INTO market_route_hypotheses
                (id,project_id,user_id,account_id,version,route_json,evidence_refs_json,
                 confidence,status,created_at)
                VALUES (?,?,?,?,?,?,?,?, 'draft',?)""",
                (
                    route_id,
                    project_id,
                    user_id,
                    account_id,
                    version,
                    _json(payload, field="route", limit=40_000),
                    _json(refs, field="evidence_refs", limit=12_000),
                    confidence_value,
                    _now(),
                ),
            )
            _advance_stage(db, project_id, "market_routes_ready", _now())
        return self.get_market_route(
            user_id=user_id, account_id=account_id, project_id=project_id, route_id=route_id
        )

    def select_market_route(
        self,
        *,
        user_id: str,
        account_id: str,
        project_id: str,
        route_id: str,
        confirmed_by_user: bool,
    ) -> dict[str, Any]:
        if confirmed_by_user is not True:
            raise ValueError("explicit user confirmation is required")
        now = _now()
        with self._transaction() as db:
            _require_project(db, user_id=user_id, account_id=account_id, project_id=project_id)
            row = db.execute(
                """SELECT status FROM market_route_hypotheses
                WHERE id=? AND project_id=? AND user_id=? AND account_id=?""",
                (route_id, project_id, user_id, account_id),
            ).fetchone()
            if row is None:
                raise KeyError("market route not found in account scope")
            if row["status"] == "selected":
                return self.get_market_route(
                    user_id=user_id, account_id=account_id, project_id=project_id, route_id=route_id
                )
            if row["status"] != "draft":
                raise ValueError("only a draft market route can be selected")
            db.execute(
                """UPDATE market_route_hypotheses SET status='superseded'
                WHERE project_id=? AND status='selected'""",
                (project_id,),
            )
            db.execute(
                """UPDATE market_route_hypotheses
                SET status='selected',selected_at=? WHERE id=?""",
                (now, route_id),
            )
            _advance_stage(db, project_id, "market_route_selected", now)
        return self.get_market_route(
            user_id=user_id, account_id=account_id, project_id=project_id, route_id=route_id
        )

    def get_market_route(
        self,
        *,
        user_id: str,
        account_id: str,
        project_id: str,
        route_id: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        query = """SELECT * FROM market_route_hypotheses
        WHERE project_id=? AND user_id=? AND account_id=?"""
        params: list[Any] = [project_id, user_id, account_id]
        if route_id:
            query += " AND id=?"
            params.append(route_id)
        if status:
            if status not in MARKET_ROUTE_STATUSES:
                raise ValueError("invalid market route status")
            query += " AND status=?"
            params.append(status)
        query += " ORDER BY version DESC LIMIT 1"
        with self._connection() as db:
            row = db.execute(query, params).fetchone()
        if row is None:
            raise KeyError("market route not found in account scope")
        return _market_record(row)

    def list_market_routes(
        self, *, user_id: str, account_id: str, project_id: str
    ) -> list[dict[str, Any]]:
        with self._connection() as db:
            rows = db.execute(
                """SELECT * FROM market_route_hypotheses
                WHERE project_id=? AND user_id=? AND account_id=? ORDER BY version""",
                (project_id, user_id, account_id),
            ).fetchall()
        return [_market_record(row) for row in rows]

    # -------------------------------------------------------------
    # Benchmark graph: evidence-backed relationships, not a KB.
    # -------------------------------------------------------------

    def add_benchmark_account(
        self,
        *,
        user_id: str,
        account_id: str,
        project_id: str,
        platform: str,
        account_handle: str,
        role: str,
        selection_reason: str,
        match_dimensions: dict[str, Any],
        evidence_refs: list[str],
        account_name: str = "",
        platform_account_id: str = "",
        profile_url: str = "",
        selection_status: str = "candidate",
        metadata: dict[str, Any] | None = None,
        observed_at: str | None = None,
        valid_until: str | None = None,
    ) -> dict[str, Any]:
        if role not in BENCHMARK_ROLES:
            raise ValueError("unsupported benchmark role")
        if selection_status != "candidate":
            raise ValueError(
                "new benchmarks must start as candidates; use an explicit decision to select them"
            )
        platform_value = _text(platform, field="platform", limit=80)
        handle = _text(account_handle, field="account_handle", limit=200)
        reason = _text(selection_reason, field="selection_reason", limit=1_000)
        url = _https_url(profile_url) if profile_url else ""
        dimensions = _match_dimensions(match_dimensions)
        refs = self._verified_evidence(
            user_id=user_id, account_id=account_id, evidence_refs=evidence_refs,
            require_any=True,
        )
        now = _now()
        benchmark_id = _id("benchmark")
        with self._transaction() as db:
            _require_project(db, user_id=user_id, account_id=account_id, project_id=project_id)
            _require_confirmed_audience(db, project_id, user_id, account_id)
            db.execute(
                """INSERT INTO benchmark_accounts
                (id,project_id,user_id,target_account_id,platform,platform_account_id,
                 account_handle,account_name,profile_url,role,selection_reason,
                 match_dimensions_json,evidence_refs_json,selection_status,metadata_json,
                 observed_at,valid_until,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    benchmark_id,
                    project_id,
                    user_id,
                    account_id,
                    platform_value,
                    str(platform_account_id or "")[:200],
                    handle,
                    str(account_name or "")[:300] or None,
                    url,
                    role,
                    reason,
                    _json(dimensions, field="match_dimensions", limit=8_000),
                    _json(refs, field="evidence_refs", limit=12_000),
                    selection_status,
                    _json(metadata or {}, field="metadata", limit=16_000),
                    observed_at or now,
                    valid_until,
                    now,
                    now,
                ),
            )
        return self.get_benchmark_account(
            user_id=user_id, account_id=account_id, project_id=project_id,
            benchmark_id=benchmark_id,
        )

    def decide_benchmark_account(
        self,
        *,
        user_id: str,
        account_id: str,
        project_id: str,
        benchmark_id: str,
        decision: str,
        confirmed_by_user: bool,
    ) -> dict[str, Any]:
        if decision not in {"selected", "rejected"}:
            raise ValueError("benchmark decision must be selected or rejected")
        if confirmed_by_user is not True:
            raise ValueError("explicit user confirmation is required")
        with self._transaction() as db:
            row = _require_benchmark(
                db, user_id=user_id, account_id=account_id, project_id=project_id,
                benchmark_id=benchmark_id,
            )
            if row["selection_status"] != decision:
                db.execute(
                    """UPDATE benchmark_accounts SET selection_status=?,updated_at=?
                    WHERE id=?""",
                    (decision, _now(), benchmark_id),
                )
        self._mark_benchmark_ready_if_complete(
            user_id=user_id, account_id=account_id, project_id=project_id
        )
        return self.get_benchmark_account(
            user_id=user_id, account_id=account_id, project_id=project_id,
            benchmark_id=benchmark_id,
        )

    def add_benchmark_observation(
        self,
        *,
        user_id: str,
        account_id: str,
        project_id: str,
        benchmark_id: str,
        dimension: str,
        value: dict[str, Any],
        evidence_refs: list[str],
        confidence: float,
        observed_at: str | None = None,
        source_candidate_id: str = "",
    ) -> dict[str, Any]:
        if dimension not in BENCHMARK_DIMENSIONS:
            raise ValueError("unsupported benchmark observation dimension")
        refs = self._verified_evidence(
            user_id=user_id, account_id=account_id, evidence_refs=evidence_refs,
            require_any=True,
        )
        now = _now()
        observation_id = _id("benchobs")
        with self._transaction() as db:
            benchmark = _require_benchmark(
                db, user_id=user_id, account_id=account_id, project_id=project_id,
                benchmark_id=benchmark_id,
            )
            if benchmark["selection_status"] == "rejected":
                raise ValueError("rejected benchmark cannot receive observations")
            db.execute(
                """INSERT INTO benchmark_observations
                (id,benchmark_account_id,project_id,user_id,target_account_id,dimension,
                 value_json,evidence_refs_json,provenance_json,confidence,observed_at,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    observation_id,
                    benchmark_id,
                    project_id,
                    user_id,
                    account_id,
                    dimension,
                    _json(value, field="observation", limit=20_000),
                    _json(refs, field="evidence_refs", limit=12_000),
                    _json(
                        {
                            "source_kind": "verified_evidence",
                            "evidence_refs": refs,
                            **(
                                {"source_learning_candidate_id": source_candidate_id}
                                if source_candidate_id
                                else {}
                            ),
                        },
                        field="provenance", limit=12_000,
                    ),
                    _confidence(confidence),
                    observed_at or now,
                    now,
                ),
            )
        self._mark_benchmark_ready_if_complete(
            user_id=user_id, account_id=account_id, project_id=project_id
        )
        return self.get_benchmark_observation(
            user_id=user_id, account_id=account_id, project_id=project_id,
            observation_id=observation_id,
        )

    def apply_public_benchmark_learning(
        self,
        *,
        user_id: str,
        account_id: str,
        candidate_id: str,
        proposal: dict[str, Any],
        evidence_refs: list[str],
        confidence: float,
    ) -> dict[str, Any]:
        """Idempotently project one explicitly accepted public observation."""

        kind = str(proposal.get("kind") or "")
        if kind not in {
            "public_benchmark_account_candidate",
            "public_benchmark_observation",
        }:
            raise ValueError("unsupported public benchmark learning kind")
        project_id = str(proposal.get("project_id") or "").strip()
        projection = proposal.get("benchmark_projection") or {}
        public_source = proposal.get("public_source") or {}
        creator = public_source.get("creator") or {}
        observations = projection.get("observation_dimensions") or {}
        if not project_id or not isinstance(observations, dict) or not observations:
            raise ValueError("public benchmark learning is incomplete")
        source_marker = f'%"source_learning_candidate_id":"{candidate_id}"%'
        benchmark_id = str(proposal.get("benchmark_id") or "").strip()
        if kind == "public_benchmark_account_candidate":
            with self._connection() as db:
                existing = db.execute(
                    """SELECT id FROM benchmark_accounts
                    WHERE project_id=? AND user_id=? AND target_account_id=?
                    AND metadata_json LIKE ? ORDER BY created_at LIMIT 1""",
                    (project_id, user_id, account_id, source_marker),
                ).fetchone()
            if existing is not None:
                benchmark_id = existing["id"]
            else:
                handle = str(
                    creator.get("handle")
                    or creator.get("platform_account_id")
                    or creator.get("name")
                    or ""
                ).strip()
                benchmark = self.add_benchmark_account(
                    user_id=user_id,
                    account_id=account_id,
                    project_id=project_id,
                    platform=str(public_source.get("platform") or ""),
                    account_handle=handle,
                    account_name=str(creator.get("name") or ""),
                    platform_account_id=str(creator.get("platform_account_id") or ""),
                    profile_url=str(creator.get("profile_url") or ""),
                    role=str(projection.get("suggested_role") or ""),
                    selection_reason=str(projection.get("selection_reason") or ""),
                    match_dimensions=projection.get("match_dimensions") or {},
                    evidence_refs=evidence_refs,
                    metadata={
                        "source_learning_candidate_id": candidate_id,
                        "source_kind": "public_content_natural_experiment",
                    },
                )
                benchmark_id = benchmark["id"]
        else:
            self.get_benchmark_account(
                user_id=user_id,
                account_id=account_id,
                project_id=project_id,
                benchmark_id=benchmark_id,
            )

        created = []
        for dimension, value in observations.items():
            with self._connection() as db:
                existing = db.execute(
                    """SELECT id FROM benchmark_observations
                    WHERE benchmark_account_id=? AND dimension=? AND provenance_json LIKE ?
                    ORDER BY created_at LIMIT 1""",
                    (benchmark_id, dimension, source_marker),
                ).fetchone()
            if existing is not None:
                created.append(
                    self.get_benchmark_observation(
                        user_id=user_id,
                        account_id=account_id,
                        project_id=project_id,
                        observation_id=existing["id"],
                    )
                )
                continue
            created.append(
                self.add_benchmark_observation(
                    user_id=user_id,
                    account_id=account_id,
                    project_id=project_id,
                    benchmark_id=benchmark_id,
                    dimension=dimension,
                    value=value if isinstance(value, dict) else {"value": value},
                    evidence_refs=evidence_refs,
                    confidence=min(float(confidence), 0.7),
                    source_candidate_id=candidate_id,
                )
            )
        return {
            "benchmark": self.get_benchmark_account(
                user_id=user_id,
                account_id=account_id,
                project_id=project_id,
                benchmark_id=benchmark_id,
            ),
            "observations": created,
            "selection_guardrail": (
                "A new public benchmark remains a candidate until separately selected by the user."
            ),
        }

    def get_benchmark_account(
        self, *, user_id: str, account_id: str, project_id: str, benchmark_id: str
    ) -> dict[str, Any]:
        with self._connection() as db:
            row = _require_benchmark(
                db, user_id=user_id, account_id=account_id, project_id=project_id,
                benchmark_id=benchmark_id,
            )
        return _benchmark_record(row)

    def get_benchmark_observation(
        self, *, user_id: str, account_id: str, project_id: str, observation_id: str
    ) -> dict[str, Any]:
        with self._connection() as db:
            row = db.execute(
                """SELECT * FROM benchmark_observations
                WHERE id=? AND project_id=? AND user_id=? AND target_account_id=?""",
                (observation_id, project_id, user_id, account_id),
            ).fetchone()
        if row is None:
            raise KeyError("benchmark observation not found in account scope")
        return _benchmark_observation_record(row)

    def benchmark_readiness(
        self, *, user_id: str, account_id: str, project_id: str
    ) -> dict[str, Any]:
        as_of = _now()
        with self._connection() as db:
            _require_project(
                db, user_id=user_id, account_id=account_id, project_id=project_id
            )
            selected = db.execute(
                """SELECT id,role FROM benchmark_accounts
                WHERE project_id=? AND user_id=? AND target_account_id=?
                AND selection_status='selected'
                AND (valid_until IS NULL OR valid_until='' OR valid_until>?)""",
                (project_id, user_id, account_id, as_of),
            ).fetchall()
            observations = db.execute(
                """SELECT benchmark_account_id,dimension,COUNT(*) AS count
                FROM benchmark_observations WHERE project_id=? AND user_id=?
                AND target_account_id=? GROUP BY benchmark_account_id,dimension""",
                (project_id, user_id, account_id),
            ).fetchall()
        selected_ids = {row["id"] for row in selected}
        roles = {row["role"] for row in selected}
        counts = {identifier: 0 for identifier in selected_ids}
        covered: set[str] = set()
        for row in observations:
            if row["benchmark_account_id"] in selected_ids:
                counts[row["benchmark_account_id"]] += int(row["count"])
                covered.add(str(row["dimension"]))
        required = {"audience", "positioning", "content_pillar", "format", "engagement", "business_model"}
        missing: list[str] = []
        if len(selected) < 3:
            missing.append("selected_accounts")
        if len(roles - {"negative"}) < 2:
            missing.append("role_diversity")
        if "negative" not in roles:
            missing.append("negative_benchmark")
        shallow = sorted(identifier for identifier, count in counts.items() if count < 2)
        if shallow:
            missing.append("observation_depth")
        missing_dimensions = sorted(required - covered)
        if missing_dimensions:
            missing.append("dimension_coverage")
        return {
            "ready": not missing,
            "selected_count": len(selected),
            "roles": sorted(roles),
            "observation_counts": counts,
            "shallow_benchmark_ids": shallow,
            "covered_dimensions": sorted(covered),
            "missing_dimensions": missing_dimensions,
            "missing": missing,
            "rule": "multi-role evidence graph; follower count alone never unlocks positioning",
        }

    def _mark_benchmark_ready_if_complete(
        self, *, user_id: str, account_id: str, project_id: str
    ) -> None:
        readiness = self.benchmark_readiness(
            user_id=user_id, account_id=account_id, project_id=project_id
        )
        if not readiness["ready"]:
            return
        with self._transaction() as db:
            _require_project(
                db, user_id=user_id, account_id=account_id, project_id=project_id
            )
            _advance_stage(db, project_id, "benchmark_graph_ready", _now())

    # -------------------------------------------------------------
    # Positioning and content system: versioned, user-approved truth.
    # -------------------------------------------------------------

    def draft_positioning(
        self,
        *,
        user_id: str,
        account_id: str,
        project_id: str,
        positioning: dict[str, Any],
    ) -> dict[str, Any]:
        payload = _positioning(positioning)
        readiness = self.benchmark_readiness(
            user_id=user_id, account_id=account_id, project_id=project_id
        )
        with self._transaction() as db:
            _require_project(db, user_id=user_id, account_id=account_id, project_id=project_id)
            profile = _require_confirmed_profile(db, project_id, user_id, account_id)
            route = _require_selected_route(db, project_id, user_id, account_id)
            audience = _require_confirmed_audience(db, project_id, user_id, account_id)
            benchmark_ids = [
                row["id"] for row in db.execute(
                    """SELECT id FROM benchmark_accounts WHERE project_id=? AND user_id=?
                    AND target_account_id=? AND selection_status='selected'
                    AND (valid_until IS NULL OR valid_until='' OR valid_until>?)""",
                    (project_id, user_id, account_id, _now()),
                ).fetchall()
            ]
            observation_ids = [
                row["id"] for row in db.execute(
                    """SELECT observation.id FROM benchmark_observations AS observation
                    JOIN benchmark_accounts AS benchmark
                      ON benchmark.id=observation.benchmark_account_id
                    WHERE observation.project_id=? AND observation.user_id=?
                    AND observation.target_account_id=? AND benchmark.selection_status='selected'
                    AND (benchmark.valid_until IS NULL OR benchmark.valid_until=''
                         OR benchmark.valid_until>?)""",
                    (project_id, user_id, account_id, _now()),
                ).fetchall()
            ]
            basis = [
                f"creator_profile:{profile['id']}",
                f"market_route:{route['id']}",
                f"audience_hypothesis:{audience['id']}",
                *[f"benchmark:{item}" for item in benchmark_ids],
                *[f"benchmark_observation:{item}" for item in observation_ids],
            ]
            gaps = list(readiness["missing"])
            version = _next_version(db, "positioning_versions", project_id)
            positioning_id = _id("positioning")
            db.execute(
                """INSERT INTO positioning_versions
                (id,project_id,user_id,account_id,version,positioning_json,basis_refs_json,
                 data_gaps_json,status,created_at)
                VALUES (?,?,?,?,?,?,?,?, 'draft',?)""",
                (
                    positioning_id, project_id, user_id, account_id, version,
                    _json(payload, field="positioning", limit=40_000),
                    _json(basis, field="basis_refs", limit=24_000),
                    _json(gaps, field="data_gaps", limit=8_000),
                    _now(),
                ),
            )
        return self.get_positioning(
            user_id=user_id, account_id=account_id, project_id=project_id,
            positioning_id=positioning_id,
        )

    def approve_positioning(
        self,
        *,
        user_id: str,
        account_id: str,
        project_id: str,
        positioning_id: str,
        confirmed_by_user: bool,
        accept_data_gaps: bool = False,
    ) -> dict[str, Any]:
        if confirmed_by_user is not True:
            raise ValueError("explicit user confirmation is required")
        current = self.get_positioning(
            user_id=user_id, account_id=account_id, project_id=project_id,
            positioning_id=positioning_id,
        )
        if current["status"] == "approved":
            return current
        if current["status"] != "draft":
            raise ValueError("only a draft positioning can be approved")
        if current["data_gaps"] and accept_data_gaps is not True:
            raise ValueError("positioning has evidence gaps; explicit gap acceptance is required")
        now = _now()
        with self._transaction() as db:
            db.execute(
                """UPDATE positioning_versions SET status='superseded'
                WHERE project_id=? AND status='approved'""",
                (project_id,),
            )
            updated = db.execute(
                """UPDATE positioning_versions SET status='approved',approved_at=?
                WHERE id=? AND project_id=? AND user_id=? AND account_id=? AND status='draft'""",
                (now, positioning_id, project_id, user_id, account_id),
            ).rowcount
            if updated != 1:
                raise ValueError("positioning approval conflicted with another update")
            _advance_stage(db, project_id, "positioning_approved", now)
        return self.get_positioning(
            user_id=user_id, account_id=account_id, project_id=project_id,
            positioning_id=positioning_id,
        )

    def get_positioning(
        self,
        *,
        user_id: str,
        account_id: str,
        project_id: str,
        positioning_id: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        query = """SELECT * FROM positioning_versions
        WHERE project_id=? AND user_id=? AND account_id=?"""
        params: list[Any] = [project_id, user_id, account_id]
        if positioning_id:
            query += " AND id=?"
            params.append(positioning_id)
        if status:
            query += " AND status=?"
            params.append(status)
        query += " ORDER BY version DESC LIMIT 1"
        with self._connection() as db:
            row = db.execute(query, params).fetchone()
        if row is None:
            raise KeyError("positioning not found in account scope")
        return _positioning_record(row)

    def draft_content_system(
        self,
        *,
        user_id: str,
        account_id: str,
        project_id: str,
        system: dict[str, Any],
    ) -> dict[str, Any]:
        payload = _content_system(system)
        with self._transaction() as db:
            positioning = db.execute(
                """SELECT id FROM positioning_versions WHERE project_id=? AND user_id=?
                AND account_id=? AND status='approved'""",
                (project_id, user_id, account_id),
            ).fetchone()
            if positioning is None:
                raise ValueError("approved positioning is required")
            version = _next_version(db, "content_system_versions", project_id)
            system_id = _id("content_system")
            basis = [f"positioning:{positioning['id']}"]
            db.execute(
                """INSERT INTO content_system_versions
                (id,project_id,user_id,account_id,positioning_id,version,system_json,
                 basis_refs_json,status,created_at)
                VALUES (?,?,?,?,?,?,?,?,'draft',?)""",
                (
                    system_id, project_id, user_id, account_id, positioning["id"], version,
                    _json(payload, field="content_system", limit=64_000),
                    _json(basis, field="basis_refs", limit=8_000), _now(),
                ),
            )
        return self.get_content_system(
            user_id=user_id, account_id=account_id, project_id=project_id, system_id=system_id
        )

    def approve_content_system(
        self,
        *,
        user_id: str,
        account_id: str,
        project_id: str,
        system_id: str,
        confirmed_by_user: bool,
    ) -> dict[str, Any]:
        if confirmed_by_user is not True:
            raise ValueError("explicit user confirmation is required")
        now = _now()
        with self._transaction() as db:
            current = db.execute(
                """SELECT status FROM content_system_versions
                WHERE id=? AND project_id=? AND user_id=? AND account_id=?""",
                (system_id, project_id, user_id, account_id),
            ).fetchone()
            if current is None:
                raise KeyError("content system not found in account scope")
            if current["status"] == "approved":
                return self.get_content_system(
                    user_id=user_id, account_id=account_id, project_id=project_id,
                    system_id=system_id,
                )
            if current["status"] != "draft":
                raise ValueError("only a draft content system can be approved")
            db.execute(
                """UPDATE content_system_versions SET status='superseded'
                WHERE project_id=? AND status='approved'""",
                (project_id,),
            )
            db.execute(
                """UPDATE content_system_versions SET status='approved',approved_at=?
                WHERE id=?""",
                (now, system_id),
            )
            _advance_stage(db, project_id, "content_system_approved", now)
        return self.get_content_system(
            user_id=user_id, account_id=account_id, project_id=project_id, system_id=system_id
        )

    def get_content_system(
        self,
        *,
        user_id: str,
        account_id: str,
        project_id: str,
        system_id: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        query = """SELECT * FROM content_system_versions
        WHERE project_id=? AND user_id=? AND account_id=?"""
        params: list[Any] = [project_id, user_id, account_id]
        if system_id:
            query += " AND id=?"
            params.append(system_id)
        if status:
            query += " AND status=?"
            params.append(status)
        query += " ORDER BY version DESC LIMIT 1"
        with self._connection() as db:
            row = db.execute(query, params).fetchone()
        if row is None:
            raise KeyError("content system not found in account scope")
        return _content_system_record(row)

    def propose_experiment(
        self,
        *,
        user_id: str,
        account_id: str,
        project_id: str,
        hypothesis: str,
        variable: dict[str, Any],
        variants: list[dict[str, Any]],
        prediction: dict[str, Any],
        success_criteria: dict[str, Any],
    ) -> dict[str, Any]:
        hypothesis_value = _text(hypothesis, field="hypothesis", limit=1_000)
        if not isinstance(variable, dict) or not variable.get("dimension"):
            raise ValueError("experiment variable requires a dimension")
        if not isinstance(variants, list) or not 2 <= len(variants) <= 8:
            raise ValueError("experiment requires 2 to 8 variants")
        if not isinstance(success_criteria, dict) or not success_criteria.get("primary_metric"):
            raise ValueError("success criteria require a primary_metric")
        with self._connection() as db:
            system = db.execute(
                """SELECT id FROM content_system_versions WHERE project_id=? AND user_id=?
                AND account_id=? AND status='approved'""",
                (project_id, user_id, account_id),
            ).fetchone()
        if system is None:
            raise ValueError("approved content system is required")
        content_system_id = str(system["id"])
        raw_key = _json(
            {"project_id": project_id, "content_system_id": content_system_id,
             "hypothesis": hypothesis_value, "variable": variable, "variants": variants},
            field="experiment_identity", limit=40_000,
        )
        source_key = "account-experiment:" + hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
        now = _now()
        with self._transaction() as db:
            existing = db.execute(
                "SELECT id FROM account_experiments WHERE source_key=?", (source_key,)
            ).fetchone()
            if existing is not None:
                experiment_id = existing["id"]
            else:
                experiment_id = _id("experiment")
                db.execute(
                    """INSERT INTO account_experiments
                    (id,source_key,project_id,user_id,account_id,content_system_id,
                     hypothesis,variable_json,
                     variants_json,asset_ids_json,prediction_json,success_criteria_json,
                     status,created_at,updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?, '[]',?,?, 'draft',?,?)""",
                    (
                        experiment_id, source_key, project_id, user_id, account_id,
                        content_system_id, hypothesis_value,
                        _json(variable, field="variable", limit=16_000),
                        _json(variants, field="variants", limit=40_000),
                        _json(prediction, field="prediction", limit=20_000),
                        _json(success_criteria, field="success_criteria", limit=20_000),
                        now, now,
                    ),
                )
        return self.get_experiment(
            user_id=user_id, account_id=account_id, project_id=project_id,
            experiment_id=experiment_id,
        )

    def approve_experiment(
        self,
        *,
        user_id: str,
        account_id: str,
        project_id: str,
        experiment_id: str,
        confirmed_by_user: bool,
    ) -> dict[str, Any]:
        if confirmed_by_user is not True:
            raise ValueError("explicit user confirmation is required")
        now = _now()
        with self._transaction() as db:
            updated = db.execute(
                """UPDATE account_experiments SET status='running',approved_at=?,updated_at=?
                WHERE id=? AND project_id=? AND user_id=? AND account_id=? AND status='draft'""",
                (now, now, experiment_id, project_id, user_id, account_id),
            ).rowcount
            if updated == 0:
                current = db.execute(
                    """SELECT status FROM account_experiments WHERE id=? AND project_id=?
                    AND user_id=? AND account_id=?""",
                    (experiment_id, project_id, user_id, account_id),
                ).fetchone()
                if current is None:
                    raise KeyError("experiment not found in account scope")
                if current["status"] != "running":
                    raise ValueError("only a draft experiment can be approved")
            _advance_stage(db, project_id, "experiment_running", now)
        return self.get_experiment(
            user_id=user_id, account_id=account_id, project_id=project_id,
            experiment_id=experiment_id,
        )

    def get_experiment(
        self, *, user_id: str, account_id: str, project_id: str, experiment_id: str
    ) -> dict[str, Any]:
        with self._connection() as db:
            row = db.execute(
                """SELECT * FROM account_experiments WHERE id=? AND project_id=?
                AND user_id=? AND account_id=?""",
                (experiment_id, project_id, user_id, account_id),
            ).fetchone()
        if row is None:
            raise KeyError("experiment not found in account scope")
        return _experiment_record(row)

    # ------------------------------------------------------------------
    # Influence calibration: replay-approved, versioned account strategy.
    # ------------------------------------------------------------------

    def apply_learning_calibration(
        self,
        *,
        user_id: str,
        account_id: str,
        candidate_id: str,
    ) -> dict[str, Any]:
        """Promote one accepted strategy candidate into active account weights.

        The learning-candidate table remains the review/audit owner.  This
        method owns only the durable, versioned strategy truth consumed by
        preflight.  It deliberately refuses raw ``weight`` candidates so replay
        approval and strategy review cannot be collapsed into one click.
        """

        with self._transaction() as db:
            candidate = db.execute(
                """SELECT * FROM marketing_learning_candidates
                WHERE id=? AND user_id=? AND account_id=?""",
                (candidate_id, user_id, account_id),
            ).fetchone()
            if candidate is None:
                raise KeyError("strategy learning candidate not found in account scope")
            if candidate["candidate_type"] != "strategy" or candidate["status"] != "accepted":
                raise ValueError("an accepted strategy candidate is required")
            proposal = json.loads(candidate["proposal_json"] or "{}")
            if proposal.get("kind") != "account_influence_calibration":
                raise ValueError("strategy candidate is not an account influence calibration")
            source_weight_id = str(proposal.get("source_weight_candidate_id") or "")
            source_weight = db.execute(
                """SELECT candidate_type,status,proposal_json
                FROM marketing_learning_candidates
                WHERE id=? AND user_id=? AND account_id=?""",
                (source_weight_id, user_id, account_id),
            ).fetchone()
            if source_weight is None or source_weight["candidate_type"] != "weight" \
                    or source_weight["status"] != "accepted":
                raise ValueError("calibration requires its replay-approved weight candidate")
            source_proposal = json.loads(source_weight["proposal_json"] or "{}")
            adjustment = proposal.get("proposed_adjustment")
            if adjustment != source_proposal.get("proposed_adjustment"):
                raise ValueError("strategy calibration diverges from the approved weight candidate")

            existing = db.execute(
                "SELECT * FROM account_influence_calibrations WHERE source_candidate_id=?",
                (candidate_id,),
            ).fetchone()
            if existing is not None:
                return _calibration_record(existing)

            project = db.execute(
                """SELECT id FROM account_strategy_projects
                WHERE user_id=? AND account_id=? AND status='active'""",
                (user_id, account_id),
            ).fetchone()
            if project is None:
                raise ValueError("active account strategy project is required")
            previous = db.execute(
                """SELECT * FROM account_influence_calibrations
                WHERE project_id=? AND status='active'""",
                (project["id"],),
            ).fetchone()
            base_weights = (
                json.loads(previous["weights_json"] or "{}") if previous is not None else None
            )
            weights = apply_influence_weight_adjustment(base_weights, adjustment)
            version = int(
                db.execute(
                    """SELECT COALESCE(MAX(version),0)+1
                    FROM account_influence_calibrations WHERE project_id=?""",
                    (project["id"],),
                ).fetchone()[0]
            )
            now = _now()
            if previous is not None:
                db.execute(
                    """UPDATE account_influence_calibrations SET status='superseded'
                    WHERE project_id=? AND status='active'""",
                    (project["id"],),
                )
            calibration_id = _id("calibration")
            db.execute(
                """INSERT INTO account_influence_calibrations
                (id,project_id,user_id,account_id,source_candidate_id,version,
                 formula_version,weights_json,adjustment_json,review_reason,status,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,'active',?)""",
                (
                    calibration_id,
                    project["id"],
                    user_id,
                    account_id,
                    candidate_id,
                    version,
                    str(proposal.get("score_version") or INFLUENCE_SCORE_VERSION),
                    _json(weights, field="influence_weights", limit=8_000),
                    _json(adjustment, field="influence_adjustment", limit=4_000),
                    str(candidate["decision_reason"] or "")[:500],
                    now,
                ),
            )
            created = db.execute(
                "SELECT * FROM account_influence_calibrations WHERE id=?",
                (calibration_id,),
            ).fetchone()
        return _calibration_record(created)

    def get_active_influence_calibration(
        self, *, user_id: str, account_id: str
    ) -> dict[str, Any] | None:
        with self._connection() as db:
            row = db.execute(
                """SELECT calibration.* FROM account_influence_calibrations AS calibration
                JOIN account_strategy_projects AS project ON project.id=calibration.project_id
                WHERE calibration.user_id=? AND calibration.account_id=?
                AND calibration.status='active' AND project.status='active'""",
                (user_id, account_id),
            ).fetchone()
        return _calibration_record(row) if row is not None else None

    def read_operating_model(
        self, *, user_id: str, account_id: str, project_id: str
    ) -> dict[str, Any]:
        """Bounded projection for Agent planning; no raw benchmark content."""

        with self._connection() as db:
            project = _require_project(
                db, user_id=user_id, account_id=account_id, project_id=project_id
            )
            profile = _latest(db, "creator_operating_profiles", project_id, "confirmed")
            route = _latest(db, "market_route_hypotheses", project_id, "selected")
            audience = _latest(db, "audience_hypotheses", project_id, "confirmed")
            positioning = _latest(db, "positioning_versions", project_id, "approved")
            content_system = _latest(db, "content_system_versions", project_id, "approved")
            experiments = db.execute(
                """SELECT COUNT(*) FROM account_experiments
                WHERE project_id=? AND user_id=? AND account_id=?""",
                (project_id, user_id, account_id),
            ).fetchone()[0]
            calibration = db.execute(
                """SELECT * FROM account_influence_calibrations
                WHERE project_id=? AND user_id=? AND account_id=? AND status='active'""",
                (project_id, user_id, account_id),
            ).fetchone()
        positioning_record = _positioning_record(positioning) if positioning else None
        content_system_record = _content_system_record(content_system) if content_system else None
        active_basis = {
            f"creator_profile:{profile['id']}" if profile else "creator_profile:missing",
            f"market_route:{route['id']}" if route else "market_route:missing",
            f"audience_hypothesis:{audience['id']}" if audience else "audience_hypothesis:missing",
        }
        positioning_basis = set(positioning_record["basis_refs"]) if positioning_record else set()
        positioning_current = bool(positioning_record) and active_basis <= positioning_basis
        content_system_current = bool(
            content_system_record
            and positioning
            and content_system_record["positioning_id"] == positioning["id"]
        )
        return {
            "project": _project(project),
            "creator_profile": _creator_record(profile) if profile else None,
            "market_route": _market_record(route) if route else None,
            "audience_hypothesis": _audience_record(audience) if audience else None,
            "benchmark_readiness": self.benchmark_readiness(
                user_id=user_id, account_id=account_id, project_id=project_id
            ),
            "positioning": positioning_record,
            "content_system": content_system_record,
            "strategy_alignment": {
                "positioning_current": positioning_current,
                "content_system_current": content_system_current,
                "stale_basis_refs": sorted(active_basis - positioning_basis),
            },
            "experiment_count": int(experiments),
            "influence_calibration": _calibration_record(calibration) if calibration else None,
        }

    def _verified_evidence(
        self,
        *,
        user_id: str,
        account_id: str,
        evidence_refs: list[str],
        require_any: bool = False,
    ) -> list[str]:
        refs = _string_list(evidence_refs, field="evidence_refs", limit=100)
        if not refs and not require_any:
            return []
        records = EvidenceRepository(self.paths).require_verified(
            user_id=user_id,
            account_id=account_id,
            evidence_ids=refs,
            require_any=require_any,
        )
        return [str(item["id"]) for item in records]


def _creator_profile(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("profile must be an object")
    list_fields = (
        "experiences", "skills", "proof_assets", "strong_views", "constraints",
        "taboos", "motivations", "unknowns",
    )
    payload = {key: _value_list(value.get(key), field=key) for key in list_fields}
    for key in ("identity", "expression_capabilities", "production_resources", "sustainability"):
        raw = value.get(key) or {}
        if not isinstance(raw, dict):
            raise ValueError(f"profile field {key} must be an object")
        payload[key] = raw
    payload["human_projection_model"] = build_human_projection_model(
        need_projections=value.get("need_projection_hypotheses"),
        cognitive_projections=(
            value.get("cognitive_projection_hypotheses")
            if value.get("cognitive_projection_hypotheses") is not None
            else value.get("cognitive_style_hypotheses")
        ),
        existence_strategies=(
            value.get("existence_strategy_hypotheses")
            if value.get("existence_strategy_hypotheses") is not None
            else value.get("existence_hypotheses")
        ),
    )
    if not any(payload[key] for key in ("experiences", "skills", "proof_assets")):
        raise ValueError("profile requires experience, skill, or proof assets")
    return payload


def _market_route(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("market route must be an object")
    scalar = (
        "label", "category", "subcategory", "target_audience", "urgent_problem",
        "content_promise", "creator_advantage", "competition_hypothesis",
    )
    payload = {key: _text(value.get(key), field=key, limit=1_500) for key in scalar}
    for key in ("platform_candidates", "monetization_paths", "risks", "data_gaps"):
        payload[key] = _value_list(value.get(key), field=key)
    sustainability = value.get("sustainability") or {}
    if not isinstance(sustainability, dict):
        raise ValueError("sustainability must be an object")
    payload["sustainability"] = sustainability
    return payload


def _positioning(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("positioning must be an object")
    missing = sorted(POSITIONING_REQUIRED - set(value))
    if missing:
        raise ValueError(f"positioning missing fields: {missing}")
    payload = dict(value)
    for key in ("promise", "differentiation", "persona", "audience_summary", "proof_mechanism"):
        payload[key] = _text(value.get(key), field=key, limit=2_000)
    for key in ("content_pillars", "tone", "taboos", "recurring_formats", "commercial_path"):
        payload[key] = _value_list(value.get(key), field=key, required=True)
    if not isinstance(value.get("monetization_boundary"), dict):
        raise ValueError("monetization_boundary must be an object")
    return payload


def _content_system(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("content system must be an object")
    missing = sorted(CONTENT_SYSTEM_REQUIRED - set(value))
    if missing:
        raise ValueError(f"content system missing fields: {missing}")
    payload = dict(value)
    for key in (
        "acquisition_lanes", "trust_lanes", "action_lanes", "recurring_series",
        "production_workflow", "commercial_boundaries",
    ):
        payload[key] = _value_list(value.get(key), field=key, required=True)
    for key in (
        "platform_expression", "publishing_cadence", "measurement_plan", "exploration_policy",
    ):
        if not isinstance(value.get(key), dict):
            raise ValueError(f"content system field {key} must be an object")
    return payload


def _match_dimensions(value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        raise ValueError("match_dimensions must be an object")
    result: dict[str, float] = {}
    for key, raw in value.items():
        if key not in MATCH_DIMENSIONS:
            raise ValueError(f"unsupported match dimension: {key}")
        result[key] = _confidence(raw)
    if len(result) < 3:
        raise ValueError("benchmark matching requires at least three dimensions")
    return result


def _require_project(db, *, user_id: str, account_id: str, project_id: str):
    row = db.execute(
        """SELECT * FROM account_strategy_projects
        WHERE id=? AND user_id=? AND account_id=? AND status='active'""",
        (project_id, user_id, account_id),
    ).fetchone()
    if row is None:
        raise KeyError("active strategy project not found in account scope")
    return row


def _require_confirmed_profile(db, project_id: str, user_id: str, account_id: str):
    row = db.execute(
        """SELECT * FROM creator_operating_profiles WHERE project_id=? AND user_id=?
        AND account_id=? AND status='confirmed'""",
        (project_id, user_id, account_id),
    ).fetchone()
    if row is None:
        raise ValueError("confirmed creator profile is required")
    return row


def _require_selected_route(db, project_id: str, user_id: str, account_id: str):
    row = db.execute(
        """SELECT * FROM market_route_hypotheses WHERE project_id=? AND user_id=?
        AND account_id=? AND status='selected'""",
        (project_id, user_id, account_id),
    ).fetchone()
    if row is None:
        raise ValueError("selected market route is required")
    return row


def _require_confirmed_audience(db, project_id: str, user_id: str, account_id: str):
    row = db.execute(
        """SELECT * FROM audience_hypotheses WHERE project_id=? AND user_id=?
        AND account_id=? AND status='confirmed'""",
        (project_id, user_id, account_id),
    ).fetchone()
    if row is None:
        raise ValueError("confirmed audience hypothesis is required")
    return row


def _require_benchmark(
    db, *, user_id: str, account_id: str, project_id: str, benchmark_id: str
):
    row = db.execute(
        """SELECT * FROM benchmark_accounts WHERE id=? AND project_id=?
        AND user_id=? AND target_account_id=?""",
        (benchmark_id, project_id, user_id, account_id),
    ).fetchone()
    if row is None:
        raise KeyError("benchmark account not found in account scope")
    return row


def _advance_stage(db, project_id: str, stage: str, now: str) -> None:
    order = {
        "goal_defined": 10,
        "creator_model_ready": 20,
        "market_routes_ready": 30,
        "market_route_selected": 40,
        "audience_hypothesis_ready": 50,
        "benchmark_graph_ready": 60,
        "positioning_approved": 70,
        "content_system_approved": 80,
        "experiment_running": 90,
    }
    current = db.execute(
        "SELECT stage FROM account_strategy_projects WHERE id=?", (project_id,)
    ).fetchone()
    current_stage = str(current["stage"] or "goal_defined") if current else "goal_defined"
    if order.get(stage, 0) < order.get(current_stage, 0):
        return
    db.execute(
        "UPDATE account_strategy_projects SET stage=?,updated_at=? WHERE id=?",
        (stage, now, project_id),
    )


def _next_version(db, table: str, project_id: str) -> int:
    return int(
        db.execute(
            f"SELECT COALESCE(MAX(version),0)+1 FROM {table} WHERE project_id=?",
            (project_id,),
        ).fetchone()[0]
    )


def _latest(db, table: str, project_id: str, status: str):
    return db.execute(
        f"SELECT * FROM {table} WHERE project_id=? AND status=? ORDER BY version DESC LIMIT 1",
        (project_id, status),
    ).fetchone()


def _project(row) -> dict[str, Any]:
    value = dict(row)
    value["constraints"] = json.loads(value.pop("constraints_json") or "{}")
    return value


def _creator_record(row) -> dict[str, Any]:
    value = dict(row)
    value["profile"] = json.loads(value.pop("profile_json") or "{}")
    value["source_refs"] = json.loads(value.pop("source_refs_json") or "[]")
    return value


def _market_record(row) -> dict[str, Any]:
    value = dict(row)
    value["route"] = json.loads(value.pop("route_json") or "{}")
    value["evidence_refs"] = json.loads(value.pop("evidence_refs_json") or "[]")
    return value


def _audience_record(row) -> dict[str, Any]:
    value = dict(row)
    for key in (
        "segments_json", "pains_json", "scenarios_json", "jobs_json",
        "current_alternatives_json", "trust_barriers_json", "desired_outcomes_json",
        "behavior_signals_json", "exclusions_json", "data_gaps_json",
    ):
        value[key.removesuffix("_json")] = json.loads(value.pop(key) or "[]")
    legacy_strategies = json.loads(value.pop("existence_hypotheses_json", "[]") or "[]")
    legacy_cognition = json.loads(
        value.pop("cognitive_style_hypotheses_json", "[]") or "[]"
    )
    strategies = json.loads(
        value.pop("existence_strategy_hypotheses_json", "[]") or "[]"
    )
    needs = json.loads(value.pop("need_projection_hypotheses_json", "[]") or "[]")
    cognition = json.loads(
        value.pop("cognitive_projection_hypotheses_json", "[]") or "[]"
    )
    collective = json.loads(
        value.pop("collective_projection_hypotheses_json", "[]") or "[]"
    )
    value["human_projection_model"] = build_human_projection_model(
        need_projections=needs,
        cognitive_projections=cognition or legacy_cognition,
        existence_strategies=strategies or legacy_strategies,
        collective_projections=collective,
    )
    return value


def _benchmark_record(row) -> dict[str, Any]:
    value = dict(row)
    value["match_dimensions"] = json.loads(value.pop("match_dimensions_json") or "{}")
    value["evidence_refs"] = json.loads(value.pop("evidence_refs_json") or "[]")
    value["metadata"] = json.loads(value.pop("metadata_json") or "{}")
    return value


def _benchmark_observation_record(row) -> dict[str, Any]:
    value = dict(row)
    value["value"] = json.loads(value.pop("value_json") or "{}")
    value["evidence_refs"] = json.loads(value.pop("evidence_refs_json") or "[]")
    value["provenance"] = json.loads(value.pop("provenance_json") or "{}")
    return value


def _positioning_record(row) -> dict[str, Any]:
    value = dict(row)
    value["positioning"] = json.loads(value.pop("positioning_json") or "{}")
    value["basis_refs"] = json.loads(value.pop("basis_refs_json") or "[]")
    value["data_gaps"] = json.loads(value.pop("data_gaps_json") or "[]")
    return value


def _content_system_record(row) -> dict[str, Any]:
    value = dict(row)
    value["system"] = json.loads(value.pop("system_json") or "{}")
    value["basis_refs"] = json.loads(value.pop("basis_refs_json") or "[]")
    return value


def _experiment_record(row) -> dict[str, Any]:
    value = dict(row)
    for key in ("variable_json", "prediction_json", "success_criteria_json"):
        value[key.removesuffix("_json")] = json.loads(value.pop(key) or "{}")
    for key in ("variants_json", "asset_ids_json"):
        value[key.removesuffix("_json")] = json.loads(value.pop(key) or "[]")
    return value


def _calibration_record(row) -> dict[str, Any]:
    value = dict(row)
    value["weights"] = json.loads(value.pop("weights_json") or "{}")
    value["adjustment"] = json.loads(value.pop("adjustment_json") or "{}")
    return value


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _confidence(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("confidence values must be numeric")
    if not 0 <= float(value) <= 1:
        raise ValueError("confidence values must be between 0 and 1")
    return round(float(value), 4)


def _text(value: Any, *, field: str, limit: int) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} is required")
    if len(text) > limit:
        raise ValueError(f"{field} exceeds {limit} characters")
    return text


def _json(value: Any, *, field: str, limit: int) -> str:
    try:
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be JSON serializable") from exc
    if len(encoded.encode("utf-8")) > limit:
        raise ValueError(f"{field} exceeds {limit} bytes")
    return encoded


def _value_list(
    value: Any, *, field: str, required: bool = False, limit: int = 30
) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    if required and not value:
        raise ValueError(f"{field} requires at least one item")
    if len(value) > limit:
        raise ValueError(f"{field} exceeds {limit} items")
    _json(value, field=field, limit=24_000)
    return value


def _string_list(value: Any, *, field: str, limit: int) -> list[str]:
    items = _value_list(value, field=field, limit=limit)
    result = [str(item).strip() for item in items if str(item).strip()]
    if len(result) != len(items):
        raise ValueError(f"{field} contains an empty item")
    return list(dict.fromkeys(result))


def _https_url(value: Any) -> str:
    text = str(value or "").strip()
    parsed = urlsplit(text)
    if parsed.scheme.lower() != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("profile_url must be a public HTTPS URL")
    return text
