"""Three governed knowledge bases: platform, account, and content."""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from typing import Any

from agent.marketing.data_paths import MarketingDataPaths
from agent.marketing.domains.article_drafts import ARTICLE_STYLEBOOKS
from agent.marketing.domains.evidence import EvidenceRepository
from agent.marketing.domains.storage import MarketingDomainRepository


KNOWLEDGE_BASES = {"platform", "account", "content"}
TRUSTED_SOURCE_KINDS = {
    "builtin_curated",
    "verified_evidence",
    "accepted_learning",
    "signed_aggregate",
}
FORBIDDEN_SOURCE_KINDS = {"user", "agent", "conversation", "model_inference"}
BOOTSTRAP_MARKER = "marketing_three_knowledge_bases_20260712_v1"


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
    ) -> dict[str, Any]:
        if knowledge_base == "account":
            raise ValueError("account knowledge must come from governed receipt learning")
        verified = EvidenceRepository(self.paths).require_verified(
            user_id=user_id,
            account_id=account_id,
            evidence_ids=evidence_refs,
            require_any=True,
        )
        return self._upsert(
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

    def promote_account_learning(
        self,
        *,
        user_id: str,
        account_id: str,
        candidate_id: str,
        topic: str | None = None,
    ) -> dict[str, Any]:
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
        knowledge_base = "platform" if knowledge_type == "platform_rule" else "content"
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
                    valid_to,
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
        raise ValueError("knowledge_base must be platform, account, or content")
    return base


def _record(row: Any) -> dict[str, Any]:
    value = dict(row)
    value["statement"] = json.loads(value.pop("statement_json") or "{}")
    value["evidence_refs"] = json.loads(value.pop("evidence_refs_json") or "[]")
    return value


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
