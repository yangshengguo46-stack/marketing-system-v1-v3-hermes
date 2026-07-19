"""System-only write owner and read-only consumer for human observations."""

from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from agent.epistemic_contract import (
    EpistemicClass,
    SystemAuthority,
    require_system_authority,
)
from hermes_constants import get_hermes_home

from .theories import BUILTIN_THEORIES


_FORBIDDEN_KEYS = {
    "avatar", "contact", "email", "handle", "name", "nickname", "phone",
    "platform_account_id", "profile", "profile_url", "raw_comments", "real_name",
    "user_id", "username", "wechat", "weixin",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _id(prefix: str, key: str) -> str:
    return f"{prefix}_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:28]


def _bounded(value: Any, *, field: str, depth: int = 0) -> Any:
    if depth > 6:
        raise ValueError(f"{field} exceeds maximum depth")
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        if not math.isfinite(float(value)):
            raise ValueError(f"{field} contains non-finite number")
        return value
    if isinstance(value, str):
        return " ".join(value.split())[:12_000]
    if isinstance(value, list):
        if len(value) > 200:
            raise ValueError(f"{field} contains too many items")
        return [_bounded(item, field=f"{field}[]", depth=depth + 1) for item in value]
    if isinstance(value, dict):
        if len(value) > 120:
            raise ValueError(f"{field} contains too many fields")
        leaked = sorted(_FORBIDDEN_KEYS & {str(key).lower() for key in value})
        if leaked:
            raise ValueError(f"{field} contains direct identity fields: {', '.join(leaked)}")
        return {
            str(key)[:100]: _bounded(item, field=f"{field}.{key}", depth=depth + 1)
            for key, item in value.items()
        }
    raise ValueError(f"{field} contains unsupported value")


class _Storage:
    def __init__(self, db_path: str | Path | None = None, *, initialize: bool):
        configured = str(os.environ.get("HUMAN_OBSERVER_DB") or "").strip()
        self.db_path = Path(db_path or configured or (get_hermes_home() / "state.db")).expanduser()
        if initialize:
            from hermes_state import SessionDB

            owner = SessionDB(db_path=self.db_path)
            owner.close()

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.db_path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return db

    @contextmanager
    def _connection(self, *, write: bool = False) -> Iterator[sqlite3.Connection]:
        db = self._connect()
        try:
            if write:
                db.execute("BEGIN IMMEDIATE")
            yield db
            if write:
                db.commit()
        except Exception:
            if write:
                db.rollback()
            raise
        finally:
            db.close()


class HumanObserverReader(_Storage):
    """Read-only projection seam for products; it exposes no mutation methods."""

    def __init__(self, db_path: str | Path | None = None):
        super().__init__(db_path, initialize=False)

    def list_theories(self, *, status: str = "available") -> list[dict[str, Any]]:
        with self._connection() as db:
            rows = db.execute(
                "SELECT * FROM human_theories WHERE status=? ORDER BY family,theory_id,version",
                (status,),
            ).fetchall()
        return [_decode(row) for row in rows]

    def get_observation(self, event_id: str) -> dict[str, Any]:
        with self._connection() as db:
            row = db.execute("SELECT * FROM human_observation_events WHERE id=?", (event_id,)).fetchone()
        if row is None:
            raise KeyError("human observation not found")
        return _decode(row)

    def projection(self, *, namespace: str = "global", limit: int = 100) -> dict[str, Any]:
        with self._connection() as db:
            interpretations = db.execute(
                """SELECT * FROM human_interpretations
                WHERE namespace=? AND status IN ('candidate','supported','contested')
                ORDER BY created_at DESC,id DESC LIMIT ?""",
                (namespace, max(1, min(int(limit), 500))),
            ).fetchall()
            revisions = db.execute(
                """SELECT * FROM human_model_revisions WHERE status IN ('seed','candidate','active','contested')
                ORDER BY model_name,version DESC"""
            ).fetchall()
        return {
            "contract": "human-observer-read-projection-v1",
            "namespace": namespace,
            "interpretations": [_decode(row) for row in interpretations],
            "model_revisions": [_decode(row) for row in revisions],
            "authority": "read_only_no_product_writeback",
        }


class _HumanObserverWriter(HumanObserverReader):
    """Capability-gated writer; absent from package, RPC, tool, and UI APIs."""

    def __init__(
        self,
        db_path: str | Path | None = None,
        *,
        authority: SystemAuthority,
    ):
        require_system_authority(authority, EpistemicClass.HUMAN_RESEARCH)
        self._authority = authority
        _Storage.__init__(self, db_path, initialize=True)
        self._seed_registry()

    @staticmethod
    def pseudonymous_ref(kind: str, value: str, *, namespace: str = "global") -> str:
        if kind not in {"subject", "cohort"}:
            raise ValueError("pseudonymous ref kind must be subject or cohort")
        text = str(value or "").strip()
        if not text:
            raise ValueError("pseudonymous source value is required")
        return f"{kind}_" + hashlib.sha256(f"{namespace}\0{text}".encode()).hexdigest()[:32]

    def _seed_registry(self) -> None:
        created_at = _now()
        with self._connection(write=True) as db:
            for theory in BUILTIN_THEORIES:
                db.execute(
                    """INSERT OR IGNORE INTO human_theories
                    (theory_id,version,name,family,epistemic_status,constructs_json,
                     assumptions_json,falsification_json,source_refs_json,status,created_at)
                    VALUES (?,?,?,?,?,?,?,?,?,'available',?)""",
                    (
                        theory["theory_id"], theory["version"], theory["name"], theory["family"],
                        theory["epistemic_status"], _json(theory["constructs"]),
                        _json(theory["assumptions"]), _json(theory["falsification"]),
                        _json(theory["source_refs"]), created_at,
                    ),
                )
            db.execute(
                """INSERT OR IGNORE INTO human_model_revisions
                (id,model_name,version,parent_revision_id,ontology_json,theory_weights_json,
                 evidence_event_ids_json,counterevidence_event_ids_json,evaluation_json,status,created_at)
                VALUES (?,?,1,NULL,?,?,?,?,?,'seed',?)""",
                (
                    _id("modelrev", "human-existence-meta-model:1"),
                    "human_existence_meta_model",
                    _json({
                        "claim": "existence may be modeled through revisable, context-bound strategies",
                        "directly_observable": False,
                        "fixed_axiom": False,
                    }),
                    _json({"existence_strategy": 0.0}),
                    "[]", "[]",
                    _json({"status": "unvalidated_seed", "promotion_requires": "sealed_prediction_outcomes"}),
                    created_at,
                ),
            )

    def record_observation(
        self, *, event_key: str, source_kind: str, source_ref: str, modality: str,
        occurred_at: str, observed_at: str, observation: dict[str, Any],
        context: dict[str, Any], provenance: dict[str, Any], rights: dict[str, Any],
        namespace: str = "global", subject_ref: str | None = None,
        cohort_ref: str | None = None,
    ) -> dict[str, Any]:
        for label, value in (("event_key", event_key), ("source_kind", source_kind), ("source_ref", source_ref), ("modality", modality), ("occurred_at", occurred_at), ("observed_at", observed_at)):
            if not str(value or "").strip():
                raise ValueError(f"{label} is required")
        for ref, prefix in ((subject_ref, "subject_"), (cohort_ref, "cohort_")):
            if ref is not None and not str(ref).startswith(prefix):
                raise ValueError("only pseudonymous subject/cohort refs are accepted")
        clean_observation = _bounded(observation, field="observation")
        clean_context = _bounded(context, field="context")
        clean_provenance = _bounded(provenance, field="provenance")
        clean_rights = _bounded(rights, field="rights")
        if not isinstance(clean_provenance, dict) or not clean_provenance.get("collector"):
            raise ValueError("provenance.collector is required")
        if not isinstance(clean_rights, dict) or not clean_rights.get("basis") or not clean_rights.get("retention"):
            raise ValueError("rights.basis and rights.retention are required")
        digest = hashlib.sha256(_json({"context": clean_context, "observation": clean_observation}).encode()).hexdigest()
        event_id = _id("humanobs", f"{namespace}\0{event_key}")
        with self._connection(write=True) as db:
            existing = db.execute("SELECT * FROM human_observation_events WHERE event_key=?", (event_key,)).fetchone()
            if existing is not None:
                if existing["observation_sha256"] != digest:
                    raise ValueError("immutable observation event_key already exists with different payload")
                return _decode(existing)
            db.execute(
                """INSERT INTO human_observation_events
                (id,event_key,namespace,source_kind,source_ref,modality,subject_ref,cohort_ref,
                 occurred_at,observed_at,context_json,observation_json,provenance_json,rights_json,
                 observation_sha256,status,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'observed',?)""",
                (event_id,event_key,namespace,source_kind,source_ref,modality,subject_ref,cohort_ref,
                 occurred_at,observed_at,_json(clean_context),_json(clean_observation),
                 _json(clean_provenance),_json(clean_rights),digest,_now()),
            )
        return self.get_observation(event_id)

    def record_interpretation(
        self, *, interpretation_key: str, event_id: str, theory_id: str,
        theory_version: str, construct: str, claim: dict[str, Any],
        context_scope: dict[str, Any], support_event_ids: list[str] | None = None,
        counter_event_ids: list[str] | None = None, model_ref: str = "",
        confidence: float = 0.3, namespace: str = "global",
    ) -> dict[str, Any]:
        confidence = float(confidence)
        if not 0 <= confidence <= 0.7:
            raise ValueError("interpretation confidence must be between 0 and 0.7")
        clean_claim = _bounded(claim, field="claim")
        clean_scope = _bounded(context_scope, field="context_scope")
        interpretation_id = _id("humanint", interpretation_key)
        with self._connection(write=True) as db:
            if db.execute("SELECT 1 FROM human_theories WHERE theory_id=? AND version=? AND status='available'", (theory_id, theory_version)).fetchone() is None:
                raise KeyError("theory version is not available")
            db.execute(
                """INSERT OR IGNORE INTO human_interpretations
                (id,interpretation_key,namespace,event_id,theory_id,theory_version,construct,
                 claim_json,context_scope_json,support_event_ids_json,counter_event_ids_json,
                 model_ref,confidence,status,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,'candidate',?)""",
                (interpretation_id,interpretation_key,namespace,event_id,theory_id,theory_version,
                 str(construct)[:120],_json(clean_claim),_json(clean_scope),
                 _json(support_event_ids or [event_id]),_json(counter_event_ids or []),
                 str(model_ref)[:240],round(confidence,4),_now()),
            )
            row = db.execute("SELECT * FROM human_interpretations WHERE interpretation_key=?", (interpretation_key,)).fetchone()
        return _decode(row)

    def upsert_graph_node(
        self, *, node_type: str, stable_ref: str, attributes: dict[str, Any],
        evidence_event_ids: list[str], valid_from: str, valid_to: str | None = None,
        namespace: str = "global",
    ) -> dict[str, Any]:
        node_id = _id("humannode", f"{namespace}\0{node_type}\0{stable_ref}")
        now = _now()
        with self._connection(write=True) as db:
            db.execute(
                """INSERT INTO human_graph_nodes
                (id,namespace,node_type,stable_ref,attributes_json,evidence_event_ids_json,
                 valid_from,valid_to,status,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,'active',?,?)
                ON CONFLICT(namespace,node_type,stable_ref) DO UPDATE SET
                  attributes_json=excluded.attributes_json,
                  evidence_event_ids_json=excluded.evidence_event_ids_json,
                  valid_to=excluded.valid_to,updated_at=excluded.updated_at""",
                (node_id,namespace,node_type,stable_ref,_json(_bounded(attributes,field="attributes")),
                 _json(evidence_event_ids),valid_from,valid_to,now,now),
            )
            row = db.execute("SELECT * FROM human_graph_nodes WHERE id=?", (node_id,)).fetchone()
        return _decode(row)

    def record_graph_edge(
        self, *, source_node_id: str, target_node_id: str, relation: str,
        context: dict[str, Any], evidence_event_ids: list[str], confidence: float,
        valid_from: str, valid_to: str | None = None, namespace: str = "global",
    ) -> dict[str, Any]:
        confidence = float(confidence)
        if not 0 <= confidence <= 1:
            raise ValueError("graph edge confidence must be between 0 and 1")
        key = _json([namespace,source_node_id,target_node_id,relation,valid_from,evidence_event_ids])
        edge_id = _id("humanedge", key)
        now = _now()
        with self._connection(write=True) as db:
            db.execute(
                """INSERT OR IGNORE INTO human_graph_edges
                (id,namespace,source_node_id,target_node_id,relation,context_json,
                 evidence_event_ids_json,confidence,valid_from,valid_to,status,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,'candidate',?,?)""",
                (edge_id,namespace,source_node_id,target_node_id,str(relation)[:160],
                 _json(_bounded(context,field="edge_context")),_json(evidence_event_ids),
                 round(confidence,4),valid_from,valid_to,now,now),
            )
            row = db.execute("SELECT * FROM human_graph_edges WHERE id=?", (edge_id,)).fetchone()
        return _decode(row)

    def propose_hypothesis(
        self, *, hypothesis_key: str, theory_id: str, theory_version: str,
        scope: dict[str, Any], statement: dict[str, Any], evidence_for: list[str],
        evidence_against: list[str], sample_count: int, context_count: int,
        confidence: float, namespace: str = "global", supersedes_id: str | None = None,
    ) -> dict[str, Any]:
        confidence = float(confidence)
        if not 0 <= confidence <= 0.7:
            raise ValueError("hypothesis confidence must be between 0 and 0.7")
        hypothesis_id = _id("humanhyp", hypothesis_key)
        now = _now()
        with self._connection(write=True) as db:
            if db.execute("SELECT 1 FROM human_theories WHERE theory_id=? AND version=?", (theory_id,theory_version)).fetchone() is None:
                raise KeyError("theory version not found")
            db.execute(
                """INSERT OR IGNORE INTO human_hypotheses
                (id,hypothesis_key,namespace,theory_id,theory_version,scope_json,statement_json,
                 evidence_for_json,evidence_against_json,sample_count,context_count,confidence,
                 status,version,supersedes_id,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?, 'candidate',1,?,?,?)""",
                (hypothesis_id,hypothesis_key,namespace,theory_id,theory_version,
                 _json(_bounded(scope,field="scope")),_json(_bounded(statement,field="statement")),
                 _json(evidence_for),_json(evidence_against),int(sample_count),int(context_count),
                 round(confidence,4),supersedes_id,now,now),
            )
            row = db.execute("SELECT * FROM human_hypotheses WHERE hypothesis_key=?", (hypothesis_key,)).fetchone()
        return _decode(row)

    def propose_model_revision(
        self, *, model_name: str, ontology: dict[str, Any], theory_weights: dict[str, Any],
        evidence_event_ids: list[str], counterevidence_event_ids: list[str],
        evaluation: dict[str, Any], parent_revision_id: str | None = None,
    ) -> dict[str, Any]:
        with self._connection(write=True) as db:
            row = db.execute("SELECT COALESCE(MAX(version),0)+1 AS version FROM human_model_revisions WHERE model_name=?", (model_name,)).fetchone()
            version = int(row["version"])
            revision_id = _id("modelrev", f"{model_name}:{version}")
            db.execute(
                """INSERT INTO human_model_revisions
                (id,model_name,version,parent_revision_id,ontology_json,theory_weights_json,
                 evidence_event_ids_json,counterevidence_event_ids_json,evaluation_json,status,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,'candidate',?)""",
                (revision_id,model_name,version,parent_revision_id,
                 _json(_bounded(ontology,field="ontology")),
                 _json(_bounded(theory_weights,field="theory_weights")),
                 _json(evidence_event_ids),_json(counterevidence_event_ids),
                 _json(_bounded(evaluation,field="evaluation")),_now()),
            )
            result = db.execute("SELECT * FROM human_model_revisions WHERE id=?", (revision_id,)).fetchone()
        return _decode(result)

    def seal_prediction(self, *, prediction_key: str, target: dict[str, Any], prediction: dict[str, Any], due_at: str, evidence_event_ids: list[str], hypothesis_id: str | None = None, namespace: str = "global") -> dict[str, Any]:
        prediction_id = _id("humanpred", prediction_key)
        with self._connection(write=True) as db:
            db.execute(
                """INSERT OR IGNORE INTO human_predictions
                (id,prediction_key,namespace,hypothesis_id,target_json,prediction_json,
                 evidence_event_ids_json,due_at,status,created_at)
                VALUES (?,?,?,?,?,?,?,?,'sealed',?)""",
                (prediction_id,prediction_key,namespace,hypothesis_id,_json(_bounded(target,field="target")),
                 _json(_bounded(prediction,field="prediction")),_json(evidence_event_ids),due_at,_now()),
            )
            row = db.execute("SELECT * FROM human_predictions WHERE prediction_key=?", (prediction_key,)).fetchone()
        return _decode(row)

    def settle_prediction(self, *, prediction_id: str, observation_event_id: str, outcome: dict[str, Any], evaluation: dict[str, Any]) -> dict[str, Any]:
        with self._connection(write=True) as db:
            prediction = db.execute("SELECT * FROM human_predictions WHERE id=?", (prediction_id,)).fetchone()
            if prediction is None:
                raise KeyError("prediction not found")
            outcome_id = _id("humanoutcome", prediction_id)
            db.execute(
                """INSERT OR IGNORE INTO human_prediction_outcomes
                (id,prediction_id,observation_event_id,outcome_json,evaluation_json,settled_at,created_at)
                VALUES (?,?,?,?,?,?,?)""",
                (outcome_id,prediction_id,observation_event_id,_json(_bounded(outcome,field="outcome")),
                 _json(_bounded(evaluation,field="evaluation")),_now(),_now()),
            )
            db.execute("UPDATE human_predictions SET status='settled' WHERE id=?", (prediction_id,))
            row = db.execute("SELECT * FROM human_prediction_outcomes WHERE prediction_id=?", (prediction_id,)).fetchone()
        return _decode(row)

    def record_ingestion(self, *, source_kind: str, source_ref: str, event_ids: list[str], interpretation_ids: list[str], source_sha256: str) -> None:
        with self._connection(write=True) as db:
            db.execute(
                """INSERT OR IGNORE INTO human_source_ingestions
                (source_kind,source_ref,event_ids_json,interpretation_ids_json,source_sha256,status,created_at)
                VALUES (?,?,?,?,?,'ingested',?)""",
                (source_kind,source_ref,_json(event_ids),_json(interpretation_ids),source_sha256,_now()),
            )


def _decode(row: sqlite3.Row) -> dict[str, Any]:
    value = dict(row)
    for key in list(value):
        if key.endswith("_json"):
            value[key[:-5]] = json.loads(value.pop(key) or "null")
    return value
