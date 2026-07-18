"""Durable daily topic-recommendation batches and delivery receipts."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

from agent.marketing.data_paths import MarketingDataPaths
from agent.marketing.domains.storage import MarketingDomainRepository


_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class TopicRecommendationRepository(MarketingDomainRepository):
    """Own preflight-backed topic batches; model prose is never the receipt."""

    def __init__(self, paths: MarketingDataPaths | None = None):
        super().__init__(paths)

    def start_batch(
        self,
        *,
        user_id: str,
        entity_id: str,
        account_id: str,
        as_of_date: str,
        source_session_id: str,
        target_platforms: list[str],
        input_summary: dict[str, Any],
    ) -> dict[str, Any]:
        date_value = _date(as_of_date)
        batch_id = _batch_id(user_id, entity_id, date_value)
        session = str(source_session_id or "").strip()[:200]
        if not session:
            raise ValueError("topic recommendation batch requires a source session")
        now = _now()
        with self._transaction() as db:
            existing = db.execute(
                "SELECT * FROM marketing_topic_recommendation_batches WHERE id=?",
                (batch_id,),
            ).fetchone()
            if existing is not None and existing["status"] == "completed":
                db.execute(
                    """INSERT INTO marketing_topic_recommendation_delivery_receipts
                    (source_session_id,batch_id,delivery_sha256,status,created_at)
                    VALUES (?,?,?,'prepared',?)
                    ON CONFLICT(source_session_id) DO UPDATE SET
                        batch_id=excluded.batch_id,
                        delivery_sha256=excluded.delivery_sha256,
                        status='prepared',validated_at=NULL""",
                    (session, batch_id, existing["delivery_sha256"], now),
                )
            else:
                db.execute(
                    """INSERT INTO marketing_topic_recommendation_batches
                    (id,user_id,entity_id,account_id,as_of_date,source_session_id,
                     target_platforms_json,input_json,status,created_at,updated_at)
                    VALUES (?,?,?,?,?,?,?,?, 'building',?,?)
                    ON CONFLICT(id) DO UPDATE SET
                        account_id=excluded.account_id,
                        source_session_id=excluded.source_session_id,
                        target_platforms_json=excluded.target_platforms_json,
                        input_json=excluded.input_json,
                        status='building',error='',updated_at=excluded.updated_at""",
                    (
                        batch_id,
                        user_id,
                        entity_id,
                        account_id,
                        date_value,
                        session,
                        _json(target_platforms),
                        _json(input_summary),
                        now,
                        now,
                    ),
                )
        # Open the read only after BEGIN IMMEDIATE has been released.
        return self.get(batch_id)

    def complete_batch(
        self,
        *,
        batch_id: str,
        candidates: list[dict[str, Any]],
        delivery_text: str,
    ) -> dict[str, Any]:
        delivery = str(delivery_text or "").strip()
        if not delivery:
            raise ValueError("topic recommendation delivery text is required")
        delivery_sha256 = hashlib.sha256(delivery.encode("utf-8")).hexdigest()
        now = _now()
        recommended = sum(
            1 for item in candidates if item.get("recommendation_eligible") is True
        )
        with self._transaction() as db:
            batch = db.execute(
                "SELECT * FROM marketing_topic_recommendation_batches WHERE id=?",
                (batch_id,),
            ).fetchone()
            if batch is None:
                raise KeyError("topic recommendation batch not found")
            db.execute(
                "DELETE FROM marketing_topic_recommendation_candidates WHERE batch_id=?",
                (batch_id,),
            )
            for item in candidates:
                rank = int(item["rank"])
                digest = hashlib.sha256(f"{batch_id}:{rank}".encode()).hexdigest()[:24]
                candidate_id = f"topic_candidate_{digest}"
                db.execute(
                    """INSERT INTO marketing_topic_recommendation_candidates
                    (id,batch_id,user_id,entity_id,account_id,rank,topic,angle,
                     plan_id,preflight_id,target_platforms_json,evidence_refs_json,
                     signal_refs_json,decision_status,recommendation_eligible,
                     influence_score,candidate_json,created_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        candidate_id,
                        batch_id,
                        batch["user_id"],
                        batch["entity_id"],
                        batch["account_id"],
                        rank,
                        str(item.get("topic") or "")[:500],
                        str(item.get("angle") or "")[:1000],
                        item["plan_id"],
                        item["preflight_id"],
                        _json(item.get("target_platforms") or []),
                        _json(item.get("evidence_refs") or []),
                        _json(item.get("signal_refs") or []),
                        str(item.get("decision_status") or "")[:120],
                        1 if item.get("recommendation_eligible") is True else 0,
                        float(item.get("influence_score") or 0),
                        _json(item),
                        now,
                    ),
                )
            updated = db.execute(
                """UPDATE marketing_topic_recommendation_batches
                SET status='completed',delivery_text=?,delivery_sha256=?,
                    recommended_count=?,research_only_count=?,error='',
                    completed_at=?,updated_at=? WHERE id=?""",
                (
                    delivery,
                    delivery_sha256,
                    recommended,
                    len(candidates) - recommended,
                    now,
                    now,
                    batch_id,
                ),
            ).rowcount
            if updated != 1:
                raise KeyError("topic recommendation batch disappeared")
            db.execute(
                """INSERT INTO marketing_topic_recommendation_delivery_receipts
                (source_session_id,batch_id,delivery_sha256,status,created_at)
                VALUES (?,?,?,'prepared',?)
                ON CONFLICT(source_session_id) DO UPDATE SET
                    batch_id=excluded.batch_id,
                    delivery_sha256=excluded.delivery_sha256,
                    status='prepared',validated_at=NULL""",
                (
                    str(batch["source_session_id"]),
                    batch_id,
                    delivery_sha256,
                    now,
                ),
            )
        return self.get(batch_id)

    def fail_batch(self, batch_id: str, error: str) -> None:
        with self._transaction() as db:
            db.execute(
                """UPDATE marketing_topic_recommendation_batches
                SET status='failed',error=?,updated_at=? WHERE id=? AND status!='completed'""",
                (str(error or "")[:1000], _now(), batch_id),
            )

    def get(self, batch_id: str) -> dict[str, Any]:
        with self._connection() as db:
            row = db.execute(
                "SELECT * FROM marketing_topic_recommendation_batches WHERE id=?",
                (batch_id,),
            ).fetchone()
            if row is None:
                raise KeyError("topic recommendation batch not found")
            candidates = db.execute(
                """SELECT * FROM marketing_topic_recommendation_candidates
                WHERE batch_id=? ORDER BY rank,id""",
                (batch_id,),
            ).fetchall()
        return _batch_record(row, candidates)

    def latest_for_session(self, source_session_id: str) -> dict[str, Any] | None:
        session = str(source_session_id or "").strip()
        if not session:
            return None
        with self._connection() as db:
            row = db.execute(
                """SELECT b.id FROM marketing_topic_recommendation_delivery_receipts r
                JOIN marketing_topic_recommendation_batches b ON b.id=r.batch_id
                WHERE r.source_session_id=? AND b.status='completed'
                  AND r.delivery_sha256=b.delivery_sha256
                ORDER BY r.created_at DESC,b.id DESC LIMIT 1""",
                (session,),
            ).fetchone()
        return self.get(str(row["id"])) if row is not None else None

    def latest_for_entity(
        self, *, user_id: str, entity_id: str
    ) -> dict[str, Any] | None:
        """Return the newest completed inbox batch for one operating entity."""

        user = str(user_id or "default").strip() or "default"
        entity = str(entity_id or "").strip()
        if not entity:
            raise ValueError("entity_id is required")
        with self._connection() as db:
            row = db.execute(
                """SELECT id FROM marketing_topic_recommendation_batches
                WHERE user_id=? AND entity_id=? AND status='completed'
                ORDER BY as_of_date DESC,completed_at DESC,id DESC LIMIT 1""",
                (user, entity),
            ).fetchone()
        return self.get(str(row["id"])) if row is not None else None

    def get_candidate(
        self, *, candidate_id: str, user_id: str, entity_id: str
    ) -> dict[str, Any]:
        """Read one completed recommendation without crossing entity scope."""

        candidate = str(candidate_id or "").strip()
        user = str(user_id or "default").strip() or "default"
        entity = str(entity_id or "").strip()
        if not candidate or not entity:
            raise ValueError("candidate_id and entity_id are required")
        with self._connection() as db:
            row = db.execute(
                """SELECT c.* FROM marketing_topic_recommendation_candidates c
                JOIN marketing_topic_recommendation_batches b ON b.id=c.batch_id
                WHERE c.id=? AND c.user_id=? AND c.entity_id=?
                  AND b.status='completed'""",
                (candidate, user, entity),
            ).fetchone()
        if row is None:
            raise KeyError("topic recommendation candidate not found")
        return _candidate_record(row)

    def validate_delivery(
        self, *, source_session_id: str, content: str
    ) -> dict[str, Any]:
        batch = self.latest_for_session(source_session_id)
        if batch is None:
            raise ValueError(
                "daily topic recommendation delivery requires a completed preflight batch"
            )
        supplied = str(content or "").strip()
        supplied_sha = hashlib.sha256(supplied.encode("utf-8")).hexdigest()
        if supplied_sha != batch["delivery_sha256"]:
            raise ValueError(
                "daily topic recommendation output differs from the preflight-approved delivery"
            )
        with self._transaction() as db:
            updated = db.execute(
                """UPDATE marketing_topic_recommendation_delivery_receipts
                SET status='validated',validated_at=?
                WHERE source_session_id=? AND batch_id=? AND delivery_sha256=?""",
                (
                    _now(),
                    str(source_session_id).strip(),
                    batch["id"],
                    batch["delivery_sha256"],
                ),
            ).rowcount
            if updated != 1:
                raise ValueError(
                    "daily topic recommendation delivery receipt disappeared"
                )
        return batch


