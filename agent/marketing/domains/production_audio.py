"""Auditable TTS production for the native faceless-video lane."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from agent.marketing.data_paths import MarketingDataPaths
from agent.marketing.domains.media_assets import MediaAssetRepository
from agent.marketing.domains.storage import MarketingDomainRepository


TTS_JOB_VERSION = "marketing.video.voice.v1"
_TTSRunner = Callable[[str, str], str]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _record(row) -> dict[str, Any]:
    value = dict(row)
    value["receipt"] = json.loads(value.pop("receipt_json") or "{}")
    value.pop("idempotency_key", None)
    return value


class ProductionAudioRepository(MarketingDomainRepository):
    """Prepare and settle real provider-backed voice assets with one-shot approval."""

    def __init__(
        self,
        paths: MarketingDataPaths | None = None,
        *,
        tts_runner: _TTSRunner | None = None,
    ) -> None:
        super().__init__(paths)
        self.media = MediaAssetRepository(self.paths)
        self._tts_runner = tts_runner

    def prepare_voice(
        self,
        *,
        user_id: str,
        account_id: str,
        name: str,
        script_text: str,
    ) -> dict[str, Any]:
        user_id = self._required(user_id, "user_id")
        account_id = self._required(account_id, "account_id")
        name = self._required(name, "name", limit=300)
        script = self._required(script_text, "script_text", limit=4000)
        script_sha = hashlib.sha256(script.encode("utf-8")).hexdigest()
        idempotency_key = hashlib.sha256(
            f"{user_id}\0{account_id}\0voiceover\0{name}\0{script_sha}".encode("utf-8")
        ).hexdigest()
        now = _now()
        job_id = f"audio_job_{uuid.uuid4().hex}"
        with self._transaction() as db:
            existing = db.execute(
                "SELECT * FROM marketing_audio_jobs WHERE idempotency_key=?",
                (idempotency_key,),
            ).fetchone()
            if existing is not None:
                return _record(existing)
            db.execute(
                """INSERT INTO marketing_audio_jobs
                (id,idempotency_key,user_id,account_id,kind,name,script_text,
                 script_sha256,status,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,'prepared',?,?)""",
                (
                    job_id, idempotency_key, user_id, account_id, "voiceover",
                    name, script, script_sha, now, now,
                ),
            )
            row = db.execute(
                "SELECT * FROM marketing_audio_jobs WHERE id=?", (job_id,)
            ).fetchone()
        return _record(row)

    def approve(
        self,
        *,
        job_id: str,
        user_id: str,
        account_id: str,
        approval_ref: str,
        confirmed_by_user: bool,
    ) -> dict[str, Any]:
        if not confirmed_by_user:
            raise ValueError("explicit human approval is required before TTS generation")
        approval = self._required(approval_ref, "approval_ref", limit=500)
        with self._transaction() as db:
            row = db.execute(
                """SELECT * FROM marketing_audio_jobs
                WHERE id=? AND user_id=? AND account_id=?""",
                (job_id, user_id, account_id),
            ).fetchone()
            if row is None:
                raise KeyError("audio job not found in account scope")
            if row["status"] in {"prepared", "failed"}:
                db.execute(
                    """UPDATE marketing_audio_jobs
                    SET status='approved',approval_ref=?,failure_code=NULL,
                        settled_at=NULL,updated_at=? WHERE id=?""",
                    (approval, _now(), job_id),
                )
            elif row["status"] not in {"approved", "running", "completed"}:
                raise ValueError(f"cannot approve audio job in {row['status']}")
        return self.get(job_id=job_id, user_id=user_id, account_id=account_id)

    def execute(
        self, *, job_id: str, user_id: str, account_id: str
    ) -> dict[str, Any]:
        job = self.get(job_id=job_id, user_id=user_id, account_id=account_id)
        if job["status"] == "completed":
            return job
        if job["status"] != "approved":
            raise ValueError("audio job must be approved before TTS generation")
        now = _now()
        with self._transaction() as db:
            claimed = db.execute(
                """UPDATE marketing_audio_jobs
                SET status='running',started_at=?,failure_code=NULL,updated_at=?
                WHERE id=? AND user_id=? AND account_id=? AND status='approved'""",
                (now, now, job_id, user_id, account_id),
            ).rowcount
        if claimed != 1:
            return self.get(job_id=job_id, user_id=user_id, account_id=account_id)

        work_root = self.paths.config_dir.parent / "marketing-audio-jobs" / job_id
        work_root.mkdir(parents=True, exist_ok=True)
        requested_output = work_root / "voice.mp3"
        try:
            result = self._run_tts(job["script_text"], requested_output)
            output = Path(str(result.get("file_path") or "")).expanduser().resolve()
            if not result.get("success") or not output.is_file() or output.stat().st_size <= 0:
                raise RuntimeError(str(result.get("error") or "TTS provider produced no output"))
            provider = self._required(result.get("provider"), "provider", limit=100)
            mime_type = mimetypes.guess_type(output.name)[0] or "audio/mpeg"
            if not mime_type.startswith("audio/"):
                raise RuntimeError("TTS provider returned a non-audio file")
            receipt = {
                "version": TTS_JOB_VERSION,
                "job_id": job_id,
                "provider": provider,
                "script_sha256": job["script_sha256"],
                "character_count": len(job["script_text"]),
                "approval_ref": job["approval_ref"],
                "generated_at": _now(),
            }
            asset = self.media.import_generated_file(
                user_id=user_id,
                account_id=account_id,
                name=job["name"],
                media_type="audio",
                role="voice",
                path=output,
                mime_type=mime_type,
                provider=f"hermes_tts:{provider}",
                provider_asset_id=f"tts://{job_id}/voice",
                source_type="ai_generated",
                rights_status="generated",
                metadata={
                    "job_id": job_id,
                    "provider": provider,
                    "script_sha256": job["script_sha256"],
                },
                receipt=receipt,
            )
            settled = _now()
            with self._transaction() as db:
                db.execute(
                    """UPDATE marketing_audio_jobs
                    SET status='completed',provider=?,output_asset_id=?,receipt_json=?,
                        settled_at=?,updated_at=? WHERE id=? AND status='running'""",
                    (
                        provider, asset["id"],
                        json.dumps(receipt, ensure_ascii=False, sort_keys=True),
                        settled, settled, job_id,
                    ),
                )
        except Exception as exc:
            failed = _now()
            with self._transaction() as db:
                db.execute(
                    """UPDATE marketing_audio_jobs
                    SET status='failed',failure_code=?,settled_at=?,updated_at=?
                    WHERE id=? AND status='running'""",
                    (type(exc).__name__[:120], failed, failed, job_id),
                )
            raise
        finally:
            for child in work_root.glob("*"):
                if child.is_file():
                    child.unlink(missing_ok=True)
        return self.get(job_id=job_id, user_id=user_id, account_id=account_id)

    def get(self, *, job_id: str, user_id: str, account_id: str) -> dict[str, Any]:
        with self._connection() as db:
            row = db.execute(
                """SELECT * FROM marketing_audio_jobs
                WHERE id=? AND user_id=? AND account_id=?""",
                (job_id, user_id, account_id),
            ).fetchone()
        if row is None:
            raise KeyError("audio job not found in account scope")
        return _record(row)

    def _run_tts(self, text: str, output_path: Path) -> dict[str, Any]:
        if self._tts_runner is None:
            from tools.tts_tool import text_to_speech_tool

            raw = text_to_speech_tool(text=text, output_path=str(output_path))
        else:
            raw = self._tts_runner(text, str(output_path))
        try:
            value = json.loads(raw)
        except (TypeError, json.JSONDecodeError) as exc:
            raise RuntimeError("TTS provider returned an invalid result") from exc
        if not isinstance(value, dict):
            raise RuntimeError("TTS provider returned an invalid result")
        return value

    @staticmethod
    def _required(value: Any, field: str, *, limit: int = 256) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError(f"{field} is required")
        if len(text) > limit:
            raise ValueError(f"{field} must be at most {limit} characters")
        return text
