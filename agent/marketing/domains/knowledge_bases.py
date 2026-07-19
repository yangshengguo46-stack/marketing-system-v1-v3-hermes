"""Four governed knowledge bases: platform, market, account, and content."""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from agent.epistemic_contract import (
    EpistemicClass,
    SystemAuthority,
    require_system_authority,
)
from agent.marketing.data_paths import MarketingDataPaths
from agent.marketing.domains.article_drafts import ARTICLE_STYLEBOOKS
from agent.marketing.domains.evidence import EvidenceRepository
from agent.marketing.domains.storage import MarketingDomainRepository


KNOWLEDGE_BASES = {"platform", "market", "account", "content"}
TRUSTED_SOURCE_KINDS = {
    "builtin_curated",
    "verified_evidence",
    "accepted_learning",
    "signed_aggregate",
}
FORBIDDEN_SOURCE_KINDS = {"user", "agent", "conversation", "model_inference"}
BOOTSTRAP_MARKER = "marketing_four_knowledge_bases_20260712_v1"

# A missing ``valid_to`` is not permission for volatile knowledge to live
# forever.  Stable content principles and receipt-backed account learning are
# intentionally excluded; platform rules and market observations must be
# refreshed from evidence or a newly signed aggregate.
FRESHNESS_DAYS: dict[tuple[str, str], int] = {
    ("platform", "builtin_curated"): 180,
    ("platform", "verified_evidence"): 90,
    ("platform", "signed_aggregate"): 120,
    ("market", "verified_evidence"): 45,
    ("market", "signed_aggregate"): 60,
}


CONTENT_PRINCIPLES: tuple[dict[str, Any], ...] = (
    {
        "topic": "attention_hook",
        "layer": "individual_attention",
        "principle": "开头的冲突、反常识、痛点或信息缺口提高停留可能，但必须与后文兑现一致。",
        "observable_variables": ["first_3s_retention", "scroll_stop", "title_content_gap"],
    },
    {
        "topic": "personal_relevance",
        "layer": "individual_attention",
        "principle": "内容越接近受众当前任务、身份和损失风险，越容易获得注意与行动。",
        "observable_variables": ["audience_fit", "target_comment_ratio", "profile_visit_rate"],
    },
    {
        "topic": "cognitive_load",
        "layer": "individual_attention",
        "principle": "信息密度需要与受众认知成本匹配；过低无价值，过高会造成跳出。",
        "observable_variables": ["retention_curve", "completion_rate", "rewatch_rate"],
    },
    {
        "topic": "emotional_arousal",
        "layer": "individual_attention",
        "principle": "情绪能提高记忆和传播动机，但过度煽动会损伤信任并增加负反馈。",
        "observable_variables": ["share_rate", "comment_sentiment", "negative_feedback_rate"],
    },
    {
        "topic": "trust_evidence",
        "layer": "persuasion",
        "principle": "来源、案例、边界和反方观点共同决定可信度；断言强度不能超过证据强度。",
        "observable_variables": ["save_rate", "positive_comment_quality", "source_coverage"],
    },
    {
        "topic": "identity_signal",
        "layer": "social_propagation",
        "principle": "用户更愿意转发能表达身份、立场、品味或群体归属的内容。",
        "observable_variables": ["share_rate", "repost_comment_topics", "audience_cluster"],
    },
    {
        "topic": "share_utility",
        "layer": "social_propagation",
        "principle": "实用价值、社交货币和情绪价值是三类主要分享动机。",
        "observable_variables": ["share_rate", "save_rate", "direct_message_mentions"],
    },
    {
        "topic": "group_conflict",
        "layer": "social_propagation",
        "principle": "适度立场差异能触发讨论，极端对立会提高举报、拉黑和账号长期风险。",
        "observable_variables": ["comment_rate", "report_rate", "block_rate", "follower_churn"],
    },
)