def _batch_record(row, candidates) -> dict[str, Any]:
    value = dict(row)
    value["target_platforms"] = json.loads(value.pop("target_platforms_json") or "[]")
    value["input"] = json.loads(value.pop("input_json") or "{}")
    value["candidates"] = [_candidate_record(item) for item in candidates]
    value["recommendations"] = [
        item for item in value["candidates"] if item["recommendation_eligible"]
    ]
    return value


def _candidate_record(row) -> dict[str, Any]:
    value = dict(row)
    value["target_platforms"] = json.loads(value.pop("target_platforms_json") or "[]")
    value["evidence_refs"] = json.loads(value.pop("evidence_refs_json") or "[]")
    value["signal_refs"] = json.loads(value.pop("signal_refs_json") or "[]")
    value["candidate"] = json.loads(value.pop("candidate_json") or "{}")
    value["recommendation_eligible"] = bool(value["recommendation_eligible"])
    return value


def _batch_id(user_id: str, entity_id: str, as_of_date: str) -> str:
    digest = hashlib.sha256(
        f"{user_id}:{entity_id}:{as_of_date}".encode("utf-8")
    ).hexdigest()[:24]
    return f"topic_batch_{digest}"


def _date(value: str) -> str:
    text = str(value or "").strip()
    if not _DATE.fullmatch(text):
        raise ValueError("as_of_date must use YYYY-MM-DD")
    datetime.strptime(text, "%Y-%m-%d")
    return text


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
