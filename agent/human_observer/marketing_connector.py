"""One-way connector from immutable Marketing receipts into Human Observation.

Marketing contributes observations.  It cannot accept/reject theories, revise
the model, or write an interpretation back into the core through product APIs.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from .repository import SystemHumanObserver
from .theories import COLLECTIVE_MECHANISM_THEORY


class MarketingReceiptConnector:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.owner = SystemHumanObserver(self.db_path)

    def run(self, *, limit: int = 500) -> dict[str, Any]:
        rows = self._pending(limit=limit)
        ingested: list[str] = []
        quarantined: list[dict[str, str]] = []
        for row in rows:
            try:
                self._ingest(row)
                ingested.append(row["id"])
            except Exception as exc:
                quarantined.append({"receipt_id": row["id"], "reason": f"{type(exc).__name__}: {exc}"[:500]})
        return {
            "version": "marketing-human-observation-connector-v1",
            "pending_count": len(rows),
            "ingested_receipt_ids": ingested,
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
        return [{**dict(row), "summary": json.loads(row["summary_json"] or "{}")} for row in rows]

    def _ingest(self, receipt: dict[str, Any]) -> None:
        summary = receipt["summary"]
        source_sha = hashlib.sha256(
            json.dumps(summary, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        platform = str(receipt.get("platform") or "unknown")
        cohort_ref = self.owner.pseudonymous_ref(
            "cohort",
            f"marketing:{receipt.get('account_id') or 'unscoped'}:{platform}",
            namespace="human_research",
        )
        occurred_at = str(summary.get("observed_at") or receipt["created_at"])
        if receipt["receipt_type"] == "public_content_natural_experiment":
            observation = {
                "content": summary.get("content") or {},
                "metrics": summary.get("metrics") or {},
                "metric_delta": summary.get("metric_delta") or {},
                "causal_warning": summary.get("causal_warning") or "observational association only",
            }
            modality = "public_content_and_aggregate_feedback"
        else:
            observation = {
                "metrics": summary.get("metrics") or {},
                "social_reaction_observation": summary.get("social_reaction_observation") or {},
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

    def _interpret_public_model(self, receipt: dict[str, Any], event_id: str) -> list[dict[str, Any]]:
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
                ("maslow_hierarchy", "1.0", "need_projection", cluster.get("need_projection")),
                ("jungian_cognitive_functions", "1.0", "cognitive_projection", cluster.get("cognitive_projection")),
                ("existence_strategy", "0.1", "existence_strategy", cluster.get("existence_strategy")),
            )
            mechanism = str(cluster.get("collective_mechanism") or "unknown")
            dimensions += ((COLLECTIVE_MECHANISM_THEORY.get(mechanism, "emergent_norm"), "1.0", "collective_mechanism", mechanism),)
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
                        confidence=min(0.7, max(0.0, float(receipt["summary"].get("confidence") or 0.3))),
                        namespace="human_research",
                    )
                )
        return result