class KnowledgeBaseRepository(MarketingDomainRepository):
    """Own durable knowledge while keeping user opinion in memory, not truth."""

    def __init__(self, paths: MarketingDataPaths | None = None):
        super().__init__(paths)
        self.bootstrap_curated_knowledge()

    def bootstrap_curated_knowledge(self) -> None:
        with self._connection() as db:
            if db.execute(
                "SELECT 1 FROM state_meta WHERE key=?", (BOOTSTRAP_MARKER,)
            ).fetchone():
                return
        for platform, stylebook in ARTICLE_STYLEBOOKS.items():
            self._upsert(
                knowledge_base="platform",
                user_id="default",
                account_id=None,
                platform=platform,
                region="cn",
                content_kind="article_soft",
                topic="editor_stylebook",
                statement=stylebook,
                source_kind="builtin_curated",
                source_ref="article_stylebooks",
                evidence_refs=[],
                confidence=0.65,
                version=str(stylebook["version"]),
                valid_from="2026-07-10T00:00:00+00:00",
            )
        for principle in CONTENT_PRINCIPLES:
            self._upsert(
                knowledge_base="content",
                user_id="default",
                account_id=None,
                platform=None,
                region="",
                content_kind="all",
                topic=str(principle["topic"]),
                statement={**principle, "epistemic_status": "testable_prior_not_law"},
                source_kind="builtin_curated",
                source_ref="influence_attention_model.v1",
                evidence_refs=[],
                confidence=0.6,
                version="2026-07-09.v1",
                valid_from="2026-07-09T00:00:00+00:00",
            )
        with self._transaction() as db:
            db.execute(
                "INSERT OR REPLACE INTO state_meta(key,value) VALUES (?,?)",
                (BOOTSTRAP_MARKER, _now()),
            )

    def add_evidence_knowledge(
        self,
        *,
        knowledge_base: str,
        user_id: str,
        account_id: str,
        topic: str,
        statement: dict[str, Any],
        evidence_refs: list[str],
        platform: str | None = None,
        region: str = "cn",
        content_kind: str = "",
        version: str,
        valid_from: str | None = None,
        valid_to: str | None = None,
        confidence: float = 0.7,
        supersedes_entry_ids: list[str] | None = None,
        authority: SystemAuthority | None = None,
    ) -> dict[str, Any]:
        require_system_authority(authority, EpistemicClass.DERIVED_KNOWLEDGE)
        if knowledge_base == "account":
            raise ValueError("account knowledge must come from governed receipt learning")
        verified = EvidenceRepository(self.paths).require_verified(
            user_id=user_id,
            account_id=account_id,
            evidence_ids=evidence_refs,
            require_any=True,
        )
        entry = self._upsert(
            knowledge_base=knowledge_base,
            user_id="default",
            account_id=None,
            platform=platform,
            region=region,
            content_kind=content_kind,
            topic=topic,
            statement=statement,
            source_kind="verified_evidence",
            source_ref=verified[0]["id"],
            evidence_refs=[item["id"] for item in verified],
            confidence=confidence,
            version=version,
            valid_from=valid_from or _now(),
            valid_to=valid_to,
        )
        self._supersede_entries(
            entry=entry,
            entry_ids=supersedes_entry_ids or [],
        )
        return self.get_entry(entry["id"])

    def propose_evidence_knowledge(
        self,
        *,
        knowledge_base: str,
        user_id: str,
        account_id: str,
        topic: str,
        statement: dict[str, Any],
        evidence_refs: list[str],
        platform: str | None = None,
        region: str = "cn",
        content_kind: str = "",
        version: str,
        valid_from: str | None = None,
        valid_to: str | None = None,
        confidence: float = 0.7,
        supersedes_entry_ids: list[str] | None = None,
        source_key: str | None = None,
    ) -> dict[str, Any]:
        """Create a system-evaluated candidate; never write interpretation as truth."""

        base = _base(knowledge_base)
        if base not in {"platform", "market"}:
            raise ValueError("evidence candidates may target only platform or market knowledge")
        verified = EvidenceRepository(self.paths).require_verified(
            user_id=user_id,
            account_id=account_id,
            evidence_ids=evidence_refs,
            require_any=True,
        )
        if base == "platform" and not str(platform or "").strip():
            raise ValueError("platform knowledge candidate requires platform")
        if not isinstance(statement, dict) or not statement:
            raise ValueError("knowledge candidate requires a structured statement")
        bounded_confidence = max(0.0, min(0.85, float(confidence)))
        proposal = {
            "kind": "evidence_knowledge_candidate",
            "knowledge_base": base,
            "topic": str(topic or "").strip(),
            "statement": statement,
            "platform": str(platform or "").strip() or None,
            "region": str(region or "")[:40],
            "content_kind": str(content_kind or "")[:80],
            "version": str(version or "")[:100],
            "valid_from": valid_from or _now(),
            "valid_to": valid_to,
            "supersedes_entry_ids": list(dict.fromkeys(supersedes_entry_ids or []))[:100],
            "guardrail": (
                "Pending only. Source integrity is verified, but the claim enters knowledge "
                "only after system evidence/conflict gates and remains freshness-bounded."
            ),
        }
        if not proposal["topic"] or not proposal["version"]:
            raise ValueError("knowledge candidate requires topic and version")
        digest = hashlib.sha256(
            json.dumps(
                {
                    "base": base,
                    "account": account_id,
                    "platform": proposal["platform"],
                    "topic": proposal["topic"],
                    "statement": statement,
                    "evidence": [item["id"] for item in verified],
                    "version": proposal["version"],
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()[:28]
        from agent.marketing.intelligence.store import OperatingLoopRepository

        return OperatingLoopRepository(self.paths).create_learning_candidate(
            source_key=source_key or f"evidence-knowledge:{digest}",
            candidate_type="memory",
            user_id=user_id,
            account_id=account_id,
            platform=proposal["platform"],
            evidence_refs=[item["id"] for item in verified],
            proposal=proposal,
            confidence=bounded_confidence,
        )

    def project_evidence_candidate(
        self,
        candidate_id: str,
        *,
        authority: SystemAuthority | None = None,
    ) -> dict[str, Any]:
        """Idempotently recover projection of an already accepted candidate."""

        require_system_authority(authority, EpistemicClass.DERIVED_KNOWLEDGE)

        from agent.marketing.intelligence.store import OperatingLoopRepository

        candidate = OperatingLoopRepository(self.paths).get_learning_candidate(candidate_id)
        proposal = candidate.get("proposal") or {}
        if candidate.get("status") != "accepted":
            raise ValueError("only accepted evidence knowledge can be projected")
        if proposal.get("kind") != "evidence_knowledge_candidate":
            raise ValueError("candidate is not evidence knowledge")
        return self.add_evidence_knowledge(
            knowledge_base=str(proposal.get("knowledge_base") or ""),
            user_id=str(candidate.get("user_id") or "default"),
            account_id=str(candidate.get("account_id") or ""),
            topic=str(proposal.get("topic") or ""),
            statement=proposal.get("statement") or {},
            evidence_refs=candidate.get("evidence_refs") or [],
            platform=str(proposal.get("platform") or "") or None,
            region=str(proposal.get("region") or ""),
            content_kind=str(proposal.get("content_kind") or ""),
            version=str(proposal.get("version") or ""),
            valid_from=str(proposal.get("valid_from") or candidate.get("decided_at") or _now()),
            valid_to=str(proposal.get("valid_to") or "") or None,
            confidence=float(candidate.get("confidence") or 0),
            supersedes_entry_ids=proposal.get("supersedes_entry_ids") or [],
            authority=authority,
        )

    def get_entry(self, entry_id: str) -> dict[str, Any]:
        with self._connection() as db:
            row = db.execute(
                "SELECT * FROM marketing_knowledge_entries WHERE id=?", (entry_id,)
            ).fetchone()
        if row is None:
            raise KeyError("knowledge entry not found")
        return _record(row)

    def audit_freshness_and_conflicts(self, *, as_of: str | None = None) -> dict[str, Any]:
        """Remove stale volatile claims from retrieval and quarantine explicit conflicts."""

        now = _parse_time(as_of or _now())
        stale: list[str] = []
        calibrated: list[str] = []
        conflicts: list[dict[str, Any]] = []
        with self._transaction() as db:
            rows = db.execute(
                """SELECT * FROM marketing_knowledge_entries
                WHERE status='active' ORDER BY valid_from,id"""
            ).fetchall()
            active: list[dict[str, Any]] = []
            for row in rows:
                value = _record(row)
                explicit_end = _optional_time(value.get("valid_to"))
                ttl_days = FRESHNESS_DAYS.get(
                    (value["knowledge_base"], value["source_kind"])
                )
                inferred_end = (
                    _parse_time(value["valid_from"]) + timedelta(days=ttl_days)
                    if ttl_days is not None
                    else None
                )
                expires_at = explicit_end or inferred_end
                if explicit_end is None and inferred_end is not None:
                    db.execute(
                        """UPDATE marketing_knowledge_entries
                        SET valid_to=?,updated_at=? WHERE id=? AND status='active'""",
                        (inferred_end.isoformat(), now.isoformat(), value["id"]),
                    )
                    value["valid_to"] = inferred_end.isoformat()
                    calibrated.append(value["id"])
                if expires_at is not None and expires_at <= now:
                    db.execute(
                        """UPDATE marketing_knowledge_entries
                        SET status='stale',valid_to=COALESCE(NULLIF(valid_to,''),?),updated_at=?
                        WHERE id=? AND status='active'""",
                        (expires_at.isoformat(), now.isoformat(), value["id"]),
                    )
                    stale.append(value["id"])
                else:
                    active.append(value)

            claims: dict[tuple[str, ...], list[dict[str, Any]]] = {}
            for value in active:
                claim_key = str((value.get("statement") or {}).get("claim_key") or "").strip()
                if not claim_key:
                    continue
                key = (
                    value["knowledge_base"],
                    value["user_id"],
                    str(value.get("account_id") or ""),
                    str(value.get("platform") or ""),
                    value["region"],
                    value["content_kind"],
                    value["topic"],
                    claim_key,
                )
                claims.setdefault(key, []).append(value)
            for key, entries in claims.items():
                values = {
                    json.dumps(
                        (entry.get("statement") or {}).get("claim_value"),
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    for entry in entries
                }
                if len(values) <= 1:
                    continue
                ids = [entry["id"] for entry in entries]
                db.executemany(
                    """UPDATE marketing_knowledge_entries
                    SET status='conflicted',updated_at=? WHERE id=? AND status='active'""",
                    [(now.isoformat(), entry_id) for entry_id in ids],
                )
                conflicts.append({"claim_key": key[-1], "entry_ids": ids})
        return {
            "as_of": now.isoformat(),
            "freshness_calibrated_entry_ids": calibrated,
            "stale_entry_ids": stale,
            "conflicts": conflicts,
        }

    def _supersede_entries(
        self, *, entry: dict[str, Any], entry_ids: list[str]
    ) -> None:
        ids = list(dict.fromkeys(str(item or "").strip() for item in entry_ids if item))
        if not ids:
            return
        now = _now()
        with self._transaction() as db:
            placeholders = ",".join("?" for _ in ids)
            rows = db.execute(
                f"""SELECT id,knowledge_base,IFNULL(platform,'') AS platform,topic
                FROM marketing_knowledge_entries WHERE id IN ({placeholders})""",
                ids,
            ).fetchall()
            if {row["id"] for row in rows} != set(ids):
                raise ValueError("superseded knowledge entry is missing")
            for row in rows:
                if (
                    row["knowledge_base"] != entry["knowledge_base"]
                    or row["platform"] != str(entry.get("platform") or "")
                    or row["topic"] != entry["topic"]
                ):
                    raise ValueError("superseded knowledge must share base, platform and topic")
            db.executemany(
                """UPDATE marketing_knowledge_entries
                SET status='superseded',valid_to=COALESCE(NULLIF(valid_to,''),?),updated_at=?
                WHERE id=? AND id!=?""",
                [(entry["valid_from"], now, entry_id, entry["id"]) for entry_id in ids],
            )
            previous = next((entry_id for entry_id in ids if entry_id != entry["id"]), None)
            if previous:
                db.execute(
                    "UPDATE marketing_knowledge_entries SET supersedes_id=? WHERE id=?",
                    (previous, entry["id"]),
                )

    def promote_account_learning(
        self,
        *,
        user_id: str,
        account_id: str,
        candidate_id: str,
        topic: str | None = None,
        authority: SystemAuthority | None = None,
    ) -> dict[str, Any]:
        require_system_authority(authority, EpistemicClass.DERIVED_KNOWLEDGE)
        with self._connection() as db:
            row = db.execute(
                """SELECT * FROM marketing_learning_candidates
                WHERE id=? AND user_id=? AND account_id=?""",
                (candidate_id, user_id, account_id),
            ).fetchone()
        if row is None:
            raise KeyError("learning candidate not found in account scope")
        if row["status"] != "accepted":
            raise ValueError("only accepted learning can enter account knowledge")
        receipt_refs = json.loads(row["receipt_refs_json"] or "[]")
        if not receipt_refs:
            raise ValueError("account knowledge requires real receipt references")
        placeholders = ",".join("?" for _ in receipt_refs)
        with self._connection() as db:
            found_receipts = db.execute(
                f"""SELECT id FROM marketing_receipt_refs
                WHERE user_id=? AND account_id=? AND id IN ({placeholders})""",
                [user_id, account_id, *receipt_refs],
            ).fetchall()
        if {item["id"] for item in found_receipts} != set(receipt_refs):
            raise ValueError("account knowledge receipt references are not verified in scope")
        proposal = json.loads(row["proposal_json"] or "{}")
        return self._upsert(
            knowledge_base="account",
            user_id=user_id,
            account_id=account_id,
            platform=row["platform"],
            region="",
            content_kind=str(proposal.get("content_kind") or ""),
            topic=topic or str(proposal.get("rule_key") or row["candidate_type"]),
            statement={
                "candidate_type": row["candidate_type"],
                "proposal": proposal,
                "receipt_refs": receipt_refs,
            },
            source_kind="accepted_learning",
            source_ref=candidate_id,
            evidence_refs=json.loads(row["evidence_refs_json"] or "[]"),
            confidence=float(row["confidence"] or 0),
            version=f"candidate:{candidate_id}",
            valid_from=row["decided_at"] or row["created_at"],
        )

    def install_signed_pack(self, pack: dict[str, Any]) -> dict[str, Any]:
        knowledge_type = str(pack.get("knowledge_type") or "content_prior")
        if knowledge_type == "platform_rule":
            knowledge_base = "platform"
        elif knowledge_type in {"market_pattern", "category_pattern", "category_benchmark"}:
            knowledge_base = "market"
        else:
            knowledge_base = "content"
        sample_size = max(1, int(pack.get("sample_size") or 1))
        confidence = min(0.9, 0.5 + math.log10(sample_size) * 0.1)
        return self._upsert(
            knowledge_base=knowledge_base,
            user_id="default",
            account_id=None,
            platform=str(pack.get("platform") or "") or None,
            region=str(pack.get("region") or ""),
            content_kind=str((pack.get("payload") or {}).get("cohort", {}).get("content_kind") or ""),
            topic=knowledge_type,
            statement={"aggregate_prior": pack.get("payload"), "sample_size": sample_size},
            source_kind="signed_aggregate",
            source_ref=str(pack["id"]),
            evidence_refs=[],
            confidence=confidence,
            version=str(pack["version"]),
            valid_from=str(pack["window_start"]),
            valid_to=None,
        )

    def retrieve(
        self,
        *,
        knowledge_base: str,
        user_id: str = "default",
        account_id: str | None = None,
        platform: str | None = None,
        content_kind: str | None = None,
        topics: list[str] | None = None,
        limit: int = 50,
        as_of: str | None = None,
    ) -> dict[str, Any]:
        base = _base(knowledge_base)
        now = str(as_of or _now())
        query = """SELECT * FROM marketing_knowledge_entries
        WHERE knowledge_base=? AND status='active' AND valid_from<=?
        AND (valid_to IS NULL OR valid_to='' OR valid_to>?)"""
        params: list[Any] = [base, now, now]
        if base == "account":
            if not account_id:
                raise ValueError("account knowledge retrieval requires account_id")
            query += " AND user_id=? AND account_id=?"
            params.extend([user_id, account_id])
        if platform:
            query += " AND (platform=? OR platform IS NULL OR platform='')"
            params.append(platform)
        if content_kind:
            query += " AND (content_kind=? OR content_kind='' OR content_kind='all')"
            params.append(content_kind)
        topic_values = [str(item).strip() for item in (topics or []) if str(item).strip()]
        if topic_values:
            query += " AND topic IN (" + ",".join("?" for _ in topic_values) + ")"
            params.extend(topic_values)
        query += " ORDER BY confidence DESC, valid_from DESC, id LIMIT ?"
        params.append(max(1, min(int(limit), 200)))
        with self._connection() as db:
            rows = db.execute(query, params).fetchall()
        entries = [_record(row) for row in rows]
        return {"knowledge_base": base, "entries": entries, "total": len(entries)}

    def retrieve_for_preflight(
        self,
        *,
        user_id: str,
        account_id: str,
        platforms: list[str],
        content_kind: str,
    ) -> dict[str, Any]:
        platform_entries: list[dict[str, Any]] = []
        for platform in platforms:
            platform_entries.extend(
                self.retrieve(
                    knowledge_base="platform",
                    platform=platform,
                    content_kind=content_kind,
                    limit=30,
                )["entries"]
            )
        return {
            "platform": platform_entries,
            "market": self.retrieve(
                knowledge_base="market",
                platform=platforms[0] if len(platforms) == 1 else None,
                content_kind=content_kind,
                limit=40,
            )["entries"],
            "account": self.retrieve(
                knowledge_base="account",
                user_id=user_id,
                account_id=account_id,
                content_kind=content_kind,
                limit=30,
            )["entries"],
            "content": self.retrieve(
                knowledge_base="content",
                content_kind=content_kind,
                limit=50,
            )["entries"],
            "authority_order": [
                "local_receipt_backed_account_knowledge",
                "verified_current_platform_knowledge",
                "verified_market_and_category_knowledge",
                "curated_or_signed_content_prior",
                "user_preference_memory_is_not_knowledge_truth",
            ],
        }

    def _upsert(
        self,
        *,
        knowledge_base: str,
        user_id: str,
        account_id: str | None,
        platform: str | None,
        region: str,
        content_kind: str,
        topic: str,
        statement: dict[str, Any],
        source_kind: str,
        source_ref: str,
        evidence_refs: list[str],
        confidence: float,
        version: str,
        valid_from: str,
        valid_to: str | None = None,
    ) -> dict[str, Any]:
        base = _base(knowledge_base)
        source = str(source_kind or "").strip()
        if source in FORBIDDEN_SOURCE_KINDS or source not in TRUSTED_SOURCE_KINDS:
            raise ValueError("user/model statements cannot write knowledge truth")
        if base == "account" and (not account_id or source != "accepted_learning"):
            raise ValueError("account knowledge requires accepted receipt-backed learning")
        if base == "platform" and not platform:
            raise ValueError("platform knowledge requires platform")
        topic_value = re.sub(r"[^a-zA-Z0-9_.:-]+", "_", str(topic or "").strip())[:120]
        if not topic_value or not isinstance(statement, dict) or not statement:
            raise ValueError("knowledge topic and structured statement are required")
        identity = {
            "base": base,
            "user": user_id,
            "account": account_id or "",
            "platform": platform or "",
            "region": region,
            "content_kind": content_kind,
            "topic": topic_value,
            "version": version,
            "source_kind": source,
            "source_ref": source_ref,
        }
        entry_id = "knowledge_" + hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()[:28]
        now = _now()
        effective_valid_to = valid_to or _default_valid_to(
            knowledge_base=base,
            source_kind=source,
            valid_from=valid_from,
        )
        with self._transaction() as db:
            previous = None
            if source in {"builtin_curated", "signed_aggregate"}:
                previous = db.execute(
                    """SELECT id FROM marketing_knowledge_entries
                    WHERE knowledge_base=? AND user_id=?
                      AND IFNULL(account_id,'')=? AND IFNULL(platform,'')=?
                      AND region=? AND content_kind=? AND topic=?
                      AND source_kind=? AND source_ref=? AND status='active' AND id!=?
                    ORDER BY valid_from DESC,id DESC LIMIT 1""",
                    (
                        base,
                        user_id,
                        account_id or "",
                        platform or "",
                        str(region or "")[:40],
                        str(content_kind or "")[:80],
                        topic_value,
                        source,
                        str(source_ref or "")[:300],
                        entry_id,
                    ),
                ).fetchone()
            db.execute(
                """INSERT INTO marketing_knowledge_entries
                (id,knowledge_base,user_id,account_id,platform,region,content_kind,topic,
                 statement_json,source_kind,source_ref,evidence_refs_json,confidence,version,
                 status,valid_from,valid_to,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,'active',?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    statement_json=excluded.statement_json,
                    evidence_refs_json=excluded.evidence_refs_json,
                    confidence=excluded.confidence,valid_to=excluded.valid_to,
                    status='active',updated_at=excluded.updated_at""",
                (
                    entry_id,
                    base,
                    user_id,
                    account_id,
                    platform,
                    str(region or "")[:40],
                    str(content_kind or "")[:80],
                    topic_value,
                    json.dumps(statement, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                    source,
                    str(source_ref or "")[:300],
                    json.dumps(list(dict.fromkeys(evidence_refs)), ensure_ascii=False),
                    max(0.0, min(1.0, float(confidence))),
                    str(version or "")[:100],
                    valid_from,
                    effective_valid_to,
                    now,
                    now,
                ),
            )
            if previous is not None:
                db.execute(
                    "UPDATE marketing_knowledge_entries SET status='superseded',updated_at=? WHERE id=?",
                    (now, previous["id"]),
                )
                db.execute(
                    "UPDATE marketing_knowledge_entries SET supersedes_id=? WHERE id=?",
                    (previous["id"], entry_id),
                )
            row = db.execute(
                "SELECT * FROM marketing_knowledge_entries WHERE id=?", (entry_id,)
            ).fetchone()
        return _record(row)


def _base(value: Any) -> str:
    base = str(value or "").strip().lower()
    if base not in KNOWLEDGE_BASES:
        raise ValueError("knowledge_base must be platform, market, account, or content")
    return base


def _record(row: Any) -> dict[str, Any]:
    value = dict(row)
    value["statement"] = json.loads(value.pop("statement_json") or "{}")
    value["evidence_refs"] = json.loads(value.pop("evidence_refs_json") or "[]")
    return value


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_time(value: Any) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid knowledge timestamp: {value}") from exc
    return (
        parsed.replace(tzinfo=timezone.utc)
        if parsed.tzinfo is None
        else parsed.astimezone(timezone.utc)
    )


def _optional_time(value: Any) -> datetime | None:
    return None if value in (None, "") else _parse_time(value)


def _default_valid_to(
    *, knowledge_base: str, source_kind: str, valid_from: str
) -> str | None:
    ttl_days = FRESHNESS_DAYS.get((knowledge_base, source_kind))
    if ttl_days is None:
        return None
    return (_parse_time(valid_from) + timedelta(days=ttl_days)).isoformat()
