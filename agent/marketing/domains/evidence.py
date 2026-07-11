"""Account-scoped evidence captured by the native Hermes tool runtime."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from agent.marketing.data_paths import MarketingDataPaths
from agent.marketing.domains.storage import MarketingDomainRepository


VERIFIED_STATUS = "verified"
_TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "spm",
}


class EvidenceRepository(MarketingDomainRepository):
    """Persist evidence only after a real Hermes collector returned content.

    The repository has no model-facing create method.  The native tool result
    seam calls :meth:`capture_web_extract_result`; model tools may only read
    the generated records and cite their system-generated IDs.
    """

    def __init__(self, paths: MarketingDataPaths | None = None):
        super().__init__(paths)
        self._ensure_schema()

    def capture_web_extract_result(
        self,
        *,
        user_id: str,
        account_id: str,
        result: Any,
        session_id: str,
        tool_call_id: str = "",
        requested_urls: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        payload = _decode_result(result)
        result_items = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(result_items, list):
            return []

        captured: list[dict[str, Any]] = []
        for item in result_items:
            if not isinstance(item, dict) or item.get("error"):
                continue
            canonical_url = _canonical_url(item.get("url"))
            content = str(item.get("content") or "").strip()
            if not canonical_url or not content:
                continue
            title = _optional_text(item.get("title"), 500)
            reported_hash = str(item.get("source_content_sha256") or "").strip().lower()
            content_hash = (
                reported_hash
                if re.fullmatch(r"[0-9a-f]{64}", reported_hash)
                else hashlib.sha256(content.encode("utf-8")).hexdigest()
            )
            digest = hashlib.sha256(
                f"{user_id}\0{account_id}\0web_extract\0{canonical_url}\0{content_hash}".encode(
                    "utf-8"
                )
            ).hexdigest()[:28]
            evidence_id = f"evidence_{digest}"
            now = _now()
            excerpt = _excerpt(content)
            metadata = {
                "collector": "hermes.web_extract",
                "content_characters": len(content),
                "excerpt_origin": str(item.get("content_origin") or "extracted_source"),
                "source_hash_origin": (
                    "native_collector_raw_content"
                    if re.fullmatch(r"[0-9a-f]{64}", reported_hash)
                    else "returned_content_fallback"
                ),
                "requested_urls": [
                    value
                    for value in (_canonical_url(url) for url in (requested_urls or []))
                    if value
                ][:20],
                "claim_truth_verified": False,
                "verification_note": (
                    "Source integrity was verified by a successful native fetch; "
                    "individual claims may still require cross-source verification."
                ),
            }
            with self._transaction() as db:
                db.execute(
                    """INSERT INTO evidence_records
                    (id,user_id,account_id,source_type,provider,canonical_url,title,excerpt,
                     content_sha256,status,verification_level,captured_at,session_id,
                     tool_call_id,metadata_json,created_at,updated_at)
                    VALUES (?,?,?,'web',?,?,?,?,?,'verified','source_integrity',?,?,?,?,?,?)
                    ON CONFLICT(id) DO UPDATE SET
                        title=excluded.title,
                        excerpt=excluded.excerpt,
                        session_id=excluded.session_id,
                        tool_call_id=excluded.tool_call_id,
                        metadata_json=excluded.metadata_json,
                        updated_at=excluded.updated_at""",
                    (
                        evidence_id,
                        user_id,
                        account_id,
                        "hermes_web_extract",
                        canonical_url,
                        title,
                        excerpt,
                        content_hash,
                        now,
                        session_id,
                        tool_call_id,
                        json.dumps(metadata, ensure_ascii=False, separators=(",", ":")),
                        now,
                        now,
                    ),
                )
                row = db.execute(
                    "SELECT * FROM evidence_records WHERE id=?", (evidence_id,)
                ).fetchone()
            captured.append(_record(row))
        return captured

    def require_verified(
        self,
        *,
        user_id: str,
        account_id: str,
        evidence_ids: list[str],
        require_any: bool = True,
    ) -> list[dict[str, Any]]:
        refs = _evidence_ids(evidence_ids)
        if require_any and not refs:
            raise ValueError(
                "content production requires at least one verified EvidencePack record"
            )
        if not refs:
            return []
        placeholders = ",".join("?" for _ in refs)
        with self._connection() as db:
            rows = db.execute(
                f"""SELECT * FROM evidence_records
                WHERE user_id=? AND account_id=? AND status='verified'
                  AND id IN ({placeholders})""",
                [user_id, account_id, *refs],
            ).fetchall()
        found = {row["id"]: _record(row) for row in rows}
        missing = [ref for ref in refs if ref not in found]
        if missing:
            raise ValueError(
                "evidence_refs must be verified records captured in the current account scope: "
                + ", ".join(missing)
            )
        return [found[ref] for ref in refs]

    def list(
        self,
        *,
        user_id: str,
        account_id: str,
        status: str | None = VERIFIED_STATUS,
        limit: int = 20,
    ) -> dict[str, Any]:
        safe_limit = max(1, min(int(limit), 100))
        query = "SELECT * FROM evidence_records WHERE user_id=? AND account_id=?"
        params: list[Any] = [user_id, account_id]
        if status:
            if status not in {"captured", "verified", "rejected", "stale"}:
                raise ValueError("unsupported evidence status")
            query += " AND status=?"
            params.append(status)
        query += " ORDER BY captured_at DESC, id DESC LIMIT ?"
        params.append(safe_limit)
        with self._connection() as db:
            rows = db.execute(query, params).fetchall()
        records = [_record(row) for row in rows]
        return {
            "user_id": user_id,
            "account_id": account_id,
            "records": records,
            "total": len(records),
            "verification_semantics": (
                "verified means source integrity is complete; it does not assert every claim is true"
            ),
        }

    def _ensure_schema(self) -> None:
        with self._connection() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS evidence_records (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    canonical_url TEXT NOT NULL,
                    title TEXT NOT NULL DEFAULT '',
                    excerpt TEXT NOT NULL,
                    content_sha256 TEXT NOT NULL,
                    status TEXT NOT NULL,
                    verification_level TEXT NOT NULL,
                    captured_at TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    tool_call_id TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_evidence_scope_content
                    ON evidence_records(user_id, account_id, provider, canonical_url, content_sha256);
                CREATE INDEX IF NOT EXISTS idx_evidence_scope_status
                    ON evidence_records(user_id, account_id, status, captured_at);
                """
            )

