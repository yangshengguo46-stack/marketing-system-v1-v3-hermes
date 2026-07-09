"""Product-owned account lifecycle truth and deterministic next-action logic."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .store import AgentCoreStore, _id, _json, _now


PROJECT_STATUSES = frozenset({"active", "completed", "archived"})
HYPOTHESIS_STATUSES = frozenset({"draft", "confirmed", "superseded"})
BENCHMARK_RELATIONS = frozenset({"direct", "adjacent", "aspirational", "negative"})
OBSERVATION_DIMENSIONS = frozenset({
    "audience", "positioning", "content_pillar", "format", "hook",
    "tone", "cadence", "engagement", "conversion", "gap",
})
SOURCE_KINDS = frozenset({
    "official_api", "creator_center_mcp", "public_web", "user_input", "model_inference",
})
BENCHMARK_SELECTION_STATUSES = frozenset({"candidate", "selected", "rejected"})
BENCHMARK_REQUIRED_DIMENSIONS = frozenset({
    "audience", "positioning", "content_pillar", "format", "engagement",
})
BENCHMARK_MIN_SELECTED = 2
BENCHMARK_MIN_SAMPLES_PER_ACCOUNT = 5
POSITIONING_REQUIRED_FIELDS = frozenset({
    "promise", "differentiation", "persona", "content_pillars", "tone", "taboos",
})
ACTUAL_AUDIENCE_SOURCE_KINDS = frozenset({"official_api", "creator_center_mcp"})
ACTUAL_AUDIENCE_DIMENSIONS = frozenset({
    "gender", "age", "region", "active_days", "interests", "device", "growth",
})
EXPERIMENT_STATUSES = frozenset({"draft", "running", "review_due", "completed", "cancelled"})
STRATEGY_TRIGGERS = frozenset({
    "experiment_retro", "audience_gap", "user_feedback", "failure_recovery",
    "weight_candidate_replay",
})
WEIGHT_CALIBRATION_METRICS = {
    "PlatformReachPotential": {
        "primary_metric": "attention",
        "label": "曝光与点击进入",
        "accept_if": "真实浏览量或进入率提升，且预演偏差收窄",
    },
    "RetentionDesign": {
        "primary_metric": "retention",
        "label": "完播与停留",
        "accept_if": "完播率、平均播放时长或关键段留存提升",
    },
    "PersuasionScore": {
        "primary_metric": "trust",
        "label": "信任互动",
        "accept_if": "评论质量、收藏、转发或私信线索提升",
    },
    "BusinessValue": {
        "primary_metric": "action",
        "label": "商业转化意图",
        "accept_if": "关注、咨询、点击或明确行动意图提升",
    },
    "RiskPenalty": {
        "primary_metric": "risk",
        "label": "风险控制",
        "accept_if": "负反馈、违规风险或争议失控下降",
    },
}
DEFAULT_WEIGHT_CALIBRATION_METRIC = {
    "primary_metric": "overall_fit",
    "label": "账号适配度",
    "accept_if": "发布回执显示该策略方向优于原有判断",
}


@dataclass(frozen=True)
class LifecycleStatus:
    project_id: str
    stage: str
    next_action: str
    audience_hypothesis: dict[str, Any] | None
    benchmark_count: int
    benchmark_observation_count: int
    benchmark_readiness: dict[str, Any]
    positioning: dict[str, Any] | None
    experiment_count: int
    data_gaps: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "stage": self.stage,
            "next_action": self.next_action,
            "audience_hypothesis": self.audience_hypothesis,
            "benchmark_count": self.benchmark_count,
            "benchmark_observation_count": self.benchmark_observation_count,
            "benchmark_readiness": self.benchmark_readiness,
            "positioning": self.positioning,
            "experiment_count": self.experiment_count,
            "data_gaps": self.data_gaps,
        }


class AccountLifecycleService:
    """Own lifecycle state; Agent memory remains a derived consumer."""

    def __init__(self, store: AgentCoreStore):
        self.store = store

    @staticmethod
    def _require_scope(user_id: str, account_id: str) -> None:
        if not user_id or not user_id.strip():
            raise ValueError("user_id is required")
        if not account_id or not account_id.strip():
            raise ValueError("account_id is required")

    def create_project(
        self, *, user_id: str, account_id: str, business_goal: str,
        constraints: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._require_scope(user_id, account_id)
        if not business_goal or not business_goal.strip():
            raise ValueError("business_goal is required")
        project_id = _id("strategy")
        timestamp = _now()
        try:
            with self.store._connect() as db:
                db.execute(
                    """INSERT INTO account_strategy_projects
                    (id,user_id,account_id,business_goal,constraints_json,stage,status,created_at,updated_at)
                    VALUES (?,?,?,?,?,'goal_defined','active',?,?)""",
                    (project_id, user_id, account_id, business_goal.strip(),
                     _json(constraints or {}), timestamp, timestamp),
                )
        except Exception as exc:
            if "UNIQUE constraint failed" in str(exc):
                raise ValueError("an active strategy project already exists for this account") from exc
            raise
        return self.get_project(user_id=user_id, account_id=account_id, project_id=project_id)

    def get_project(self, *, user_id: str, account_id: str, project_id: str) -> dict[str, Any]:
        self._require_scope(user_id, account_id)
        with self.store._connect() as db:
            row = db.execute(
                "SELECT * FROM account_strategy_projects WHERE id=? AND user_id=? AND account_id=?",
                (project_id, user_id, account_id),
            ).fetchone()
        if row is None:
            raise KeyError("strategy project not found in account scope")
        result = dict(row)
        result["constraints"] = json.loads(result.pop("constraints_json"))
        return result

    def get_active_project(self, *, user_id: str, account_id: str) -> dict[str, Any] | None:
        self._require_scope(user_id, account_id)
        with self.store._connect() as db:
            row = db.execute(
                """SELECT id FROM account_strategy_projects
                WHERE user_id=? AND account_id=? AND status='active'""",
                (user_id, account_id),
            ).fetchone()
        return None if row is None else self.get_project(
            user_id=user_id, account_id=account_id, project_id=row["id"]
        )

    def bind_prospect_project(
        self, *, user_id: str, prospect_account_id: str, target_account_id: str,
        project_id: str,
    ) -> dict[str, Any]:
        """Atomically attach a pre-login strategy project to a real account.

        This is deliberately a move, not a merge.  If the real account already
        owns an active strategy project, product code must ask the user which
        project to keep instead of silently mixing two account strategies.
        """
        self._require_scope(user_id, prospect_account_id)
        self._require_scope(user_id, target_account_id)
        if not prospect_account_id.startswith("prospect_"):
            raise ValueError("source account must be a prospect workspace")
        if target_account_id.startswith("prospect_"):
            raise ValueError("target account must be a connected account")
        if prospect_account_id == target_account_id:
            raise ValueError("source and target account must differ")
        if not project_id or not project_id.strip():
            raise ValueError("project_id is required for an idempotent binding")

        with self.store._connect() as db:
            source = db.execute(
                """SELECT * FROM account_strategy_projects
                WHERE id=? AND user_id=? AND account_id=? AND status='active'""",
                (project_id, user_id, prospect_account_id),
            ).fetchone()
            if source is None:
                rebound = db.execute(
                    """SELECT id FROM account_strategy_projects
                    WHERE id=? AND user_id=? AND account_id=? AND status='active'""",
                    (project_id, user_id, target_account_id),
                ).fetchone()
                if rebound is not None:
                    return {
                        "status": "already_bound", "project_id": project_id,
                        "from_account_id": prospect_account_id,
                        "account_id": target_account_id, "updated": {},
                        "lifecycle": self.read_status(
                            user_id=user_id, account_id=target_account_id, project_id=project_id,
                        ),
                    }
                raise KeyError("active prospect strategy project not found")

            existing = db.execute(
                """SELECT id FROM account_strategy_projects
                WHERE user_id=? AND account_id=? AND status='active'""",
                (user_id, target_account_id),
            ).fetchone()
            if existing is not None:
                raise ValueError(
                    "target account already has an active strategy project; explicit merge is required"
                )

            updates = {
                "audience_hypotheses": ("account_id",),
                "audience_snapshots": ("account_id",),
                "positioning_versions": ("account_id",),
                "account_experiments": ("account_id",),
                "strategy_candidates": ("account_id",),
                "benchmark_observations": ("target_account_id",),
            }
            counts: dict[str, int] = {}
            for table, (column,) in updates.items():
                cursor = db.execute(
                    f"UPDATE {table} SET {column}=? WHERE project_id=? AND user_id=? AND {column}=?",
                    (target_account_id, project_id, user_id, prospect_account_id),
                )
                counts[table] = cursor.rowcount

            cursor = db.execute(
                """UPDATE benchmark_accounts SET target_account_id=?
                WHERE project_id=? AND user_id=? AND target_account_id=?""",
                (target_account_id, project_id, user_id, prospect_account_id),
            )
            counts["benchmark_accounts"] = cursor.rowcount

            # Only assets explicitly attached to this project's experiments
            # move with the strategy. Unrelated drafts in the prospect scope do not.
            cursor = db.execute(
                """UPDATE content_assets SET account_id=? WHERE user_id=? AND account_id=?
                AND experiment_id IN (
                    SELECT id FROM account_experiments WHERE project_id=? AND user_id=?
                )""",
                (target_account_id, user_id, prospect_account_id, project_id, user_id),
            )
            counts["content_assets"] = cursor.rowcount

            cursor = db.execute(
                """UPDATE account_strategy_projects SET account_id=?, updated_at=?
                WHERE id=? AND user_id=? AND account_id=? AND status='active'""",
                (target_account_id, _now(), project_id, user_id, prospect_account_id),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("prospect strategy binding lost its source project")
            counts["account_strategy_projects"] = cursor.rowcount

        return {
            "status": "bound", "project_id": project_id,
            "from_account_id": prospect_account_id,
            "account_id": target_account_id, "updated": counts,
            "lifecycle": self.read_status(
                user_id=user_id, account_id=target_account_id, project_id=project_id,
            ),
        }

    def read_account_status(self, *, user_id: str, account_id: str) -> dict[str, Any]:
        """Read the active lifecycle without making an empty project as a side effect."""
        project = self.get_active_project(user_id=user_id, account_id=account_id)
        if project is None:
            return {
                "project_id": None,
                "stage": "not_started",
                "next_action": "draft_audience_hypothesis",
                "audience_hypothesis": None,
                "benchmark_count": 0,
                "benchmark_observation_count": 0,
                "benchmark_readiness": {
                    "ready": False,
                    "missing": ["selected_accounts", "sample_depth", "dimension_coverage", "negative_benchmark"],
                },
                "positioning": None,
                "experiment_count": 0,
                "data_gaps": [],
            }
        return self.read_status(
            user_id=user_id, account_id=account_id, project_id=project["id"]
        )

    def draft_audience_hypothesis(
        self, *, user_id: str, account_id: str, project_id: str,
        segments: list[dict[str, Any]], pains: list[str] | None = None,
        scenarios: list[str] | None = None, exclusions: list[str] | None = None,
        data_gaps: list[str] | None = None,
    ) -> dict[str, Any]:
        self.get_project(user_id=user_id, account_id=account_id, project_id=project_id)
        if not segments:
            raise ValueError("at least one audience segment is required")
        timestamp = _now()
        hypothesis_id = _id("audience")
        with self.store._connect() as db:
            version = db.execute(
                "SELECT COALESCE(MAX(version),0)+1 FROM audience_hypotheses WHERE project_id=?",
                (project_id,),
            ).fetchone()[0]
            db.execute(
                """INSERT INTO audience_hypotheses
                (id,project_id,user_id,account_id,version,segments_json,pains_json,scenarios_json,
                 exclusions_json,data_gaps_json,status,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,'draft',?)""",
                (hypothesis_id, project_id, user_id, account_id, version, _json(segments),
                 _json(pains or []), _json(scenarios or []), _json(exclusions or []),
                 _json(data_gaps or []), timestamp),
            )
        return self._get_hypothesis(user_id, account_id, project_id, hypothesis_id)

    def add_benchmark_account(
        self, *, user_id: str, account_id: str, project_id: str, platform: str,
        account_handle: str, account_name: str | None, relation: str,
        selection_reason: str, source_ref: str, selection_status: str = "selected",
    ) -> dict[str, Any]:
        self.get_project(user_id=user_id, account_id=account_id, project_id=project_id)
        if relation not in BENCHMARK_RELATIONS:
            raise ValueError(f"unsupported benchmark relation: {relation}")
        if selection_status not in BENCHMARK_SELECTION_STATUSES:
            raise ValueError(f"unsupported benchmark selection status: {selection_status}")
        if not all(str(v or "").strip() for v in (platform, account_handle, selection_reason, source_ref)):
            raise ValueError("platform, account_handle, selection_reason and source_ref are required")
        benchmark_id = _id("bench")
        with self.store._connect() as db:
            db.execute(
                """INSERT INTO benchmark_accounts
                (id,user_id,platform,account_handle,account_name,metadata_json,created_at,
                 project_id,target_account_id,relation,selection_reason,source_ref,selection_status)
                VALUES (?,?,?,?,?,'{}',?,?,?,?,?,?,?)""",
                (benchmark_id, user_id, platform.strip(), account_handle.strip(),
                 account_name.strip() if isinstance(account_name, str) and account_name.strip() else None,
                 _now(), project_id, account_id, relation, selection_reason.strip(), source_ref.strip(),
                 selection_status),
            )
        return self.get_benchmark_account(
            user_id=user_id, account_id=account_id, project_id=project_id,
            benchmark_account_id=benchmark_id,
        )

    def get_benchmark_account(
        self, *, user_id: str, account_id: str, project_id: str,
        benchmark_account_id: str,
    ) -> dict[str, Any]:
        with self.store._connect() as db:
            row = db.execute(
                """SELECT * FROM benchmark_accounts WHERE id=? AND user_id=?
                AND target_account_id=? AND project_id=?""",
                (benchmark_account_id, user_id, account_id, project_id),
            ).fetchone()
        if row is None:
            raise KeyError("benchmark account not found in account scope")
        result = dict(row)
        result["metadata"] = json.loads(result.pop("metadata_json"))
        return result

    def decide_benchmark_account(
        self, *, user_id: str, account_id: str, project_id: str,
        benchmark_account_id: str, decision: str, relation: str | None = None,
    ) -> dict[str, Any]:
        if decision not in {"selected", "rejected"}:
            raise ValueError("benchmark decision must be selected or rejected")
        if relation is not None and relation not in BENCHMARK_RELATIONS:
            raise ValueError(f"unsupported benchmark relation: {relation}")
        if relation is not None and decision != "selected":
            raise ValueError("relation can only be changed when selecting a benchmark")
        self.get_benchmark_account(
            user_id=user_id, account_id=account_id, project_id=project_id,
            benchmark_account_id=benchmark_account_id,
        )
        with self.store._connect() as db:
            if relation is None:
                db.execute(
                    """UPDATE benchmark_accounts SET selection_status=? WHERE id=? AND user_id=?
                    AND target_account_id=? AND project_id=?""",
                    (decision, benchmark_account_id, user_id, account_id, project_id),
                )
            else:
                db.execute(
                    """UPDATE benchmark_accounts SET selection_status=?,relation=?
                    WHERE id=? AND user_id=? AND target_account_id=? AND project_id=?""",
                    (decision, relation, benchmark_account_id, user_id, account_id, project_id),
                )
        return self.get_benchmark_account(
            user_id=user_id, account_id=account_id, project_id=project_id,
            benchmark_account_id=benchmark_account_id,
        )

    def list_benchmark_accounts(
        self, *, user_id: str, account_id: str, project_id: str,
    ) -> list[dict[str, Any]]:
        self.get_project(user_id=user_id, account_id=account_id, project_id=project_id)
        with self.store._connect() as db:
            ids = db.execute(
                """SELECT id FROM benchmark_accounts WHERE user_id=? AND target_account_id=?
                AND project_id=? ORDER BY created_at""", (user_id, account_id, project_id)
            ).fetchall()
        return [self.get_benchmark_account(
            user_id=user_id, account_id=account_id, project_id=project_id,
            benchmark_account_id=row["id"],
        ) for row in ids]

    def add_benchmark_sample(
        self, *, user_id: str, account_id: str, project_id: str,
        benchmark_account_id: str, video_id: str | None, title: str,
        transcript: str | None, metrics: dict[str, Any] | None,
        provenance: dict[str, Any],
    ) -> dict[str, Any]:
        benchmark = self.get_benchmark_account(
            user_id=user_id, account_id=account_id, project_id=project_id,
            benchmark_account_id=benchmark_account_id,
        )
        if benchmark["selection_status"] == "rejected":
            raise ValueError("rejected benchmark account cannot receive samples")
        source_kind = str(provenance.get("source_kind") or "")
        source_ref = str(provenance.get("source_ref") or "").strip()
        captured_at = str(provenance.get("captured_at") or "").strip()
        if source_kind not in SOURCE_KINDS or not source_ref or not captured_at:
            raise ValueError("provenance requires valid source_kind, source_ref and captured_at")
        if not title.strip():
            raise ValueError("sample title is required")
        sample_id = _id("sample")
        with self.store._connect() as db:
            db.execute(
                """INSERT INTO benchmark_samples
                (id,benchmark_account_id,video_id,title,transcript,metrics_json,scores_json,
                 created_at,provenance_json) VALUES (?,?,?,?,?,?,'null',?,?)""",
                (sample_id, benchmark_account_id, video_id, title.strip(), transcript,
                 _json(metrics or {}), _now(), _json(provenance)),
            )
        return self.get_benchmark_sample(
            user_id=user_id, account_id=account_id, project_id=project_id, sample_id=sample_id,
        )

    def get_benchmark_sample(
        self, *, user_id: str, account_id: str, project_id: str, sample_id: str,
    ) -> dict[str, Any]:
        with self.store._connect() as db:
            row = db.execute(
                """SELECT s.* FROM benchmark_samples s JOIN benchmark_accounts b
                ON b.id=s.benchmark_account_id WHERE s.id=? AND b.user_id=?
                AND b.target_account_id=? AND b.project_id=?""",
                (sample_id, user_id, account_id, project_id),
            ).fetchone()
        if row is None:
            raise KeyError("benchmark sample not found in account scope")
        result = dict(row)
        result["metrics"] = json.loads(result.pop("metrics_json"))
        scores = result.pop("scores_json")
        result["scores"] = json.loads(scores) if scores and scores != "null" else None
        result["provenance"] = json.loads(result.pop("provenance_json"))
        return result

    def list_benchmark_samples(
        self, *, user_id: str, account_id: str, project_id: str,
    ) -> list[dict[str, Any]]:
        with self.store._connect() as db:
            rows = db.execute(
                """SELECT s.id FROM benchmark_samples s JOIN benchmark_accounts b
                ON b.id=s.benchmark_account_id WHERE b.user_id=? AND b.target_account_id=?
                AND b.project_id=? ORDER BY s.created_at""",
                (user_id, account_id, project_id),
            ).fetchall()
        return [self.get_benchmark_sample(
            user_id=user_id, account_id=account_id, project_id=project_id, sample_id=row["id"],
        ) for row in rows]

    def add_benchmark_observation(
        self, *, user_id: str, account_id: str, project_id: str,
        benchmark_account_id: str, dimension: str, value: dict[str, Any],
        provenance: dict[str, Any], confidence: float,
    ) -> dict[str, Any]:
        self.get_benchmark_account(
            user_id=user_id, account_id=account_id, project_id=project_id,
            benchmark_account_id=benchmark_account_id,
        )
        benchmark = self.get_benchmark_account(
            user_id=user_id, account_id=account_id, project_id=project_id,
            benchmark_account_id=benchmark_account_id,
        )
        if benchmark["selection_status"] != "selected":
            raise ValueError("benchmark account must be selected before adding observations")
        if dimension not in OBSERVATION_DIMENSIONS:
            raise ValueError(f"unsupported observation dimension: {dimension}")
        source_kind = str(provenance.get("source_kind") or "")
        source_ref = str(provenance.get("source_ref") or "").strip()
        captured_at = str(provenance.get("captured_at") or "").strip()
        if source_kind not in SOURCE_KINDS or not source_ref or not captured_at:
            raise ValueError("provenance requires valid source_kind, source_ref and captured_at")
        if not 0 <= confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        observation_id = _id("benchobs")
        with self.store._connect() as db:
            db.execute(
                """INSERT INTO benchmark_observations
                (id,benchmark_account_id,project_id,user_id,target_account_id,dimension,
                 value_json,provenance_json,confidence,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (observation_id, benchmark_account_id, project_id, user_id, account_id,
                 dimension, _json(value), _json(provenance), float(confidence), _now()),
            )
        return self.get_benchmark_observation(
            user_id=user_id, account_id=account_id, project_id=project_id,
            observation_id=observation_id,
        )

    def get_benchmark_observation(
        self, *, user_id: str, account_id: str, project_id: str, observation_id: str,
    ) -> dict[str, Any]:
        with self.store._connect() as db:
            row = db.execute(
                """SELECT * FROM benchmark_observations WHERE id=? AND user_id=?
                AND target_account_id=? AND project_id=?""",
                (observation_id, user_id, account_id, project_id),
            ).fetchone()
        if row is None:
            raise KeyError("benchmark observation not found in account scope")
        result = dict(row)
        result["value"] = json.loads(result.pop("value_json"))
        result["provenance"] = json.loads(result.pop("provenance_json"))
        return result

    def list_benchmark_observations(
        self, *, user_id: str, account_id: str, project_id: str,
        benchmark_account_id: str | None = None,
    ) -> list[dict[str, Any]]:
        query = """SELECT id FROM benchmark_observations WHERE user_id=?
            AND target_account_id=? AND project_id=?"""
        args: list[Any] = [user_id, account_id, project_id]
        if benchmark_account_id:
            query += " AND benchmark_account_id=?"
            args.append(benchmark_account_id)
        query += " ORDER BY created_at"
        with self.store._connect() as db:
            rows = db.execute(query, args).fetchall()
        return [self.get_benchmark_observation(
            user_id=user_id, account_id=account_id, project_id=project_id,
            observation_id=row["id"],
        ) for row in rows]

    def benchmark_readiness(
        self, *, user_id: str, account_id: str, project_id: str,
    ) -> dict[str, Any]:
        """Return an evidence gate; a mere account name never unlocks positioning."""
        self.get_project(user_id=user_id, account_id=account_id, project_id=project_id)
        with self.store._connect() as db:
            selected = db.execute(
                """SELECT id, relation FROM benchmark_accounts WHERE user_id=?
                AND target_account_id=? AND project_id=? AND selection_status='selected'""",
                (user_id, account_id, project_id),
            ).fetchall()
            sample_counts = {
                row["benchmark_account_id"]: row["count"] for row in db.execute(
                    """SELECT s.benchmark_account_id, COUNT(*) AS count FROM benchmark_samples s
                    JOIN benchmark_accounts b ON b.id=s.benchmark_account_id WHERE b.user_id=?
                    AND b.target_account_id=? AND b.project_id=? AND b.selection_status='selected'
                    GROUP BY s.benchmark_account_id""", (user_id, account_id, project_id)
                ).fetchall()
            }
            dimensions = {row["dimension"] for row in db.execute(
                """SELECT DISTINCT o.dimension FROM benchmark_observations o
                JOIN benchmark_accounts b ON b.id=o.benchmark_account_id WHERE o.user_id=?
                AND o.target_account_id=? AND o.project_id=? AND b.selection_status='selected'""",
                (user_id, account_id, project_id),
            ).fetchall()}

        selected_ids = [row["id"] for row in selected]
        shallow = [
            benchmark_id for benchmark_id in selected_ids
            if sample_counts.get(benchmark_id, 0) < BENCHMARK_MIN_SAMPLES_PER_ACCOUNT
        ]
        missing_dimensions = sorted(BENCHMARK_REQUIRED_DIMENSIONS - dimensions)
        has_negative = any(row["relation"] == "negative" for row in selected)
        missing: list[str] = []
        if len(selected) < BENCHMARK_MIN_SELECTED:
            missing.append("selected_accounts")
        if shallow:
            missing.append("sample_depth")
        if missing_dimensions:
            missing.append("dimension_coverage")
        if not has_negative:
            missing.append("negative_benchmark")
        return {
            "ready": not missing,
            "selected_count": len(selected),
            "minimum_selected": BENCHMARK_MIN_SELECTED,
            "minimum_samples_per_account": BENCHMARK_MIN_SAMPLES_PER_ACCOUNT,
            "sample_counts": sample_counts,
            "shallow_benchmark_ids": shallow,
            "covered_dimensions": sorted(dimensions),
            "required_dimensions": sorted(BENCHMARK_REQUIRED_DIMENSIONS),
            "missing_dimensions": missing_dimensions,
            "has_negative_benchmark": has_negative,
            "missing": missing,
        }

    def draft_positioning(
        self, *, user_id: str, account_id: str, project_id: str,
        positioning: dict[str, Any], evidence_refs: list[str],
        rollback_of: str | None = None,
    ) -> dict[str, Any]:
        self.get_project(user_id=user_id, account_id=account_id, project_id=project_id)
        readiness = self.benchmark_readiness(
            user_id=user_id, account_id=account_id, project_id=project_id,
        )
        if not readiness["ready"]:
            raise ValueError(f"benchmark evidence is not ready: {readiness['missing']}")
        missing_fields = sorted(POSITIONING_REQUIRED_FIELDS - set(positioning))
        if missing_fields:
            raise ValueError(f"positioning missing required fields: {missing_fields}")
        if not all(str(positioning.get(key) or "").strip() for key in ("promise", "differentiation", "persona")):
            raise ValueError("promise, differentiation and persona cannot be empty")
        for key in ("content_pillars", "tone", "taboos"):
            if not isinstance(positioning.get(key), list):
                raise ValueError(f"positioning field {key} must be an array")
        if not evidence_refs:
            raise ValueError("positioning requires evidence_refs")
        with self.store._connect() as db:
            audience_row = db.execute(
                """SELECT id FROM audience_hypotheses WHERE project_id=? AND user_id=?
                AND account_id=? AND status='confirmed'""", (project_id, user_id, account_id)
            ).fetchone()
            if audience_row is None:
                raise ValueError("a confirmed audience hypothesis is required")
            valid_evidence = {
                row["id"] for row in db.execute(
                    """SELECT id FROM benchmark_observations WHERE user_id=?
                    AND target_account_id=? AND project_id=?""",
                    (user_id, account_id, project_id),
                ).fetchall()
            }
            if not set(evidence_refs).issubset(valid_evidence):
                raise ValueError("positioning evidence_refs contain out-of-scope observations")
            version = db.execute(
                "SELECT COALESCE(MAX(version),0)+1 FROM positioning_versions WHERE project_id=?",
                (project_id,),
            ).fetchone()[0]
            positioning_id = _id("positioning")
            payload = dict(positioning)
            payload["audience_hypothesis_id"] = audience_row["id"]
            if rollback_of:
                payload["rollback_of"] = rollback_of
            db.execute(
                """INSERT INTO positioning_versions
                (id,project_id,user_id,account_id,version,positioning_json,evidence_refs_json,
                 status,created_at) VALUES (?,?,?,?,?,?,?,'draft',?)""",
                (positioning_id, project_id, user_id, account_id, version,
                 _json(payload), _json(evidence_refs), _now()),
            )
        return self.get_positioning(
            user_id=user_id, account_id=account_id, project_id=project_id,
            positioning_id=positioning_id,
        )

    def get_positioning(
        self, *, user_id: str, account_id: str, project_id: str, positioning_id: str,
    ) -> dict[str, Any]:
        with self.store._connect() as db:
            row = db.execute(
                """SELECT * FROM positioning_versions WHERE id=? AND user_id=?
                AND account_id=? AND project_id=?""",
                (positioning_id, user_id, account_id, project_id),
            ).fetchone()
        if row is None:
            raise KeyError("positioning version not found in account scope")
        result = dict(row)
        result["positioning"] = json.loads(result.pop("positioning_json"))
        result["evidence_refs"] = json.loads(result.pop("evidence_refs_json"))
        return result

    def list_positioning_versions(
        self, *, user_id: str, account_id: str, project_id: str,
    ) -> list[dict[str, Any]]:
        with self.store._connect() as db:
            rows = db.execute(
                """SELECT id FROM positioning_versions WHERE user_id=? AND account_id=?
                AND project_id=? ORDER BY version""", (user_id, account_id, project_id)
            ).fetchall()
        return [self.get_positioning(
            user_id=user_id, account_id=account_id, project_id=project_id,
            positioning_id=row["id"],
        ) for row in rows]

    def approve_positioning(
        self, *, user_id: str, account_id: str, project_id: str, positioning_id: str,
    ) -> dict[str, Any]:
        current = self.get_positioning(
            user_id=user_id, account_id=account_id, project_id=project_id,
            positioning_id=positioning_id,
        )
        if current["status"] != "draft":
            raise ValueError("only a draft positioning can be approved")
        timestamp = _now()
        with self.store._connect() as db:
            db.execute(
                """UPDATE positioning_versions SET status='superseded'
                WHERE project_id=? AND user_id=? AND account_id=? AND status='approved'""",
                (project_id, user_id, account_id),
            )
            changed = db.execute(
                """UPDATE positioning_versions SET status='approved',approved_at=?
                WHERE id=? AND project_id=? AND user_id=? AND account_id=? AND status='draft'""",
                (timestamp, positioning_id, project_id, user_id, account_id),
            )
            if changed.rowcount != 1:
                raise ValueError("positioning approval conflicted with another update")
        return self.get_positioning(
            user_id=user_id, account_id=account_id, project_id=project_id,
            positioning_id=positioning_id,
        )

    def rollback_positioning(
        self, *, user_id: str, account_id: str, project_id: str,
        target_positioning_id: str,
    ) -> dict[str, Any]:
        target = self.get_positioning(
            user_id=user_id, account_id=account_id, project_id=project_id,
            positioning_id=target_positioning_id,
        )
        draft = self.draft_positioning(
            user_id=user_id, account_id=account_id, project_id=project_id,
            positioning=target["positioning"], evidence_refs=target["evidence_refs"],
            rollback_of=target_positioning_id,
        )
        return self.approve_positioning(
            user_id=user_id, account_id=account_id, project_id=project_id,
            positioning_id=draft["id"],
        )

    def account_dna_projection(
        self, *, user_id: str, account_id: str, project_id: str,
    ) -> dict[str, Any] | None:
        with self.store._connect() as db:
            row = db.execute(
                """SELECT id FROM positioning_versions WHERE user_id=? AND account_id=?
                AND project_id=? AND status='approved'""", (user_id, account_id, project_id)
            ).fetchone()
        if row is None:
            return None
        version = self.get_positioning(
            user_id=user_id, account_id=account_id, project_id=project_id,
            positioning_id=row["id"],
        )
        data = version["positioning"]
        return {
            "persona": data["persona"],
            "tone": data["tone"],
            "audience": data.get("audience_summary", "以已确认目标受众假设为准"),
            "content_pillars": data["content_pillars"],
            "taboos": data["taboos"],
            "goals": [data["promise"]],
            "positioning_version_id": version["id"],
            "positioning_version": version["version"],
        }

    def add_audience_snapshot(
        self, *, user_id: str, account_id: str, project_id: str, platform: str,
        dimensions: dict[str, Any], provenance: dict[str, Any],
        window_start: str | None = None, window_end: str | None = None,
    ) -> dict[str, Any]:
        """Persist first-party audience facts; model/public inference is rejected."""
        self.get_project(user_id=user_id, account_id=account_id, project_id=project_id)
        source_kind = str(provenance.get("source_kind") or "")
        source_ref = str(provenance.get("source_ref") or "").strip()
        captured_at = str(provenance.get("captured_at") or "").strip()
        if source_kind not in ACTUAL_AUDIENCE_SOURCE_KINDS:
            raise ValueError("actual audience snapshots require official_api or creator_center_mcp")
        if not source_ref or not captured_at:
            raise ValueError("audience snapshot provenance requires source_ref and captured_at")
        unknown = sorted(set(dimensions) - ACTUAL_AUDIENCE_DIMENSIONS)
        if unknown:
            raise ValueError(f"unsupported actual audience dimensions: {unknown}")
        if not dimensions:
            raise ValueError("audience snapshot requires at least one dimension")
        for name, distribution in dimensions.items():
            if not isinstance(distribution, (dict, list)):
                raise ValueError(f"audience dimension {name} must be a distribution object or array")
        data_gaps = provenance.get("data_gaps", [])
        if not isinstance(data_gaps, list):
            raise ValueError("provenance.data_gaps must be an array")
        snapshot_id = _id("audience_snapshot")
        with self.store._connect() as db:
            db.execute(
                """INSERT INTO audience_snapshots
                (id,project_id,user_id,account_id,platform,dimensions_json,provenance_json,
                 window_start,window_end,captured_at,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (snapshot_id, project_id, user_id, account_id, platform, _json(dimensions),
                 _json(provenance), window_start, window_end, captured_at, _now()),
            )
        return self.get_audience_snapshot(
            user_id=user_id, account_id=account_id, project_id=project_id,
            snapshot_id=snapshot_id,
        )

    def get_audience_snapshot(
        self, *, user_id: str, account_id: str, project_id: str, snapshot_id: str,
    ) -> dict[str, Any]:
        with self.store._connect() as db:
            row = db.execute(
                """SELECT * FROM audience_snapshots WHERE id=? AND user_id=?
                AND account_id=? AND project_id=?""",
                (snapshot_id, user_id, account_id, project_id),
            ).fetchone()
        if row is None:
            raise KeyError("audience snapshot not found in account scope")
        result = dict(row)
        result["dimensions"] = json.loads(result.pop("dimensions_json"))
        result["provenance"] = json.loads(result.pop("provenance_json"))
        return result

    def list_audience_snapshots(
        self, *, user_id: str, account_id: str, project_id: str,
        platform: str | None = None, limit: int = 20,
    ) -> list[dict[str, Any]]:
        self.get_project(user_id=user_id, account_id=account_id, project_id=project_id)
        query = """SELECT id FROM audience_snapshots WHERE user_id=?
            AND account_id=? AND project_id=?"""
        args: list[Any] = [user_id, account_id, project_id]
        if platform:
            query += " AND platform=?"
            args.append(platform)
        query += " ORDER BY captured_at DESC LIMIT ?"
        args.append(max(1, min(int(limit), 100)))
        with self.store._connect() as db:
            rows = db.execute(query, args).fetchall()
        return [self.get_audience_snapshot(
            user_id=user_id, account_id=account_id, project_id=project_id,
            snapshot_id=row["id"],
        ) for row in rows]

    def create_experiment(
        self, *, user_id: str, account_id: str, project_id: str, hypothesis: str,
        variable: dict[str, Any], prediction: dict[str, Any],
        success_criteria: dict[str, Any],
    ) -> dict[str, Any]:
        self.get_project(user_id=user_id, account_id=account_id, project_id=project_id)
        if not hypothesis.strip():
            raise ValueError("experiment hypothesis is required")
        if not variable or not prediction or not success_criteria:
            raise ValueError("experiment requires variable, prediction and success_criteria")
        with self.store._connect() as db:
            positioning = db.execute(
                """SELECT id FROM positioning_versions WHERE project_id=? AND user_id=?
                AND account_id=? AND status='approved'""", (project_id, user_id, account_id)
            ).fetchone()
            if positioning is None:
                raise ValueError("an approved positioning is required before experiments")
            experiment_id = _id("experiment")
            timestamp = _now()
            db.execute(
                """INSERT INTO account_experiments
                (id,project_id,user_id,account_id,hypothesis,variable_json,asset_ids_json,
                 prediction_json,success_criteria_json,status,created_at,updated_at)
                VALUES (?,?,?,?,?,?,'[]',?,?,'draft',?,?)""",
                (experiment_id, project_id, user_id, account_id, hypothesis.strip(),
                 _json(variable), _json(prediction), _json(success_criteria), timestamp, timestamp),
            )
        return self.get_experiment(
            user_id=user_id, account_id=account_id, project_id=project_id,
            experiment_id=experiment_id,
        )

    def attach_experiment_asset(
        self, *, user_id: str, account_id: str, project_id: str,
        experiment_id: str, asset_id: str,
    ) -> dict[str, Any]:
        experiment = self.get_experiment(
            user_id=user_id, account_id=account_id, project_id=project_id,
            experiment_id=experiment_id,
        )
        asset = self.store.get_content_asset(asset_id)
        if asset.get("user_id") != user_id or asset.get("account_id") != account_id:
            raise ValueError("content asset is outside experiment account scope")
        if asset.get("experiment_id") and asset["experiment_id"] != experiment_id:
            raise ValueError("content asset already belongs to another experiment")
        asset_ids = list(experiment["asset_ids"])
        if asset_id not in asset_ids:
            asset_ids.append(asset_id)
        with self.store._connect() as db:
            db.execute(
                "UPDATE content_assets SET experiment_id=?,updated_at=? WHERE id=?",
                (experiment_id, _now(), asset_id),
            )
            db.execute(
                """UPDATE account_experiments SET asset_ids_json=?,status='running',updated_at=?
                WHERE id=? AND user_id=? AND account_id=? AND project_id=?""",
                (_json(asset_ids), _now(), experiment_id, user_id, account_id, project_id),
            )
        return self.get_experiment(
            user_id=user_id, account_id=account_id, project_id=project_id,
            experiment_id=experiment_id,
        )

    def transition_experiment(
        self, *, user_id: str, account_id: str, project_id: str,
        experiment_id: str, status: str,
    ) -> dict[str, Any]:
        if status not in EXPERIMENT_STATUSES:
            raise ValueError(f"unsupported experiment status: {status}")
        experiment = self.get_experiment(
            user_id=user_id, account_id=account_id, project_id=project_id,
            experiment_id=experiment_id,
        )
        allowed = {
            "draft": {"running", "cancelled"},
            "running": {"review_due", "cancelled"},
            "review_due": {"completed", "running"},
            "completed": set(), "cancelled": set(),
        }
        if status not in allowed[experiment["status"]]:
            raise ValueError(f"invalid experiment transition: {experiment['status']} -> {status}")
        with self.store._connect() as db:
            db.execute(
                """UPDATE account_experiments SET status=?,updated_at=? WHERE id=?
                AND user_id=? AND account_id=? AND project_id=?""",
                (status, _now(), experiment_id, user_id, account_id, project_id),
            )
        return self.get_experiment(
            user_id=user_id, account_id=account_id, project_id=project_id,
            experiment_id=experiment_id,
        )

    def get_experiment(
        self, *, user_id: str, account_id: str, project_id: str, experiment_id: str,
    ) -> dict[str, Any]:
        with self.store._connect() as db:
            row = db.execute(
                """SELECT * FROM account_experiments WHERE id=? AND user_id=?
                AND account_id=? AND project_id=?""",
                (experiment_id, user_id, account_id, project_id),
            ).fetchone()
        if row is None:
            raise KeyError("account experiment not found in account scope")
        result = dict(row)
        for key in ("variable", "asset_ids", "prediction", "success_criteria"):
            result[key] = json.loads(result.pop(f"{key}_json"))
        return result

    def experiment_timeline(
        self, *, user_id: str, account_id: str, project_id: str, experiment_id: str,
    ) -> dict[str, Any]:
        experiment = self.get_experiment(
            user_id=user_id, account_id=account_id, project_id=project_id,
            experiment_id=experiment_id,
        )
        assets = [self.store.get_content_asset(asset_id) for asset_id in experiment["asset_ids"]]
        asset_ids = set(experiment["asset_ids"])
        scores = [item for item in self.store.list_content_scores() if item["asset_id"] in asset_ids]
        predictions = [item for item in self.store.list_predictions() if item["asset_id"] in asset_ids]
        publishing = [
            item for item in self.store.list_publishing_tasks() if item["asset_id"] in asset_ids
        ]
        return {
            "experiment": experiment,
            "assets": assets,
            "scores": scores,
            "predictions": predictions,
            "publishing_tasks": publishing,
            "retrospectives": [item for item in predictions if item["status"] == "retro_completed"],
        }

    def list_experiments(
        self, *, user_id: str, account_id: str, project_id: str,
    ) -> list[dict[str, Any]]:
        with self.store._connect() as db:
            rows = db.execute(
                """SELECT id FROM account_experiments WHERE user_id=? AND account_id=?
                AND project_id=? ORDER BY created_at DESC""", (user_id, account_id, project_id)
            ).fetchall()
        return [self.get_experiment(
            user_id=user_id, account_id=account_id, project_id=project_id,
            experiment_id=row["id"],
        ) for row in rows]

    @staticmethod
    def _top_distribution_labels(value: Any, limit: int = 3) -> list[str]:
        if isinstance(value, dict):
            numeric = [
                (str(key), float(score)) for key, score in value.items()
                if isinstance(score, (int, float))
            ]
            if numeric:
                return [key for key, _ in sorted(numeric, key=lambda item: item[1], reverse=True)[:limit]]
            return [str(key) for key in list(value)[:limit]]
        if isinstance(value, list):
            labels = []
            for item in value:
                if isinstance(item, str):
                    labels.append(item)
                elif isinstance(item, dict):
                    label = item.get("label") or item.get("name") or item.get("item")
                    if label:
                        labels.append(str(label))
            return labels[:limit]
        return []

    def compare_audience_gap(
        self, *, user_id: str, account_id: str, project_id: str,
    ) -> dict[str, Any]:
        """Compare hypothesis, first-party snapshot and benchmark observations without filling gaps."""
        self.get_project(user_id=user_id, account_id=account_id, project_id=project_id)
        with self.store._connect() as db:
            audience_row = db.execute(
                """SELECT id FROM audience_hypotheses WHERE project_id=? AND user_id=?
                AND account_id=? AND status='confirmed'""", (project_id, user_id, account_id)
            ).fetchone()
            snapshot_row = db.execute(
                """SELECT id FROM audience_snapshots WHERE project_id=? AND user_id=?
                AND account_id=? ORDER BY captured_at DESC LIMIT 1""",
                (project_id, user_id, account_id),
            ).fetchone()
        target = None if audience_row is None else self._get_hypothesis(
            user_id, account_id, project_id, audience_row["id"]
        )
        actual = None if snapshot_row is None else self.get_audience_snapshot(
            user_id=user_id, account_id=account_id, project_id=project_id,
            snapshot_id=snapshot_row["id"],
        )
        benchmark_audience = [
            item for item in self.list_benchmark_observations(
                user_id=user_id, account_id=account_id, project_id=project_id,
            ) if item["dimension"] == "audience"
        ]

        target_dimensions: dict[str, Any] = {}
        for segment in (target or {}).get("segments", []):
            if not isinstance(segment, dict):
                continue
            dimensions = segment.get("dimensions")
            if isinstance(dimensions, dict):
                for key, value in dimensions.items():
                    target_dimensions.setdefault(key, value)
        actual_dimensions = (actual or {}).get("dimensions", {})
        benchmark_dimensions: dict[str, list[dict[str, Any]]] = {}
        for observation in benchmark_audience:
            dimensions = observation.get("value", {}).get("dimensions")
            if isinstance(dimensions, dict):
                for key, value in dimensions.items():
                    benchmark_dimensions.setdefault(key, []).append({
                        "value": value,
                        "observation_id": observation["id"],
                        "confidence": observation["confidence"],
                    })

        comparisons: dict[str, Any] = {}
        unknown: list[str] = []
        for dimension in sorted(set(target_dimensions) | set(actual_dimensions) | set(benchmark_dimensions)):
            target_top = self._top_distribution_labels(target_dimensions.get(dimension))
            actual_top = self._top_distribution_labels(actual_dimensions.get(dimension))
            benchmark_top = sorted({
                label for item in benchmark_dimensions.get(dimension, [])
                for label in self._top_distribution_labels(item["value"])
            })
            if not target_top or not actual_top:
                status = "unknown"
                unknown.append(dimension)
            else:
                overlap = set(target_top) & set(actual_top)
                if not overlap:
                    status = "mismatch_candidate"
                elif set(target_top) == set(actual_top):
                    status = "aligned"
                else:
                    status = "partial_overlap"
            comparisons[dimension] = {
                "status": status,
                "target_top": target_top,
                "actual_top": actual_top,
                "benchmark_top": benchmark_top,
                "benchmark_evidence_refs": [
                    item["observation_id"] for item in benchmark_dimensions.get(dimension, [])
                ],
            }

        return {
            "project_id": project_id,
            "target_audience_hypothesis": target,
            "actual_audience_snapshot": actual,
            "benchmark_audience_observations": benchmark_audience,
            "dimension_comparisons": comparisons,
            "unknown_dimensions": unknown,
            "interpretation": {
                "mismatch_is_fact": False,
                "note": "差距状态只用于提出实验，不会自动修改目标受众或账号定位",
            },
        }

    def create_strategy_candidate(
        self, *, user_id: str, account_id: str, project_id: str, trigger: str,
        proposal: dict[str, Any], evidence_refs: list[str], confidence: float,
    ) -> dict[str, Any]:
        self.get_project(user_id=user_id, account_id=account_id, project_id=project_id)
        if trigger not in STRATEGY_TRIGGERS:
            raise ValueError(f"unsupported strategy trigger: {trigger}")
        if not proposal or not str(proposal.get("type") or "").strip():
            raise ValueError("strategy proposal requires a type")
        if not evidence_refs:
            raise ValueError("strategy candidate requires evidence_refs")
        if not 0 <= confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        candidate_id = _id("strategy_candidate")
        with self.store._connect() as db:
            db.execute(
                """INSERT INTO strategy_candidates
                (id,project_id,user_id,account_id,trigger,proposal_json,evidence_refs_json,
                 confidence,status,created_at) VALUES (?,?,?,?,?,?,?,?, 'pending',?)""",
                (candidate_id, project_id, user_id, account_id, trigger, _json(proposal),
                 _json(evidence_refs), float(confidence), _now()),
            )
        return self.get_strategy_candidate(
            user_id=user_id, account_id=account_id, project_id=project_id,
            candidate_id=candidate_id,
        )

    def get_strategy_candidate(
        self, *, user_id: str, account_id: str, project_id: str, candidate_id: str,
    ) -> dict[str, Any]:
        with self.store._connect() as db:
            row = db.execute(
                """SELECT * FROM strategy_candidates WHERE id=? AND user_id=?
                AND account_id=? AND project_id=?""",
                (candidate_id, user_id, account_id, project_id),
            ).fetchone()
        if row is None:
            raise KeyError("strategy candidate not found in account scope")
        result = dict(row)
        result["proposal"] = json.loads(result.pop("proposal_json"))
        result["evidence_refs"] = json.loads(result.pop("evidence_refs_json"))
        return result

    def list_strategy_candidates(
        self, *, user_id: str, account_id: str, project_id: str,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        query = """SELECT id FROM strategy_candidates WHERE user_id=?
            AND account_id=? AND project_id=?"""
        args: list[Any] = [user_id, account_id, project_id]
        if status:
            query += " AND status=?"
            args.append(status)
        query += " ORDER BY created_at DESC"
        with self.store._connect() as db:
            rows = db.execute(query, args).fetchall()
        return [self.get_strategy_candidate(
            user_id=user_id, account_id=account_id, project_id=project_id,
            candidate_id=row["id"],
        ) for row in rows]

    @staticmethod
    def _weight_calibration_metric(adjustment: dict[str, Any]) -> dict[str, str]:
        component = str(adjustment.get("component") or "").strip()
        return {
            **DEFAULT_WEIGHT_CALIBRATION_METRIC,
            **WEIGHT_CALIBRATION_METRICS.get(component, {}),
        }

    def _existing_strategy_experiment(
        self, *, user_id: str, account_id: str, project_id: str, candidate_id: str,
    ) -> dict[str, Any] | None:
        for experiment in self.list_experiments(
            user_id=user_id, account_id=account_id, project_id=project_id,
        ):
            variable = experiment.get("variable") or {}
            if isinstance(variable, dict) and variable.get("source_strategy_candidate_id") == candidate_id:
                return experiment
        return None

    def _materialize_weight_calibration_experiment(
        self, *, user_id: str, account_id: str, project_id: str, candidate: dict[str, Any],
    ) -> dict[str, Any]:
        proposal = candidate.get("proposal") or {}
        if proposal.get("type") != "calibrate_influence_weight":
            return {
                "status": "skipped",
                "reason": "unsupported_strategy_proposal",
                "guardrail": "no experiment created for unsupported strategy proposal",
            }

        existing = self._existing_strategy_experiment(
            user_id=user_id, account_id=account_id, project_id=project_id,
            candidate_id=candidate["id"],
        )
        if existing is not None:
            return {
                "status": "exists",
                "experiment_id": existing["id"],
                "experiment": existing,
                "guardrail": "strategy candidate materialization is idempotent",
            }

        adjustment = proposal.get("proposed_adjustment")
        if not isinstance(adjustment, dict):
            adjustment = {}
        metric = self._weight_calibration_metric(adjustment)
        component = str(adjustment.get("component") or "unknown")
        direction = str(adjustment.get("direction") or "unknown")
        amount = adjustment.get("amount")
        rule_key = str(proposal.get("rule_key") or component)
        recommendation = str(proposal.get("recommendation") or "").strip()
        hypothesis = (
            f"验证策略候选 {rule_key}：围绕{metric['label']}做一条内容实验，"
            "判断该权重校准是否能被真实发布回执支持"
        )
        variable = {
            "type": "weight_calibration_experiment",
            "source": "accepted_strategy_candidate",
            "source_strategy_candidate_id": candidate["id"],
            "source_weight_candidate_id": proposal.get("source_weight_candidate_id"),
            "rule_key": rule_key,
            "component": component,
            "direction": direction,
            "amount": amount,
            "recommendation": recommendation,
            "test_design": {
                "control": "沿用当前账号 DNA、预演规则和内容判断方式",
                "variant": (
                    f"下一条内容预演时重点检验 {component} / {direction} 的影响，"
                    "用发布回执决定是否继续推进"
                ),
            },
            "guardrail": "draft experiment only; no durable strategy weight changed",
        }
        prediction = {
            "type": "weight_calibration_preflight",
            "primary_metric": metric["primary_metric"],
            "metric_label": metric["label"],
            "expected_direction": direction,
            "confidence": candidate.get("confidence"),
            "replay_summary": proposal.get("replay_summary") or {},
            "guardrail": (
                "prediction must be reconciled with a real publishing receipt "
                "before durable weight changes"
            ),
        }
        success_criteria = {
            "primary_metric": metric["primary_metric"],
            "accept_if": metric["accept_if"],
            "reject_if": "真实发布回执不支持该权重校准，或带来质量、信任、风险倒退",
            "minimum_evidence": "one_published_asset_receipt",
            "requires_blind_prediction": True,
            "source_strategy_candidate_id": candidate["id"],
        }
        try:
            experiment = self.create_experiment(
                user_id=user_id,
                account_id=account_id,
                project_id=project_id,
                hypothesis=hypothesis,
                variable=variable,
                prediction=prediction,
                success_criteria=success_criteria,
            )
        except ValueError as exc:
            if "approved positioning" not in str(exc):
                raise
            return {
                "status": "blocked",
                "reason": "approved_positioning_required",
                "message": "策略候选已接受，但账号定位未批准，暂不能生成内容实验草案",
                "guardrail": "strategy decision recorded; no experiment or durable weight changed",
            }
        return {
            "status": "created",
            "experiment_id": experiment["id"],
            "experiment": experiment,
            "guardrail": "accepted strategy candidate became a draft experiment only",
        }

    def decide_strategy_candidate(
        self, *, user_id: str, account_id: str, project_id: str,
        candidate_id: str, decision: str, reason: str,
    ) -> dict[str, Any]:
        if decision not in {"accepted", "rejected"}:
            raise ValueError("strategy decision must be accepted or rejected")
        current = self.get_strategy_candidate(
            user_id=user_id, account_id=account_id, project_id=project_id,
            candidate_id=candidate_id,
        )
        if current["status"] != "pending":
            raise ValueError("only pending strategy candidates can be decided")
        if decision == "rejected" and not reason.strip():
            raise ValueError("rejection reason is required for learning")
        with self.store._connect() as db:
            db.execute(
                """UPDATE strategy_candidates SET status=?,decision_reason=?,decided_at=?
                WHERE id=? AND user_id=? AND account_id=? AND project_id=? AND status='pending'""",
                (decision, reason.strip()[:1000], _now(), candidate_id, user_id, account_id, project_id),
            )
        result = self.get_strategy_candidate(
            user_id=user_id, account_id=account_id, project_id=project_id,
            candidate_id=candidate_id,
        )
        if decision == "accepted":
            materialization = self._materialize_weight_calibration_experiment(
                user_id=user_id, account_id=account_id, project_id=project_id,
                candidate=result,
            )
            if materialization["status"] != "skipped":
                result["materialization"] = materialization
                if materialization.get("experiment_id"):
                    result["experiment_id"] = materialization["experiment_id"]
        return result

    def confirm_audience_hypothesis(
        self, *, user_id: str, account_id: str, project_id: str, hypothesis_id: str,
    ) -> dict[str, Any]:
        self._get_hypothesis(user_id, account_id, project_id, hypothesis_id)
        timestamp = _now()
        with self.store._connect() as db:
            db.execute(
                """UPDATE audience_hypotheses SET status='superseded'
                WHERE project_id=? AND user_id=? AND account_id=? AND status='confirmed'""",
                (project_id, user_id, account_id),
            )
            changed = db.execute(
                """UPDATE audience_hypotheses SET status='confirmed', confirmed_at=?
                WHERE id=? AND project_id=? AND user_id=? AND account_id=? AND status='draft'""",
                (timestamp, hypothesis_id, project_id, user_id, account_id),
            )
            if changed.rowcount != 1:
                raise ValueError("only a draft audience hypothesis can be confirmed")
        self.read_status(user_id=user_id, account_id=account_id, project_id=project_id)
        return self._get_hypothesis(user_id, account_id, project_id, hypothesis_id)

    def _get_hypothesis(
        self, user_id: str, account_id: str, project_id: str, hypothesis_id: str,
    ) -> dict[str, Any]:
        with self.store._connect() as db:
            row = db.execute(
                """SELECT * FROM audience_hypotheses
                WHERE id=? AND project_id=? AND user_id=? AND account_id=?""",
                (hypothesis_id, project_id, user_id, account_id),
            ).fetchone()
        if row is None:
            raise KeyError("audience hypothesis not found in account scope")
        result = dict(row)
        for key in ("segments", "pains", "scenarios", "exclusions", "data_gaps"):
            result[key] = json.loads(result.pop(f"{key}_json"))
        return result

    def read_status(self, *, user_id: str, account_id: str, project_id: str) -> dict[str, Any]:
        project = self.get_project(user_id=user_id, account_id=account_id, project_id=project_id)
        with self.store._connect() as db:
            audience_row = db.execute(
                """SELECT id FROM audience_hypotheses WHERE project_id=? AND user_id=?
                AND account_id=? AND status='confirmed'""", (project_id, user_id, account_id)
            ).fetchone()
            benchmark_count = db.execute(
                """SELECT COUNT(*) FROM benchmark_accounts WHERE user_id=?
                AND target_account_id=? AND project_id=? AND selection_status='selected'""",
                (user_id, account_id, project_id)
            ).fetchone()[0]
            benchmark_observation_count = db.execute(
                """SELECT COUNT(*) FROM benchmark_observations WHERE user_id=?
                AND target_account_id=? AND project_id=?""", (user_id, account_id, project_id)
            ).fetchone()[0]
            positioning_row = db.execute(
                """SELECT positioning_json FROM positioning_versions WHERE project_id=?
                AND user_id=? AND account_id=? AND status='approved'""",
                (project_id, user_id, account_id),
            ).fetchone()
            experiment_count = db.execute(
                """SELECT COUNT(*) FROM account_experiments WHERE project_id=?
                AND user_id=? AND account_id=?""", (project_id, user_id, account_id)
            ).fetchone()[0]

        audience = None if audience_row is None else self._get_hypothesis(
            user_id, account_id, project_id, audience_row["id"]
        )
        positioning = None if positioning_row is None else json.loads(positioning_row[0])
        readiness = self.benchmark_readiness(
            user_id=user_id, account_id=account_id, project_id=project_id,
        )
        if audience is None:
            stage, next_action = "goal_defined", "draft_audience_hypothesis"
        elif benchmark_count == 0:
            stage, next_action = "audience_hypothesis_ready", "research_benchmark_accounts"
        elif not readiness["ready"]:
            stage, next_action = "audience_hypothesis_ready", "complete_benchmark_evidence"
        elif positioning is None:
            stage, next_action = "benchmark_evidence_ready", "draft_account_positioning"
        elif experiment_count == 0:
            stage, next_action = "positioning_approved", "propose_first_content_experiment"
        else:
            stage, next_action = "experiment_running", "collect_and_review_evidence"
        data_gaps = list(audience.get("data_gaps", [])) if audience else []
        if project["stage"] != stage:
            with self.store._connect() as db:
                db.execute(
                    """UPDATE account_strategy_projects SET stage=?,updated_at=?
                    WHERE id=? AND user_id=? AND account_id=?""",
                    (stage, _now(), project_id, user_id, account_id),
                )
        return LifecycleStatus(
            project_id, stage, next_action, audience, benchmark_count, benchmark_observation_count,
            readiness,
            positioning, experiment_count, data_gaps,
        ).to_dict()
