"""User-owned media asset library shared by content and video production."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from agent.marketing.data_paths import MarketingDataPaths
from agent.marketing.domains.storage import MarketingDomainRepository


MEDIA_TYPES = {"image", "audio", "video"}
ASSET_ROLES = {
    "character",
    "voice",
    "scene",
    "prop",
    "storyboard",
    "broll",
    "music",
    "sfx",
    "final_video",
    "other",
}
SOURCE_TYPES = {
    "user_upload",
    "ai_generated",
    "volcengine_trusted",
    "licensed_provider",
    "derived",
}
RIGHTS_STATUSES = {
    "user_confirmed",
    "provider_verified",
    "generated",
    "licensed",
    "inherited",
}
MAX_UPLOAD_BYTES = 200 * 1024 * 1024
MAX_INLINE_UPLOAD_BYTES = 32 * 1024 * 1024
MAX_LOCAL_IMPORT_FILES = 200
TEMPORARY_ASSET_TTL_DAYS = 7
STORAGE_TIERS = {"temporary", "library", "cloud"}

_RIGHTS_BY_SOURCE = {
    "user_upload": "user_confirmed",
    "ai_generated": "generated",
    "volcengine_trusted": "provider_verified",
    "licensed_provider": "licensed",
    "derived": "inherited",
}
_SENSITIVE_KEY = re.compile(
    r"^(?:api[_-]?key|authorization|cookie|password|secret|token)$"
    r"|(?:^|[_-])(?:access[_-]?token|refresh[_-]?token|client[_-]?secret)$",
    re.IGNORECASE,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _record(row) -> dict[str, Any]:
    result = dict(row)
    result["metadata"] = json.loads(result.pop("metadata_json") or "{}")
    result["receipt"] = json.loads(result.pop("receipt_json") or "{}")
    return result


def _required_text(value: Any, field: str, *, limit: int = 256) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} is required")
    if len(text) > limit:
        raise ValueError(f"{field} must be at most {limit} characters")
    return text


def _optional_text(value: Any, field: str, *, limit: int = 256) -> str | None:
    if value is None or not str(value).strip():
        return None
    return _required_text(value, field, limit=limit)


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if _SENSITIVE_KEY.search(str(key)) else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, tuple):
        return [_redact(item) for item in value]
    return value


def _safe_json_object(value: dict[str, Any] | None, field: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object")
    cleaned = _redact(value)
    try:
        json.dumps(cleaned, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must contain JSON-compatible values") from exc
    return cleaned


def _safe_filename(value: Any) -> str:
    raw = Path(str(value or "")).name
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", raw) or "asset.bin"
    if len(cleaned.encode("utf-8")) <= 180:
        return cleaned
    suffix = Path(cleaned).suffix[:20]
    stem_limit = max(1, 180 - len(suffix))
    return f"{Path(cleaned).stem[:stem_limit]}{suffix}"


def _local_media_type(path: Path) -> tuple[str, str]:
    mime_type = str(mimetypes.guess_type(path.name)[0] or "").lower()
    for media_type in ("image", "video", "audio"):
        if mime_type.startswith(f"{media_type}/"):
            return media_type, mime_type
    return "", ""


class MediaAssetRepository(MarketingDomainRepository):
    def __init__(self, paths: MarketingDataPaths | None = None):
        super().__init__(paths)
        self.root = self.paths.config_dir.parent / "marketing-assets"
        self.root.mkdir(parents=True, exist_ok=True)

    def import_bytes(
        self,
        *,
        user_id: str,
        account_id: str | None,
        name: str,
        media_type: str,
        role: str,
        source_type: str,
        rights_status: str,
        payload: bytes,
        filename: str,
        mime_type: str = "",
        provider: str = "",
        provider_asset_id: str = "",
        metadata: dict[str, Any] | None = None,
        receipt: dict[str, Any] | None = None,
        storage_tier: str = "library",
        expires_at: str | None = None,
    ) -> dict[str, Any]:
        self._validate(media_type, role, source_type, rights_status)
        user_id = _required_text(user_id, "user_id")
        account_id = _optional_text(account_id, "account_id")
        name = _required_text(name, "name", limit=512)
        metadata = _safe_json_object(metadata, "metadata")
        receipt = _safe_json_object(receipt, "receipt")
        storage_tier = str(storage_tier or "library").strip().lower()
        if storage_tier not in STORAGE_TIERS:
            raise ValueError("unsupported storage tier")
        if storage_tier == "temporary" and not expires_at:
            expires_at = (
                datetime.now(timezone.utc) + timedelta(days=TEMPORARY_ASSET_TTL_DAYS)
            ).isoformat()
        if storage_tier != "temporary":
            expires_at = None
        normalized_mime = str(mime_type or "").strip().lower()
        if normalized_mime and not normalized_mime.startswith(f"{media_type}/"):
            raise ValueError("mime_type does not match media_type")
        if not payload or len(payload) > MAX_UPLOAD_BYTES:
            raise ValueError("asset payload must be between 1 byte and 200 MB")
        asset_id = f"media_{uuid.uuid4().hex}"
        safe_name = _safe_filename(filename)
        user_scope = hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:24]
        relative = Path(user_scope) / asset_id / safe_name
        target = (self.root / relative).resolve()
        if self.root.resolve() not in target.parents:
            raise ValueError("asset path escaped the media library")
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
            os.replace(tmp, target)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        digest = hashlib.sha256(payload).hexdigest()
        try:
            return self._insert(
                asset_id=asset_id,
                user_id=user_id,
                account_id=account_id,
                name=name,
                media_type=media_type,
                role=role,
                source_type=source_type,
                provider=provider,
                provider_asset_id=provider_asset_id,
                local_path=str(relative),
                mime_type=normalized_mime,
                sha256=digest,
                size_bytes=len(payload),
                rights_status=rights_status,
                metadata=metadata,
                receipt=receipt,
                storage_tier=storage_tier,
                expires_at=expires_at,
            )
        except Exception:
            target.unlink(missing_ok=True)
            raise

    def import_local_paths(
        self,
        *,
        user_id: str,
        account_id: str | None,
        paths: list[str],
        rights_confirmed: bool,
    ) -> dict[str, Any]:
        """Import user-selected local media without persisting source paths."""

        if not rights_confirmed:
            raise ValueError("the user must confirm they may use these assets")
        user_value = _required_text(user_id, "user_id")
        account_value = _optional_text(account_id, "account_id")
        selected = [
            Path(str(value)).expanduser().resolve()
            for value in paths[:50]
            if str(value).strip()
        ]
        files: list[tuple[Path, str]] = []
        skipped: list[dict[str, str]] = []

        for source in selected:
            if source.is_symlink():
                skipped.append({"name": source.name, "reason": "symbolic_link_ignored"})
                continue
            if source.is_file():
                files.append((source, ""))
                continue
            if not source.is_dir():
                skipped.append({
                    "name": source.name or "unknown",
                    "reason": "path_unavailable",
                })
                continue
            for candidate in source.rglob("*"):
                if len(files) >= MAX_LOCAL_IMPORT_FILES:
                    break
                if candidate.is_file() and not candidate.is_symlink():
                    files.append((candidate, source.name[:256]))

        imported: list[dict[str, Any]] = []
        reused: list[dict[str, Any]] = []
        for source, collection_name in files[:MAX_LOCAL_IMPORT_FILES]:
            media_type, mime_type = _local_media_type(source)
            if not media_type:
                skipped.append({
                    "name": source.name,
                    "reason": "unsupported_media_type",
                })
                continue
            try:
                size = source.stat().st_size
            except OSError:
                skipped.append({"name": source.name, "reason": "file_unavailable"})
                continue
            if size <= 0 or size > MAX_UPLOAD_BYTES:
                skipped.append({
                    "name": source.name,
                    "reason": "file_size_out_of_range",
                })
                continue
            payload = source.read_bytes()
            digest = hashlib.sha256(payload).hexdigest()
            existing = self._find_user_upload(
                user_id=user_value,
                account_id=account_value,
                sha256=digest,
            )
            if existing is not None:
                reused.append(existing)
                continue
            imported.append(
                self.import_bytes(
                    user_id=user_value,
                    account_id=account_value,
                    name=source.stem[:512] or source.name[:512],
                    media_type=media_type,
                    role="other",
                    source_type="user_upload",
                    rights_status="user_confirmed",
                    payload=payload,
                    filename=source.name,
                    mime_type=mime_type,
                    metadata={
                        "import_kind": "local_folder"
                        if collection_name
                        else "local_file",
                        "collection_name": collection_name or None,
                        "original_filename": source.name,
                    },
                )
            )

        return {
            "assets": imported,
            "imported": len(imported),
            "reused": len(reused),
            "reused_assets": reused,
            "skipped": skipped[:100],
            "truncated": len(files) > MAX_LOCAL_IMPORT_FILES,
        }

    def _find_user_upload(
        self,
        *,
        user_id: str,
        account_id: str | None,
        sha256: str,
    ) -> dict[str, Any] | None:
        with self._connection() as db:
            row = db.execute(
                """SELECT * FROM media_asset_library
                WHERE user_id=? AND COALESCE(account_id,'')=COALESCE(?, '')
                  AND source_type='user_upload' AND sha256=? AND status='active'
                ORDER BY created_at ASC LIMIT 1""",
                (user_id, account_id, sha256),
            ).fetchone()
        return _record(row) if row is not None else None

    def register_volcengine_trusted_asset(
        self,
        *,
        user_id: str,
        account_id: str | None,
        name: str,
        provider_asset_id: str,
        media_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        user_id = _required_text(user_id, "user_id")
        account_id = _optional_text(account_id, "account_id")
        name = _required_text(name, "name", limit=512)
        provider_asset_id = _required_text(
            provider_asset_id, "provider_asset_id", limit=2048
        )
        if not provider_asset_id.startswith("asset://"):
            raise ValueError("trusted asset id must use asset:// URI")
        self._validate(
            media_type, "character", "volcengine_trusted", "provider_verified"
        )
        metadata = _safe_json_object(metadata, "metadata")
        with self._connection() as db:
            existing = db.execute(
                """SELECT * FROM media_asset_library
                WHERE user_id=? AND provider='volcengine_ark'
                  AND provider_asset_id=? AND status='active'
                ORDER BY created_at ASC LIMIT 1""",
                (user_id, provider_asset_id),
            ).fetchone()
        if existing is not None:
            return _record(existing)
        return self._insert(
            asset_id=f"media_{uuid.uuid4().hex}",
            user_id=user_id,
            account_id=account_id,
            name=name,
            media_type=media_type,
            role="character",
            source_type="volcengine_trusted",
            provider="volcengine_ark",
            provider_asset_id=provider_asset_id,
            local_path="",
            mime_type="",
            sha256="",
            size_bytes=0,
            rights_status="provider_verified",
            metadata=metadata,
            receipt={},
        )

    def import_generated_file(
        self,
        *,
        user_id: str,
        account_id: str,
        name: str,
        media_type: str,
        role: str,
        path: Path,
        mime_type: str,
        provider: str,
        provider_asset_id: str,
        source_type: str = "ai_generated",
        rights_status: str = "generated",
        metadata: dict[str, Any] | None = None,
        receipt: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Import one provider output idempotently under a stable production URI."""

        provider_value = _required_text(provider, "provider")
        provider_asset_value = _required_text(
            provider_asset_id, "provider_asset_id", limit=2048
        )
        with self._connection() as db:
            existing = db.execute(
                """SELECT * FROM media_asset_library
                WHERE user_id=? AND account_id=? AND provider=?
                  AND provider_asset_id=? AND status='active'
                ORDER BY created_at ASC LIMIT 1""",
                (user_id, account_id, provider_value, provider_asset_value),
            ).fetchone()
        if existing is not None:
            return _record(existing)
        source = path.expanduser().resolve()
        if not source.is_file():
            raise ValueError("generated media output does not exist")
        return self.import_bytes(
            user_id=user_id,
            account_id=account_id,
            name=name,
            media_type=media_type,
            role=role,
            source_type=source_type,
            rights_status=rights_status,
            payload=source.read_bytes(),
            filename=source.name,
            mime_type=mime_type,
            provider=provider_value,
            provider_asset_id=provider_asset_value,
            metadata=metadata,
            receipt=receipt,
        )

    def import_provider_bytes(
        self,
        *,
        user_id: str,
        account_id: str,
        name: str,
        media_type: str,
        role: str,
        payload: bytes,
        filename: str,
        mime_type: str,
        provider: str,
        provider_asset_id: str,
        metadata: dict[str, Any] | None = None,
        receipt: dict[str, Any] | None = None,
        storage_tier: str = "library",
    ) -> dict[str, Any]:
        """Import a licensed provider binary once under its stable identity."""

        provider_value = _required_text(provider, "provider")
        provider_asset_value = _required_text(
            provider_asset_id, "provider_asset_id", limit=2048
        )
        existing = self.find_provider_asset(
            user_id=user_id,
            account_id=account_id,
            provider=provider_value,
            provider_asset_id=provider_asset_value,
        )
        if existing is not None:
            return existing
        return self.import_bytes(
            user_id=user_id,
            account_id=account_id,
            name=name,
            media_type=media_type,
            role=role,
            source_type="licensed_provider",
            rights_status="licensed",
            payload=payload,
            filename=filename,
            mime_type=mime_type,
            provider=provider_value,
            provider_asset_id=provider_asset_value,
            metadata=metadata,
            receipt=receipt,
            storage_tier=storage_tier,
        )

    def find_provider_asset(
        self,
        *,
        user_id: str,
        account_id: str,
        provider: str,
        provider_asset_id: str,
    ) -> dict[str, Any] | None:
        with self._connection() as db:
            row = db.execute(
                """SELECT * FROM media_asset_library
                WHERE user_id=? AND account_id=? AND provider=?
                  AND provider_asset_id=? AND status='active'
                ORDER BY created_at ASC LIMIT 1""",
                (user_id, account_id, provider, provider_asset_id),
            ).fetchone()
        return _record(row) if row is not None else None

    def _insert(self, **values) -> dict[str, Any]:
        now = _now()
        with self._transaction() as db:
            db.execute(
                """INSERT INTO media_asset_library
                (id,user_id,account_id,name,media_type,role,source_type,provider,
                 provider_asset_id,local_path,mime_type,sha256,size_bytes,rights_status,
                 metadata_json,receipt_json,storage_tier,expires_at,last_used_at,
                 status,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'active',?,?)""",
                (
                    values["asset_id"],
                    values["user_id"],
                    values["account_id"],
                    values["name"],
                    values["media_type"],
                    values["role"],
                    values["source_type"],
                    values["provider"],
                    values["provider_asset_id"],
                    values["local_path"],
                    values["mime_type"],
                    values["sha256"],
                    values["size_bytes"],
                    values["rights_status"],
                    json.dumps(values["metadata"], ensure_ascii=False),
                    json.dumps(values["receipt"], ensure_ascii=False),
                    values.get("storage_tier", "library"),
                    values.get("expires_at"),
                    now,
                    now,
                    now,
                ),
            )
            row = db.execute(
                "SELECT * FROM media_asset_library WHERE id=?", (values["asset_id"],)
            ).fetchone()
        return _record(row)

    def list(self, *, user_id: str, account_id: str | None = None) -> dict[str, Any]:
        self.cleanup_expired(user_id=user_id)
        with self._connection() as db:
            if account_id:
                rows = db.execute(
                    """SELECT * FROM media_asset_library
                    WHERE user_id=? AND status='active' AND (account_id IS NULL OR account_id=?)
                    ORDER BY updated_at DESC""",
                    (user_id, account_id),
                ).fetchall()
            else:
                rows = db.execute(
                    """SELECT * FROM media_asset_library
                    WHERE user_id=? AND status='active' ORDER BY updated_at DESC""",
                    (user_id,),
                ).fetchall()
        return {"assets": [_record(row) for row in rows], "total": len(rows)}

    def promote(
        self,
        *,
        asset_id: str,
        user_id: str,
        target_tier: str = "library",
    ) -> dict[str, Any]:
        """Keep a temporary asset in the durable local library."""

        target = str(target_tier or "library").strip().lower()
        if target == "cloud":
            raise ValueError("cloud material provider is not connected")
        if target != "library":
            raise ValueError(
                "temporary assets can only be promoted to the local library"
            )
        asset = self.get(asset_id=asset_id, user_id=user_id)
        if asset["storage_tier"] == target:
            return asset
        now = _now()
        with self._transaction() as db:
            db.execute(
                """UPDATE media_asset_library
                SET storage_tier='library',expires_at=NULL,last_used_at=?,updated_at=?
                WHERE id=? AND user_id=? AND status='active'""",
                (now, now, asset_id, user_id),
            )
        return self.get(asset_id=asset_id, user_id=user_id)

    def cleanup_expired(
        self,
        *,
        user_id: str | None = None,
        now: str | None = None,
    ) -> dict[str, Any]:
        """Remove expired temporary binaries that have no active references."""

        cutoff = str(now or _now())
        params: list[Any] = [cutoff]
        user_clause = ""
        if user_id:
            user_clause = " AND asset.user_id=?"
            params.append(_required_text(user_id, "user_id"))
        with self._transaction() as db:
            rows = db.execute(
                f"""SELECT asset.* FROM media_asset_library AS asset
                WHERE asset.status='active' AND asset.storage_tier='temporary'
                  AND asset.expires_at IS NOT NULL AND asset.expires_at<=?
                  {user_clause}
                  AND NOT EXISTS (
                    SELECT 1 FROM media_asset_references AS ref WHERE ref.asset_id=asset.id
                  )
                ORDER BY asset.expires_at ASC""",
                tuple(params),
            ).fetchall()
            ids = [str(row["id"]) for row in rows]
            if ids:
                placeholders = ",".join("?" for _ in ids)
                db.execute(
                    f"""UPDATE media_asset_library
                    SET status='expired',deleted_at=?,updated_at=?
                    WHERE id IN ({placeholders})""",
                    (cutoff, cutoff, *ids),
                )
        reclaimed = 0
        for row in rows:
            asset = _record(row)
            reclaimed += int(asset.get("size_bytes") or 0)
            relative = str(asset.get("local_path") or "")
            if relative:
                target = (self.root / relative).resolve()
                if self.root.resolve() in target.parents and target.exists():
                    target.unlink()
        return {
            "expired_asset_ids": ids,
            "expired": len(ids),
            "reclaimed_bytes": reclaimed,
        }

    def add_reference(
        self,
        *,
        asset_id: str,
        user_id: str,
        owner_kind: str,
        owner_id: str,
        relation: str,
    ) -> None:
        asset_id = _required_text(asset_id, "asset_id")
        user_id = _required_text(user_id, "user_id")
        owner_kind = _required_text(owner_kind, "owner_kind", limit=128)
        owner_id = _required_text(owner_id, "owner_id", limit=256)
        relation = _required_text(relation, "relation", limit=128)
        self.get(asset_id=asset_id, user_id=user_id)
        with self._transaction() as db:
            db.execute(
                """INSERT OR IGNORE INTO media_asset_references
                (id,asset_id,owner_kind,owner_id,relation,created_at) VALUES (?,?,?,?,?,?)""",
                (
                    f"ref_{uuid.uuid4().hex}",
                    asset_id,
                    owner_kind,
                    owner_id,
                    relation,
                    _now(),
                ),
            )
            now = _now()
            db.execute(
                """UPDATE media_asset_library
                SET last_used_at=?,expires_at=CASE WHEN storage_tier='temporary' THEN ? ELSE expires_at END,
                    updated_at=? WHERE id=?""",
                (
                    now,
                    (
                        datetime.now(timezone.utc)
                        + timedelta(days=TEMPORARY_ASSET_TTL_DAYS)
                    ).isoformat(),
                    now,
                    asset_id,
                ),
            )

    def remove_reference(
        self,
        *,
        asset_id: str,
        user_id: str,
        owner_kind: str,
        owner_id: str,
        relation: str,
    ) -> None:
        asset_id = _required_text(asset_id, "asset_id")
        user_id = _required_text(user_id, "user_id")
        owner_kind = _required_text(owner_kind, "owner_kind", limit=128)
        owner_id = _required_text(owner_id, "owner_id", limit=256)
        relation = _required_text(relation, "relation", limit=128)
        self.get(asset_id=asset_id, user_id=user_id)
        with self._transaction() as db:
            db.execute(
                "DELETE FROM media_asset_references WHERE asset_id=? AND owner_kind=? AND owner_id=? AND relation=?",
                (asset_id, owner_kind, owner_id, relation),
            )
            now = _now()
            db.execute(
                """UPDATE media_asset_library
                SET last_used_at=?,expires_at=CASE WHEN storage_tier='temporary' THEN ? ELSE expires_at END,
                    updated_at=? WHERE id=?""",
                (
                    now,
                    (
                        datetime.now(timezone.utc)
                        + timedelta(days=TEMPORARY_ASSET_TTL_DAYS)
                    ).isoformat(),
                    now,
                    asset_id,
                ),
            )

    def delete(self, *, asset_id: str, user_id: str, confirmed: bool) -> dict[str, Any]:
        if not confirmed:
            raise ValueError("explicit delete confirmation is required")
        asset = self.get(asset_id=asset_id, user_id=user_id)
        with self._transaction() as db:
            refs = [
                dict(row)
                for row in db.execute(
                    "SELECT owner_kind,owner_id,relation FROM media_asset_references WHERE asset_id=?",
                    (asset_id,),
                ).fetchall()
            ]
            if refs:
                return {"deleted": False, "blocked_by": refs, "asset": asset}
            now = _now()
            db.execute(
                "UPDATE media_asset_library SET status='deleted',deleted_at=?,updated_at=? WHERE id=?",
                (now, now, asset_id),
            )
        if asset["local_path"]:
            target = (self.root / asset["local_path"]).resolve()
            if self.root.resolve() in target.parents and target.exists():
                target.unlink()
        return {"deleted": True, "blocked_by": [], "asset_id": asset_id}

    def get(self, *, asset_id: str, user_id: str) -> dict[str, Any]:
        with self._connection() as db:
            row = db.execute(
                "SELECT * FROM media_asset_library WHERE id=? AND user_id=? AND status='active'",
                (asset_id, user_id),
            ).fetchone()
        if row is None:
            raise KeyError("media asset not found in user scope")
        return _record(row)

    def resolve_local_path(self, *, asset_id: str, user_id: str) -> str | None:
        """Resolve one library-owned file for a presentation surface."""

        asset = self.get(asset_id=asset_id, user_id=user_id)
        relative = str(asset.get("local_path") or "").strip()
        if not relative:
            return None
        target = (self.root / relative).resolve()
        if self.root.resolve() not in target.parents or not target.is_file():
            return None
        return str(target)

    @staticmethod
    def _validate(
        media_type: str, role: str, source_type: str, rights_status: str
    ) -> None:
        if media_type not in MEDIA_TYPES:
            raise ValueError("unsupported media type")
        if role not in ASSET_ROLES:
            raise ValueError("unsupported asset role")
        if source_type not in SOURCE_TYPES:
            raise ValueError("unsupported asset source type")
        if rights_status not in RIGHTS_STATUSES:
            raise ValueError("unsupported rights status")
        if _RIGHTS_BY_SOURCE[source_type] != rights_status:
            raise ValueError("rights status does not match asset source type")