def _decode_result(result: Any) -> dict[str, Any]:
    if isinstance(result, dict):
        return result
    if not isinstance(result, str):
        return {}
    try:
        value = json.loads(result)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _canonical_url(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        parsed = urlsplit(text)
    except ValueError:
        return ""
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        return ""
    if parsed.username or parsed.password:
        return ""
    hostname = parsed.hostname.lower()
    try:
        port = parsed.port
    except ValueError:
        return ""
    netloc = hostname
    if port and not (
        (parsed.scheme.lower() == "http" and port == 80)
        or (parsed.scheme.lower() == "https" and port == 443)
    ):
        netloc = f"{hostname}:{port}"
    query = [
        (key, item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in _TRACKING_QUERY_KEYS
    ]
    return urlunsplit(
        (
            parsed.scheme.lower(),
            netloc,
            parsed.path or "/",
            urlencode(sorted(query)),
            "",
        )
    )


def _excerpt(content: str, limit: int = 4_000) -> str:
    compact = re.sub(r"\s+", " ", content).strip()
    if not compact:
        raise ValueError("evidence content is empty")
    return compact[:limit]


def _evidence_ids(value: Any) -> list[str]:
    if not isinstance(value, list):
        raise ValueError("evidence_refs must be a list")
    result: list[str] = []
    for item in value:
        ref = str(item or "").strip()
        if not ref:
            continue
        if not re.fullmatch(r"evidence_[0-9a-f]{28}", ref):
            raise ValueError(f"invalid EvidencePack id: {ref}")
        if ref not in result:
            result.append(ref)
    if len(result) > 100:
        raise ValueError("evidence_refs exceeds 100 records")
    return result


def _record(row: sqlite3.Row) -> dict[str, Any]:
    value = dict(row)
    value["metadata"] = json.loads(value.pop("metadata_json") or "{}")
    return value


def _optional_text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
