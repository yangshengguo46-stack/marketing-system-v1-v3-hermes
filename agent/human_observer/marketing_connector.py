"""One-way connector from immutable Marketing receipts into Human Observation.

Marketing contributes observations.  It cannot accept/reject theories, revise
the model, or write an interpretation back into the core through product APIs.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from agent.epistemic_contract import (
    EpistemicClass,
    SystemAuthority,
    require_system_authority,
)

from .repository import _HumanObserverWriter
from .theories import COLLECTIVE_MECHANISM_THEORY


class MarketingReceiptConnector:
    def __init__(self, db_path: str | Path, *, authority: SystemAuthority):
        require_system_authority(authority, EpistemicClass.HUMAN_RESEARCH)
        self.db_path = Path(db_path)
        self.owner = _HumanObserverWriter(self.db_path, authority=authority)

    def run(self, *, limit: int = 500) -> dict[str, Any]:
        rows = self._pending(limit=limit)
        ingested: list[str] = []
        event_ids: list[str] = []
        quarantined: list[dict[str, str]] = []
        for row in rows:
            try:
                event = self._ingest(row)
                ingested.append(row["id"])
                event_ids.append(event["id"])
            except Exception as exc:
                quarantined.append({
                    "receipt_id": row["id"],
                    "reason": f"{type(exc).__name__}: {exc}"[:500],
                })
        return {
            "version": "marketing-human-observation-connector-v1",
            "pending_count": len(rows),
            "ingested_receipt_ids": ingested,
            "ingested_event_ids": event_ids,
            "quarantined": quarantined,
            "authority": "one_way_observation_only",
        }

    def _pending(self, *, limit: int) -> list[dict[str, Any]]:
        db = sqlite3.connect(self.db_path)
        db.row_factory = sqlite3.Row
        try:
            rows = db.execute(
                """SELECT r.* FROM marketing_receipt_refs r
                LEFT JOIN human_source_ingestions h
                  ON h.source_kind='marketing_receipt' AND h.source_ref=r.id
                WHERE h.source_ref IS NULL
                  AND r.receipt_type IN ('public_content_natural_experiment','metric_checkpoint_observed')
                ORDER BY r.created_at,r.id LIMIT ?""",
                (max(1, min(int(limit), 2000)),),
            ).fetchall()
        finally:
            db.close()
        return [
            {**dict(row), "summary": json.loads(row["summary_json"] or "{}")}
            for row in rows
        ]

    def _ingest(self, receipt: dict[str, Any]) -> dict[str, Any]:
        summary = receipt["summary"]
        source_sha = hashlib.sha256(
            json.dumps(
                summary, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()
        platform = str(receipt.get("platform") or "unknown")
        cohort_ref = self.owner.pseudonymous_ref(
            "cohort",
            f"marketing:{receipt.get('account_id') or 'unscoped'}:{platform}",
            namespace="human_research",
        )
        subject_ref = self.owner.pseudonymous_ref(
            "subject",
            f"marketing-user:{receipt.get('user_id') or 'unscoped'}",
            namespace="human_research",
        )
        occurred_at = str(summary.get("observed_at") or receipt["created_at"])
        if receipt["receipt_type"] == "public_content_natural_experiment":
            observation = {
                "content": summary.get("content") or {},
                "metrics": summary.get("metrics") or {},
                "metric_delta": summary.get("metric_delta") or {},
                "causal_warning": summary.get("causal_warning")
                or "observational association only",
            }
            modality = "public_content_and_aggregate_feedback"
        else:
            observation = {
                "metrics": summary.get("metrics") or {},
                "social_reaction_observation": summary.get(
                    "social_reaction_observation"
                )
                or {},
                "verification_source": summary.get("verification_source") or "",
            }
            modality = "published_content_aggregate_outcome"
        event = self.owner.record_observation(
            event_key=f"marketing_receipt:{receipt['id']}",
            source_kind="marketing_receipt",
            source_ref=receipt["id"],
            modality=modality,
            occurred_at=occurred_at,
            observed_at=receipt["created_at"],
            observation=observation,
            context={
                "domain": "marketing",
                "platform": platform,
                "receipt_type": receipt["receipt_type"],
                "scope": "anonymous_aggregate",
            },
            provenance={
                "collector": "marketing_receipt_connector",
                "receipt_type": receipt["receipt_type"],
                "source_kind": receipt["source_kind"],
                "source_ref": receipt["source_id"],
                "claim_truth_verified": False,
            },
            rights={
                "basis": "product_operational_observation",
                "retention": "follow_source_and_data_subject_policy",
                "withdrawal_supported": True,
                "use_scope": "research_and_read_only_product_projection",
            },
            namespace="human_research",
            subject_ref=subject_ref,
            cohort_ref=cohort_ref,
        )
        interpretations = self._interpret_public_model(receipt, event["id"])
        self.owner.record_ingestion(
            source_kind="marketing_receipt",
            source_ref=receipt["id"],
            event_ids=[event["id"]],
            interpretation_ids=[item["id"] for item in interpretations],
            source_sha256=source_sha,
        )
        return event

    def _interpret_public_model(
        self, receipt: dict[str, Any], event_id: str
    ) -> list[dict[str, Any]]:
        if receipt["receipt_type"] != "public_content_natural_experiment":
            return []
        model = receipt["summary"].get("model_observation") or {}
        reaction = model.get("reaction") if isinstance(model, dict) else {}
        clusters = reaction.get("clusters") if isinstance(reaction, dict) else []
        result: list[dict[str, Any]] = []
        for index, cluster in enumerate(clusters or []):
            if not isinstance(cluster, dict):
                continue
            dimensions = (
                (
                    "maslow_hierarchy",
                    "1.0",
                    "need_projection",
                    cluster.get("need_projection"),
                ),
                (
                    "jungian_cognitive_functions",
                    "1.0",
                    "cognitive_projection",
                    cluster.get("cognitive_projection"),
                ),
                (
                    "existence_strategy",
                    "0.1",
                    "existence_strategy",
                    cluster.get("existence_strategy"),
                ),
            )
            mechanism = str(cluster.get("collective_mechanism") or "unknown")
            dimensions += (
                (
                    COLLECTIVE_MECHANISM_THEORY.get(mechanism, "emergent_norm"),
                    "1.0",
                    "collective_mechanism",
                    mechanism,
                ),
            )
            for theory_id, version, construct, value in dimensions:
                if value in {None, "", "unknown"}:
                    continue
                result.append(
                    self.owner.record_interpretation(
                        interpretation_key=f"marketing:{receipt['id']}:{index}:{construct}",
                        event_id=event_id,
                        theory_id=theory_id,
                        theory_version=version,
                        construct=construct,
                        claim={
                            "projected_value": value,
                            "stance": cluster.get("stance") or "",
                            "themes": cluster.get("themes") or [],
                            "count": cluster.get("count") or 0,
                            "not_direct_observation": True,
                        },
                        context_scope={
                            "domain": "marketing",
                            "platform": receipt.get("platform") or "unknown",
                            "anonymous_cohort": True,
                        },
                        model_ref=str(receipt["summary"].get("version") or ""),
                        confidence=min(
                            0.7,
                            max(
                                0.0, float(receipt["summary"].get("confidence") or 0.3)
                            ),
                        ),
                        namespace="human_research",
                    )
                )
        return result


_DIRECT_IDENTITY_KEYS = {
    "avatar",
    "contact",
    "email",
    "handle",
    "name",
    "nickname",
    "phone",
    "platform_account_id",
    "profile",
    "profile_url",
    "raw_comments",
    "real_name",
    "source_refs",
    "basis_refs",
    "evidence_refs",
    "user_id",
    "account_id",
    "entity_id",
    "project_id",
    "username",
    "wechat",
    "weixin",
}
_RESEARCH_EXCLUDED_KEYS = {
    "human_projection_model",
    "need_projection_hypotheses",
    "cognitive_projection_hypotheses",
    "cognitive_style_hypotheses",
    "existence_strategy_hypotheses",
    "existence_hypotheses",
    "collective_projection_hypotheses",
}
_EMAIL = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_PHONE = re.compile(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)")
_URL = re.compile(r"(?i)\b(?:https?://|www\.)\S+")


def _research_safe_choice(value: Any, *, depth: int = 0) -> Any:
    """Minimise an operational choice before it crosses into research storage."""

    if depth > 6:
        return "[depth_limited]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        text = " ".join(value.split())[:4_000]
        text = _EMAIL.sub("[email_redacted]", text)
        text = _PHONE.sub("[phone_redacted]", text)
        return _URL.sub("[external_reference_redacted]", text)
    if isinstance(value, list):
        return [_research_safe_choice(item, depth=depth + 1) for item in value[:100]]
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for raw_key, item in list(value.items())[:100]:
            key = str(raw_key)[:100]
            normalized = key.lower()
            if (
                normalized in _DIRECT_IDENTITY_KEYS
                or normalized in _RESEARCH_EXCLUDED_KEYS
                or normalized.endswith("_id")
                or normalized.endswith((
                    "_name",
                    "_email",
                    "_phone",
                    "_handle",
                    "_username",
                    "_url",
                ))
            ):
                continue
            result[key] = _research_safe_choice(item, depth=depth + 1)
        return result
    return str(value)[:400]


_PERSONAL_IP_SOURCES: tuple[dict[str, Any], ...] = (
    {
        "table": "creator_operating_profiles",
        "kind": "creator_operating_profile",
        "marker": "confirmed_at",
        "epistemic_class": EpistemicClass.USER_SELF_REPORT.value,
        "json_columns": ("profile_json",),
    },
    {
        "table": "market_route_hypotheses",
        "kind": "market_route",
        "marker": "selected_at",
        "epistemic_class": EpistemicClass.STRATEGIC_CHOICE.value,
        "json_columns": ("route_json",),
    },
    {
        "table": "audience_hypotheses",
        "kind": "audience_hypothesis",
        "marker": "confirmed_at",
        "epistemic_class": EpistemicClass.STRATEGIC_CHOICE.value,
        "json_columns": (
            "segments_json",
            "pains_json",
            "scenarios_json",
            "jobs_json",
            "current_alternatives_json",
            "trust_barriers_json",
            "desired_outcomes_json",
            "behavior_signals_json",
            "exclusions_json",
        ),
    },
    {
        "table": "positioning_versions",
        "kind": "positioning",
        "marker": "approved_at",
        "epistemic_class": EpistemicClass.STRATEGIC_CHOICE.value,
        "json_columns": ("positioning_json",),
    },
    {
        "table": "content_system_versions",
        "kind": "content_system",
        "marker": "approved_at",
        "epistemic_class": EpistemicClass.STRATEGIC_CHOICE.value,
        "json_columns": ("system_json",),
    },
    {
        "table": "account_experiments",
        "kind": "account_experiment",
        "marker": "approved_at",
        "epistemic_class": EpistemicClass.STRATEGIC_CHOICE.value,
        "plain_columns": ("hypothesis",),
        "json_columns": (
            "variable_json",
            "variants_json",
            "prediction_json",
            "success_criteria_json",
        ),
    },
)


class MarketingPersonalIPConnector:
    """Observe confirmed creator self-reports and choices without governing them.

    This seam is deliberately one-way. It does not expose a product API, create
    psychological interpretations, or let a conversation revise research state.
    A confirmed choice is evidence that the subject made the choice—not evidence
    that the choice, or any story inferred from it, is objectively true.
    """

    SOURCE_KIND = "marketing_personal_ip_choice"

    def __init__(self, db_path: str | Path, *, authority: SystemAuthority):
        require_system_authority(authority, EpistemicClass.HUMAN_RESEARCH)
        self.db_path = Path(db_path)
        self.owner = _HumanObserverWriter(self.db_path, authority=authority)

    @staticmethod
    def _source_ref(table: str, artifact_id: str) -> str:
        digest = hashlib.sha256(f"{table}\0{artifact_id}".encode()).hexdigest()[:32]
        return f"choice_{digest}"

    def run(self, *, limit: int = 500) -> dict[str, Any]:
        rows = self._pending(limit=limit)
        ingested_refs: list[str] = []
        event_ids: list[str] = []
        quarantined: list[dict[str, str]] = []
        for item in rows:
            source_ref = self._source_ref(item["spec"]["table"], str(item["row"]["id"]))
            try:
                event = self._ingest(item["spec"], item["row"], source_ref=source_ref)
                ingested_refs.append(source_ref)
                event_ids.append(event["id"])
            except Exception as exc:
                quarantined.append({
                    "source_ref": source_ref,
                    "reason": f"{type(exc).__name__}: {exc}"[:500],
                })
        return {
            "version": "marketing-personal-ip-observer-v1",
            "pending_count": len(rows),
            "ingested_source_refs": ingested_refs,
            "ingested_event_ids": event_ids,
            "quarantined": quarantined,
            "authority": "one_way_observation_only",
            "auto_interpretation": False,
        }

    def _pending(self, *, limit: int) -> list[dict[str, Any]]:
        db = sqlite3.connect(self.db_path)
        db.row_factory = sqlite3.Row
        try:
            existing = {
                str(row["source_ref"])
                for row in db.execute(
                    "SELECT source_ref FROM human_source_ingestions WHERE source_kind=?",
                    (self.SOURCE_KIND,),
                ).fetchall()
            }
            pending: list[dict[str, Any]] = []
            tables = {
                str(row["name"])
                for row in db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            for spec in _PERSONAL_IP_SOURCES:
                table = str(spec["table"])
                if table not in tables:
                    continue
                columns = {
                    str(row["name"])
                    for row in db.execute(f"PRAGMA table_info({table})").fetchall()
                }
                required = {"id", "user_id", "status", str(spec["marker"])}
                required.update(spec.get("plain_columns") or ())
                required.update(spec.get("json_columns") or ())
                if not required.issubset(columns):
                    continue
                rows = db.execute(
                    f"SELECT * FROM {table} WHERE {spec['marker']} IS NOT NULL "
                    f"AND {spec['marker']}<>'' "
                    f"ORDER BY {spec['marker']},id"
                ).fetchall()
                for row in rows:
                    source_ref = self._source_ref(table, str(row["id"]))
                    if source_ref not in existing:
                        pending.append({"spec": spec, "row": dict(row)})
            pending.sort(
                key=lambda item: (
                    str(item["row"].get(item["spec"]["marker"]) or ""),
                    str(item["spec"]["table"]),
                    str(item["row"].get("id") or ""),
                )
            )
            return pending[: max(1, min(int(limit), 2_000))]
        finally:
            db.close()

    def _payload(self, spec: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        semantic_keys = {
            "profile_json": "creator_operating_profile",
            "route_json": "market_route",
            "positioning_json": "positioning_choice",
            "system_json": "content_system_choice",
        }
        for column in spec.get("plain_columns") or ():
            payload[str(column).removesuffix("_json")] = row.get(column)
        for column in spec.get("json_columns") or ():
            key = semantic_keys.get(str(column), str(column).removesuffix("_json"))
            raw = row.get(column)
            try:
                payload[key] = json.loads(raw or "null")
            except (TypeError, json.JSONDecodeError):
                payload[key] = "[invalid_source_json]"
        return _research_safe_choice(payload)

    def _ingest(
        self,
        spec: dict[str, Any],
        row: dict[str, Any],
        *,
        source_ref: str,
    ) -> dict[str, Any]:
        payload = self._payload(spec, row)
        source_sha = hashlib.sha256(
            json.dumps(
                payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()
        subject_ref = self.owner.pseudonymous_ref(
            "subject",
            f"marketing-user:{row.get('user_id') or 'unscoped'}",
            namespace="human_research",
        )
        project_scope_ref = hashlib.sha256(
            f"{row.get('project_id') or ''}\0{row.get('entity_id') or ''}\0{row.get('account_id') or ''}".encode()
        ).hexdigest()[:24]
        observed_at = str(row.get(spec["marker"]) or row.get("created_at") or "")
        event = self.owner.record_observation(
            event_key=f"marketing_personal_ip:{source_ref}",
            source_kind=self.SOURCE_KIND,
            source_ref=source_ref,
            modality="confirmed_self_report_or_operating_choice",
            occurred_at=observed_at,
            observed_at=observed_at,
            observation={
                "event": "personal_ip_choice_confirmed",
                "artifact_kind": spec["kind"],
                "epistemic_class": spec["epistemic_class"],
                "choice": payload,
                "version": int(row.get("version") or 1),
                "status_at_observation": str(row.get("status") or ""),
                "not_objective_fact": True,
                "not_psychological_interpretation": True,
            },
            context={
                "domain": "marketing_personal_ip",
                "operating_scope_ref": project_scope_ref,
                "artifact_kind": spec["kind"],
                "epistemic_class": spec["epistemic_class"],
            },
            provenance={
                "collector": "marketing_personal_ip_connector",
                "source_table": spec["table"],
                "source_status": str(row.get("status") or ""),
                "claim_truth_verified": False,
            },
            rights={
                "basis": "product_operational_observation",
                "retention": "follow_source_and_data_subject_policy",
                "withdrawal_supported": True,
                "use_scope": "research_and_read_only_product_projection",
            },
            namespace="human_research",
            subject_ref=subject_ref,
        )
        self.owner.record_ingestion(
            source_kind=self.SOURCE_KIND,
            source_ref=source_ref,
            event_ids=[event["id"]],
            interpretation_ids=[],
            source_sha256=source_sha,
        )
        return event
