"""Durable faceless-video production owned by the native Hermes runtime."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from agent.marketing.data_paths import MarketingDataPaths
from agent.marketing.domains.content_assets import ContentAssetRepository
from agent.marketing.domains.media_assets import MediaAssetRepository
from agent.marketing.domains.storage import MarketingDomainRepository
from agent.marketing.intelligence.store import OperatingLoopRepository
from agent.marketing.domains.video_ir import (
    FFMPEG_RENDERER,
    build_render_plan,
    compile_ffmpeg_edl,
    normalize_video_ir,
    video_ir_from_edl,
)
from agent.marketing.domains.video_renderers import (
    RUNTIME_VERSION,
    VideoRendererRuntime,
)
from agent.marketing.domains.video_quality import VideoQualityAnalyzer


EDL_VERSION = "marketing.faceless_video.edl.v1"
RENDERER = FFMPEG_RENDERER
SCENE_ROUTER = "marketing_scene_router_v1"
PRODUCTION_STATUSES = {
    "prepared",
    "approved",
    "running",
    "completed",
    "failed",
    "archived",
}
_ALLOWED_VISUAL_ROLES = {"scene", "broll", "prop", "storyboard", "other"}
_ALLOWED_AUDIO_ROLES = {"voice", "music", "sfx", "other"}
_Runner = Callable[[list[str], Path], None]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _number(value: Any, field: str, *, minimum: float, maximum: float) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if result < minimum or result > maximum:
        raise ValueError(f"{field} must be between {minimum} and {maximum}")
    return result


def _integer(value: Any, field: str, *, minimum: int, maximum: int) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer") from exc
    if result < minimum or result > maximum:
        raise ValueError(f"{field} must be between {minimum} and {maximum}")
    return result


def _default_runner(command: list[str], log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("ab") as log:
        subprocess.run(
            command,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=log,
            timeout=900,
        )


class VideoProductionRepository(MarketingDomainRepository):
    """Prepare, execute and settle one immutable faceless-video render."""

    def __init__(
        self,
        paths: MarketingDataPaths | None = None,
        *,
        ffmpeg_path: str | None = None,
        ffprobe_path: str | None = None,
        runner: _Runner | None = None,
        renderer_runtime: VideoRendererRuntime | None = None,
        enabled_renderers: Iterable[str] | None = None,
    ):
        super().__init__(paths)
        self.media = MediaAssetRepository(self.paths)
        self.content = ContentAssetRepository(self.paths)
        self.ffmpeg_path = ffmpeg_path or shutil.which("ffmpeg") or ""
        self.ffprobe_path = ffprobe_path or shutil.which("ffprobe") or ""
        self.runner = runner or _default_runner
        self.quality = VideoQualityAnalyzer(
            ffmpeg_path=self.ffmpeg_path,
            ffprobe_path=self.ffprobe_path,
        )
        self.renderer_runtime = renderer_runtime or VideoRendererRuntime()
        if enabled_renderers is None:
            advanced = self.renderer_runtime.health()["enabled_renderers"]
            self.enabled_renderers = tuple([FFMPEG_RENDERER, *advanced])
        else:
            self.enabled_renderers = tuple(dict.fromkeys(enabled_renderers))
        self.work_root = self.paths.config_dir.parent / "marketing-video-renders"
        self.work_root.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def prepare(
        self,
        *,
        user_id: str,
        account_id: str,
        source_asset_id: str,
        edl: dict[str, Any] | None = None,
        video_ir: dict[str, Any] | None = None,
        renderer: str = RENDERER,
    ) -> dict[str, Any]:
        source = self.content.get(
            asset_id=source_asset_id,
            user_id=user_id,
            account_id=account_id,
        )
        source_content = source.get("content") or {}
        if source_content.get("_production_kind") != "faceless_video":
            raise ValueError("video production requires a faceless_video content asset")
        if source.get("status") in {"superseded", "approved", "published", "archived"}:
            raise ValueError("video production source asset is not current")
        if renderer != RENDERER:
            raise ValueError("renderer is not enabled in this product build")
        if (edl is None) == (video_ir is None):
            raise ValueError("provide exactly one of edl or video_ir")

        if video_ir is not None:
            normalized_ir = normalize_video_ir(video_ir)
            normalized_ir = self._validate_ir_assets(
                normalized_ir,
                user_id=user_id,
                account_id=account_id,
            )
            render_plan = build_render_plan(
                normalized_ir,
                enabled_renderers=self.enabled_renderers,
            )
            if render_plan["executable"] is not True:
                blocked = [
                    scene["scene_id"]
                    for scene in render_plan["scenes"]
                    if scene["status"] != "ready"
                ]
                raise ValueError(
                    "video_ir requires unavailable renderer capabilities for scenes: "
                    + ", ".join(blocked)
                )
            normalized = self._normalize_edl(
                self._compatibility_edl(normalized_ir),
                user_id=user_id,
                account_id=account_id,
            )
        else:
            normalized = self._normalize_edl(
                edl or {},
                user_id=user_id,
                account_id=account_id,
            )
            normalized_ir = video_ir_from_edl(normalized)
            render_plan = build_render_plan(
                normalized_ir,
                enabled_renderers=self.enabled_renderers,
            )
            normalized = self._normalize_edl(
                compile_ffmpeg_edl(normalized_ir, render_plan),
                user_id=user_id,
                account_id=account_id,
            )
        encoded = _json(normalized)
        encoded_ir = _json(normalized_ir)
        encoded_render_plan = _json(render_plan)
        # Preserve the v1 EDL idempotency key so an application upgrade cannot
        # create a second production for an already prepared legacy request.
        idempotency_payload = encoded if video_ir is None else encoded_ir
        idempotency_key = hashlib.sha256(
            (
                f"{user_id}\0{account_id}\0{source_asset_id}\0"
                f"{int(source.get('version') or 1)}\0{renderer}\0{idempotency_payload}"
            ).encode("utf-8")
        ).hexdigest()
        now = _now()
        production_id = f"video_production_{uuid.uuid4().hex}"
        with self._transaction() as db:
            existing = db.execute(
                "SELECT * FROM marketing_video_productions WHERE idempotency_key=?",
                (idempotency_key,),
            ).fetchone()
            if existing is not None:
                if not json.loads(existing["video_ir_json"] or "{}"):
                    db.execute(
                        """UPDATE marketing_video_productions
                        SET video_ir_json=?,render_plan_json=?,updated_at=?
                        WHERE id=?""",
                        (
                            encoded_ir,
                            encoded_render_plan,
                            now,
                            existing["id"],
                        ),
                    )
                    existing = db.execute(
                        "SELECT * FROM marketing_video_productions WHERE id=?",
                        (existing["id"],),
                    ).fetchone()
                return _record(existing)
            db.execute(
                """INSERT INTO marketing_video_productions
                (id,idempotency_key,user_id,account_id,source_asset_id,
                 source_asset_version,provider,status,edl_json,video_ir_json,
                 render_plan_json,voice_asset_id,
                 created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,'prepared',?,?,?,?,?,?)""",
                (
                    production_id,
                    idempotency_key,
                    user_id,
                    account_id,
                    source_asset_id,
                    int(source.get("version") or 1),
                    renderer,
                    encoded,
                    encoded_ir,
                    encoded_render_plan,
                    normalized.get("voice_asset_id"),
                    now,
                    now,
                ),
            )
        for asset_id in self._ir_asset_ids(normalized_ir):
            self.media.add_reference(
                asset_id=asset_id,
                user_id=user_id,
                owner_kind="video_production",
                owner_id=production_id,
                relation="render_input",
            )
        return self.get(
            production_id=production_id,
            user_id=user_id,
            account_id=account_id,
        )

    def approve(
        self,
        *,
        production_id: str,
        user_id: str,
        account_id: str,
        approval_ref: str,
        confirmed_by_user: bool,
    ) -> dict[str, Any]:
        if not confirmed_by_user:
            raise ValueError("explicit human render approval is required")
        approval = str(approval_ref or "").strip()
        if not approval or len(approval) > 500:
            raise ValueError("approval_ref is required")
        now = _now()
        with self._transaction() as db:
            row = db.execute(
                """SELECT status FROM marketing_video_productions
                WHERE id=? AND user_id=? AND account_id=?""",
                (production_id, user_id, account_id),
            ).fetchone()
            if row is None:
                raise KeyError("video production not found in account scope")
            if row["status"] in {"prepared", "failed"}:
                db.execute(
                    """UPDATE marketing_video_productions
                    SET status='approved',approval_ref=?,failure_code=NULL,
                        settled_at=NULL,updated_at=? WHERE id=?""",
                    (approval, now, production_id),
                )
            elif row["status"] not in {"approved", "running", "completed"}:
                raise ValueError(f"cannot approve video production in {row['status']}")
        return self.get(
            production_id=production_id,
            user_id=user_id,
            account_id=account_id,
        )

    def execute(
        self,
        *,
        production_id: str,
        user_id: str,
        account_id: str,
        session_id: str = "",
    ) -> dict[str, Any]:
        production = self.get(
            production_id=production_id,
            user_id=user_id,
            account_id=account_id,
        )
        if production["status"] == "completed":
            return production
        if production["status"] != "approved":
            raise ValueError("video production must be approved before rendering")
        if not self.ffmpeg_path or not self.ffprobe_path:
            raise RuntimeError(
                "ffmpeg and ffprobe are required for faceless-video rendering"
            )

        now = _now()
        with self._transaction() as db:
            claimed = db.execute(
                """UPDATE marketing_video_productions
                SET status='running',started_at=?,failure_code=NULL,updated_at=?
                WHERE id=? AND user_id=? AND account_id=? AND status='approved'""",
                (now, now, production_id, user_id, account_id),
            ).rowcount
        if claimed != 1:
            return self.get(
                production_id=production_id,
                user_id=user_id,
                account_id=account_id,
            )

        work_dir = self.work_root / production_id
        work_dir.mkdir(parents=True, exist_ok=True)
        try:
            output_path, technical = self._render(production, work_dir)
            canvas = production["video_ir"]["canvas"]
            quality = self.quality.analyze(
                output_path,
                expected_duration=float(production["edl"]["duration"]),
                expected_width=int(canvas["width"]),
                expected_height=int(canvas["height"]),
                audio_expected=bool(
                    production["edl"].get("voice_asset_id")
                    or production["edl"].get("music_asset_id")
                ),
            )
            technical["quality_assurance"] = quality
            receipt_summary = {
                "renderer": SCENE_ROUTER,
                "production_id": production_id,
                "source_asset_id": production["source_asset_id"],
                "source_asset_version": production["source_asset_version"],
                "edl_sha256": hashlib.sha256(
                    _json(production["edl"]).encode("utf-8")
                ).hexdigest(),
                "video_ir_sha256": production["video_ir"].get("ir_sha256"),
                "render_plan_sha256": production["render_plan"].get(
                    "render_plan_sha256"
                ),
                "input_asset_ids": self._ir_asset_ids(production["video_ir"]),
                "technical": technical,
            }
            final_media = self.media.import_generated_file(
                user_id=user_id,
                account_id=account_id,
                name=f"{production['source_asset_id']} final video",
                media_type="video",
                role="final_video",
                path=output_path,
                mime_type="video/mp4",
                provider="hermes_scene_router",
                provider_asset_id=f"production://{production_id}/final",
                source_type="derived",
                rights_status="inherited",
                metadata=technical,
                receipt=receipt_summary,
            )
            self.media.add_reference(
                asset_id=final_media["id"],
                user_id=user_id,
                owner_kind="video_production",
                owner_id=production_id,
                relation="render_output",
            )
            checkpoint_at = _now()
            with self._transaction() as db:
                db.execute(
                    """UPDATE marketing_video_productions
                    SET final_video_asset_id=?,updated_at=?
                    WHERE id=? AND status='running'""",
                    (final_media["id"], checkpoint_at, production_id),
                )
            output_asset = self.content.create_faceless_render_revision(
                parent_asset_id=production["source_asset_id"],
                user_id=user_id,
                account_id=account_id,
                production={
                    "version": "marketing.faceless_video.production.v1",
                    "production_id": production_id,
                    "renderer": SCENE_ROUTER,
                    "video_ir": production["video_ir"],
                    "render_plan": production["render_plan"],
                    "edl": production["edl"],
                    "final_video_asset_id": final_media["id"],
                    "technical": technical,
                },
            )
            checkpoint_at = _now()
            with self._transaction() as db:
                db.execute(
                    """UPDATE marketing_video_productions
                    SET output_asset_id=?,updated_at=?
                    WHERE id=? AND status='running'""",
                    (output_asset["id"], checkpoint_at, production_id),
                )
            receipt = OperatingLoopRepository(self.paths).create_receipt(
                source_kind="faceless_video_render",
                source_id=production_id,
                receipt_type="render_complete",
                user_id=user_id,
                account_id=account_id,
                platform=output_asset.get("platform"),
                plan_id=(output_asset.get("content") or {}).get("_production_plan_id"),
                session_id=session_id,
                summary=receipt_summary
                | {
                    "final_video_asset_id": final_media["id"],
                    "output_asset_id": output_asset["id"],
                },
            )
            settled = _now()
            with self._transaction() as db:
                db.execute(
                    """UPDATE marketing_video_productions
                    SET status='completed',final_video_asset_id=?,output_asset_id=?,
                        receipt_json=?,settled_at=?,updated_at=?
                    WHERE id=? AND status='running'""",
                    (
                        final_media["id"],
                        output_asset["id"],
                        _json(receipt),
                        settled,
                        settled,
                        production_id,
                    ),
                )
        except Exception as exc:
            failed_at = _now()
            with self._transaction() as db:
                db.execute(
                    """UPDATE marketing_video_productions
                    SET status='failed',failure_code=?,settled_at=?,updated_at=?
                    WHERE id=? AND status='running'""",
                    (type(exc).__name__[:120], failed_at, failed_at, production_id),
                )
            raise
        return self.get(
            production_id=production_id,
            user_id=user_id,
            account_id=account_id,
        )

    def execute_ffmpeg(
        self,
        *,
        production_id: str,
        user_id: str,
        account_id: str,
        session_id: str = "",
    ) -> dict[str, Any]:
        """Compatibility alias for productions created before scene routing."""
        return self.execute(
            production_id=production_id,
            user_id=user_id,
            account_id=account_id,
            session_id=session_id,
        )

    def get(
        self, *, production_id: str, user_id: str, account_id: str
    ) -> dict[str, Any]:
        with self._connection() as db:
            row = db.execute(
                """SELECT * FROM marketing_video_productions
                WHERE id=? AND user_id=? AND account_id=?""",
                (production_id, user_id, account_id),
            ).fetchone()
        if row is None:
            raise KeyError("video production not found in account scope")
        return _record(row)

    def archive(
        self,
        *,
        production_id: str,
        user_id: str,
        account_id: str,
        confirmed: bool,
    ) -> dict[str, Any]:
        """Soft-archive an unfinished production and its draft content records."""

        if confirmed is not True:
            raise ValueError("explicit archive confirmation is required")
        now = _now()
        with self._transaction() as db:
            row = db.execute(
                """SELECT * FROM marketing_video_productions
                WHERE id=? AND user_id=? AND account_id=?""",
                (production_id, user_id, account_id),
            ).fetchone()
            if row is None:
                raise KeyError("video production not found in account scope")
            if row["status"] == "archived":
                return _record(row)
            if row["status"] == "running":
                raise ValueError("a running video production cannot be archived")
            if row["status"] not in {"prepared", "approved", "completed", "failed"}:
                raise ValueError(
                    f"video production cannot be archived from {row['status']}"
                )
            if row["status"] == "completed" and row["output_asset_id"]:
                output = db.execute(
                    """SELECT human_review_status FROM content_assets
                    WHERE id=? AND user_id=? AND account_id=?""",
                    (row["output_asset_id"], user_id, account_id),
                ).fetchone()
                if output is not None and output["human_review_status"] == "accepted":
                    raise ValueError("an accepted video production is not a draft")
            db.execute(
                """UPDATE marketing_video_productions
                SET status='archived',archived_from_status=?,archived_at=?,updated_at=?
                WHERE id=? AND user_id=? AND account_id=?""",
                (row["status"], now, now, production_id, user_id, account_id),
            )
            _archive_related_content(
                db,
                asset_ids=(row["source_asset_id"], row["output_asset_id"]),
                user_id=user_id,
                account_id=account_id,
                now=now,
            )
        return self.get(
            production_id=production_id,
            user_id=user_id,
            account_id=account_id,
        )

    def restore_archived(
        self,
        *,
        production_id: str,
        user_id: str,
        account_id: str,
    ) -> dict[str, Any]:
        """Restore an archived production and its linked content drafts."""

        now = _now()
        with self._transaction() as db:
            row = db.execute(
                """SELECT * FROM marketing_video_productions
                WHERE id=? AND user_id=? AND account_id=?""",
                (production_id, user_id, account_id),
            ).fetchone()
            if row is None:
                raise KeyError("video production not found in account scope")
            if row["status"] != "archived":
                raise ValueError("only an archived video production can be restored")
            restored_status = str(row["archived_from_status"] or "prepared")
            if restored_status not in {"prepared", "approved", "completed", "failed"}:
                restored_status = "prepared"
            db.execute(
                """UPDATE marketing_video_productions
                SET status=?,archived_from_status='',archived_at=NULL,updated_at=?
                WHERE id=? AND user_id=? AND account_id=?""",
                (restored_status, now, production_id, user_id, account_id),
            )
            _restore_related_content(
                db,
                asset_ids=(row["source_asset_id"], row["output_asset_id"]),
                user_id=user_id,
                account_id=account_id,
                now=now,
            )
        return self.get(
            production_id=production_id,
            user_id=user_id,
            account_id=account_id,
        )

    def list(
        self,
        *,
        user_id: str,
        account_id: str,
        status: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        if status and status not in PRODUCTION_STATUSES:
            raise ValueError("unsupported video production status")
        safe_limit = max(1, min(int(limit), 50))
        query = (
            "SELECT * FROM marketing_video_productions WHERE user_id=? AND account_id=?"
        )
        params: list[Any] = [user_id, account_id]
        if status:
            query += " AND status=?"
            params.append(status)
        else:
            query += " AND status!='archived'"
        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(safe_limit)
        with self._connection() as db:
            rows = db.execute(query, params).fetchall()
        return {
            "user_id": user_id,
            "account_id": account_id,
            "productions": [_record(row) for row in rows],
            "total": len(rows),
        }

    def list_review_summaries(
        self,
        *,
        user_id: str,
        account_id: str,
        status: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Return bounded production summaries for the desktop workbench."""

        result = self.list(
            user_id=user_id,
            account_id=account_id,
            status=status,
            limit=limit,
        )
        summaries = []
        for production in result["productions"]:
            try:
                source = self.content.get(
                    asset_id=production["source_asset_id"],
                    user_id=user_id,
                    account_id=account_id,
                )
            except KeyError:
                source = {}
            output = {}
            if production.get("output_asset_id"):
                try:
                    output = self.content.get(
                        asset_id=production["output_asset_id"],
                        user_id=user_id,
                        account_id=account_id,
                    )
                except KeyError:
                    output = {}
            summaries.append(self._review_summary(production, source, output))
        return {
            "user_id": user_id,
            "account_id": account_id,
            "productions": summaries,
            "total": len(summaries),
        }

    def get_review_projection(
        self,
        *,
        production_id: str,
        user_id: str,
        account_id: str,
    ) -> dict[str, Any]:
        """Load one account-scoped production with review-safe media metadata."""

        production = self.get(
            production_id=production_id,
            user_id=user_id,
            account_id=account_id,
        )
        source = self.content.get(
            asset_id=production["source_asset_id"],
            user_id=user_id,
            account_id=account_id,
        )
        output = None
        if production.get("output_asset_id"):
            output = self.content.get(
                asset_id=production["output_asset_id"],
                user_id=user_id,
                account_id=account_id,
            )

        asset_ids = self._ir_asset_ids(production.get("video_ir") or {})
        if production.get("final_video_asset_id"):
            asset_ids.append(production["final_video_asset_id"])
        media_assets = []
        for asset_id in dict.fromkeys(asset_ids):
            try:
                asset = self.media.get(asset_id=asset_id, user_id=user_id)
            except KeyError:
                continue
            if asset.get("account_id") not in {None, account_id}:
                continue
            media_assets.append(
                {
                    "id": asset["id"],
                    "name": asset["name"],
                    "media_type": asset["media_type"],
                    "role": asset["role"],
                    "mime_type": asset["mime_type"],
                    "rights_status": asset["rights_status"],
                    "source_type": asset["source_type"],
                    "provider": asset["provider"],
                    "size_bytes": asset["size_bytes"],
                    "playback_path": self.media.resolve_local_path(
                        asset_id=asset_id,
                        user_id=user_id,
                    ),
                }
            )
        return {
            "summary": self._review_summary(production, source, output or {}),
            "production": {
                key: value
                for key, value in production.items()
                if key not in {"idempotency_key", "user_id", "account_id"}
            },
            "source_asset": source,
            "output_asset": output,
            "media_assets": media_assets,
        }

    @staticmethod
    def _review_summary(
        production: dict[str, Any],
        source: dict[str, Any],
        output: dict[str, Any],
    ) -> dict[str, Any]:
        video_ir = production.get("video_ir") or {}
        canvas = video_ir.get("canvas") or {}
        scenes = video_ir.get("scenes") or []
        render_scenes = (production.get("render_plan") or {}).get("scenes") or []
        duration = round(
            sum(float(scene.get("duration") or 0) for scene in scenes),
            3,
        )
        renderers = list(
            dict.fromkeys(
                str(scene.get("renderer") or "")
                for scene in render_scenes
                if scene.get("renderer")
            )
        )
        return {
            "id": production["id"],
            "source_asset_id": production["source_asset_id"],
            "output_asset_id": production.get("output_asset_id"),
            "final_video_asset_id": production.get("final_video_asset_id"),
            "title": source.get("title") or source.get("topic") or "未命名素材视频",
            "status": production["status"],
            "failure_code": production.get("failure_code"),
            "canvas": {
                "width": int(canvas.get("width") or 1080),
                "height": int(canvas.get("height") or 1920),
                "fps": int(canvas.get("fps") or 30),
            },
            "duration": duration,
            "scene_count": len(scenes),
            "renderers": renderers,
            "human_review_status": output.get("human_review_status") or "pending",
            "created_at": production["created_at"],
            "updated_at": production["updated_at"],
            "settled_at": production.get("settled_at"),
        }

    def _normalize_edl(
        self,
        edl: dict[str, Any],
        *,
        user_id: str,
        account_id: str,
    ) -> dict[str, Any]:
        if not isinstance(edl, dict):
            raise ValueError("edl must be an object")
        if edl.get("version") != EDL_VERSION:
            raise ValueError(f"edl version must be {EDL_VERSION}")
        width = _integer(edl.get("width", 1080), "width", minimum=240, maximum=3840)
        height = _integer(edl.get("height", 1920), "height", minimum=240, maximum=3840)
        fps = _integer(edl.get("fps", 30), "fps", minimum=15, maximum=60)
        clips = edl.get("clips")
        if not isinstance(clips, list) or not clips or len(clips) > 100:
            raise ValueError("edl requires between 1 and 100 clips")
        normalized_clips = []
        total_duration = 0.0
        for index, clip in enumerate(clips):
            if not isinstance(clip, dict):
                raise ValueError("each edl clip must be an object")
            asset = self._require_media(
                clip.get("media_asset_id"),
                user_id=user_id,
                account_id=account_id,
                roles=_ALLOWED_VISUAL_ROLES,
                media_types={"image", "video"},
            )
            duration = _number(
                clip.get("duration"),
                f"clips[{index}].duration",
                minimum=0.1,
                maximum=120.0,
            )
            source_in = _number(
                clip.get("source_in", 0),
                f"clips[{index}].source_in",
                minimum=0.0,
                maximum=86_400.0,
            )
            normalized_clips.append({
                "media_asset_id": asset["id"],
                "source_in": round(source_in, 3),
                "duration": round(duration, 3),
                "fit": self._normalize_fit(
                    clip.get("fit", "cover"),
                    f"clips[{index}].fit",
                ),
            })
            total_duration += duration
        if total_duration > 600:
            raise ValueError("edl total duration must not exceed 600 seconds")

        result: dict[str, Any] = {
            "version": EDL_VERSION,
            "width": width,
            "height": height,
            "fps": fps,
            "clips": normalized_clips,
            "duration": round(total_duration, 3),
        }
        for field, role in (("voice_asset_id", "voice"), ("music_asset_id", "music")):
            value = str(edl.get(field) or "").strip()
            if value:
                result[field] = self._require_media(
                    value,
                    user_id=user_id,
                    account_id=account_id,
                    roles={role, "other"},
                    media_types={"audio"},
                )["id"]
        captions = edl.get("captions") or []
        if not isinstance(captions, list) or len(captions) > 500:
            raise ValueError("captions must be a bounded list")
        normalized_captions = []
        for index, cue in enumerate(captions):
            if not isinstance(cue, dict):
                raise ValueError("each caption cue must be an object")
            start = _number(
                cue.get("start"), f"captions[{index}].start", minimum=0, maximum=600
            )
            end = _number(
                cue.get("end"), f"captions[{index}].end", minimum=0, maximum=600
            )
            text = str(cue.get("text") or "").strip()
            if (
                end <= start
                or end > total_duration + 0.05
                or not text
                or len(text) > 200
            ):
                raise ValueError("caption cue timing or text is invalid")
            normalized_captions.append({
                "start": round(start, 3),
                "end": round(end, 3),
                "text": text,
            })
        result["captions"] = normalized_captions
        return result

    def _validate_ir_assets(
        self,
        video_ir: dict[str, Any],
        *,
        user_id: str,
        account_id: str,
    ) -> dict[str, Any]:
        for scene in video_ir["scenes"]:
            for visual in scene["visuals"]:
                self._require_media(
                    visual["media_asset_id"],
                    user_id=user_id,
                    account_id=account_id,
                    roles=_ALLOWED_VISUAL_ROLES,
                    media_types={"image", "video"},
                )
        for field, role in (("voice_asset_id", "voice"), ("music_asset_id", "music")):
            asset_id = video_ir["audio"].get(field)
            if asset_id:
                self._require_media(
                    asset_id,
                    user_id=user_id,
                    account_id=account_id,
                    roles={role, "other"},
                    media_types={"audio"},
                )
        return video_ir

    @staticmethod
    def _compatibility_edl(video_ir: dict[str, Any]) -> dict[str, Any]:
        """Keep a bounded legacy projection while Video IR remains authoritative."""
        result = {
            "version": EDL_VERSION,
            "width": video_ir["canvas"]["width"],
            "height": video_ir["canvas"]["height"],
            "fps": video_ir["canvas"]["fps"],
            "clips": [
                {
                    "media_asset_id": scene["visuals"][0]["media_asset_id"],
                    "source_in": scene["visuals"][0]["source_in"],
                    "duration": scene["duration"],
                    "fit": scene["visuals"][0]["fit"],
                }
                for scene in video_ir["scenes"]
            ],
            "captions": video_ir["captions"],
        }
        for field in ("voice_asset_id", "music_asset_id"):
            if video_ir["audio"].get(field):
                result[field] = video_ir["audio"][field]
        return result

    @staticmethod
    def _normalize_fit(value: Any, field: str) -> str:
        result = str(value or "cover").strip().lower()
        if result not in {"cover", "contain"}:
            raise ValueError(f"{field} must be cover or contain")
        return result

    def _require_media(
        self,
        asset_id: Any,
        *,
        user_id: str,
        account_id: str,
        roles: set[str],
        media_types: set[str],
    ) -> dict[str, Any]:
        asset = self.media.get(asset_id=str(asset_id or "").strip(), user_id=user_id)
        if asset.get("account_id") not in {None, account_id}:
            raise ValueError("media asset belongs to another account")
        if asset.get("role") not in roles or asset.get("media_type") not in media_types:
            raise ValueError("media asset is incompatible with this EDL slot")
        if asset.get("rights_status") not in {
            "user_confirmed",
            "provider_verified",
            "generated",
            "licensed",
            "inherited",
        }:
            raise ValueError("media asset rights are not approved")
        if not asset.get("local_path"):
            raise ValueError("media asset must be materialized locally before render")
        return asset

    @staticmethod
    def _edl_asset_ids(edl: dict[str, Any]) -> list[str]:
        result = [str(clip["media_asset_id"]) for clip in edl.get("clips") or []]
        result.extend(
            str(edl[field])
            for field in ("voice_asset_id", "music_asset_id")
            if edl.get(field)
        )
        return list(dict.fromkeys(result))

    @staticmethod
    def _ir_asset_ids(video_ir: dict[str, Any]) -> list[str]:
        result = [
            str(visual["media_asset_id"])
            for scene in video_ir.get("scenes") or []
            for visual in scene.get("visuals") or []
        ]
        result.extend(
            str(video_ir.get("audio", {}).get(field))
            for field in ("voice_asset_id", "music_asset_id")
            if video_ir.get("audio", {}).get(field)
        )
        return list(dict.fromkeys(result))

    def _asset_path(self, asset_id: str, *, user_id: str) -> Path:
        asset = self.media.get(asset_id=asset_id, user_id=user_id)
        target = (self.media.root / asset["local_path"]).resolve()
        if self.media.root.resolve() not in target.parents or not target.is_file():
            raise ValueError("media asset file is unavailable")
        return target

    def _render(
        self, production: dict[str, Any], work_dir: Path
    ) -> tuple[Path, dict[str, Any]]:
        work_dir.mkdir(parents=True, exist_ok=True)
        edl = production["edl"]
        width, height, fps = edl["width"], edl["height"], edl["fps"]
        log_path = work_dir / "ffmpeg.log"
        log_path.unlink(missing_ok=True)
        video_ir = normalize_video_ir(production["video_ir"])
        scene_plans = {
            item["scene_id"]: item for item in production["render_plan"]["scenes"]
        }
        segment_paths: list[Path] = []
        scene_outputs: list[dict[str, Any]] = []
        cache_root = self.work_root / "scene-cache"
        cache_root.mkdir(parents=True, exist_ok=True)
        for index, scene in enumerate(video_ir["scenes"]):
            plan = scene_plans.get(scene["id"])
            if not plan or plan.get("scene_sha256") != scene["scene_sha256"]:
                raise RuntimeError(f"render plan is stale for scene {scene['id']}")
            renderer = plan.get("renderer")
            if not renderer:
                raise RuntimeError(f"scene renderer is unavailable: {scene['id']}")
            cache_key = hashlib.sha256(
                _json({
                    "scene_sha256": scene["scene_sha256"],
                    "renderer": renderer,
                    "runtime_version": (
                        RUNTIME_VERSION
                        if renderer == FFMPEG_RENDERER
                        else self.renderer_runtime.health()["runtime_sha256"]
                    ),
                    "canvas": video_ir["canvas"],
                }).encode("utf-8")
            ).hexdigest()
            cache_path = cache_root / renderer / f"{cache_key}.mp4"
            target = work_dir / f"segment-{index:03d}.mp4"
            cache_hit = self._valid_cached_scene(
                cache_path,
                width=width,
                height=height,
                duration=float(scene["duration"]),
            )
            renderer_evidence: dict[str, Any] = {}
            if not cache_hit:
                scene_work = work_dir / f"scene-{index:03d}-{scene['id']}"
                scene_work.mkdir(parents=True, exist_ok=True)
                raw_path = scene_work / "raw.mp4"
                if renderer == FFMPEG_RENDERER:
                    self._render_ffmpeg_scene(
                        scene=scene,
                        user_id=production["user_id"],
                        canvas=video_ir["canvas"],
                        output_path=raw_path,
                        log_path=log_path,
                    )
                    renderer_evidence = {
                        "runtime_version": RUNTIME_VERSION,
                        "renderer": renderer,
                        "scene_sha256": scene["scene_sha256"],
                    }
                else:
                    visual_assets = []
                    for visual in scene["visuals"]:
                        asset = self.media.get(
                            asset_id=visual["media_asset_id"],
                            user_id=production["user_id"],
                        )
                        visual_assets.append({
                            "path": self._asset_path(
                                visual["media_asset_id"],
                                user_id=production["user_id"],
                            ),
                            "media_type": asset["media_type"],
                        })
                    renderer_evidence = self.renderer_runtime.render_scene(
                        renderer=renderer,
                        scene=scene,
                        canvas=video_ir["canvas"],
                        visual_assets=visual_assets,
                        work_dir=scene_work,
                        output_path=raw_path,
                    )
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                normalized_path = cache_path.with_name(
                    f".{cache_path.stem}-{uuid.uuid4().hex}.mp4"
                )
                self._normalize_scene_video(
                    source_path=raw_path,
                    output_path=normalized_path,
                    width=width,
                    height=height,
                    fps=fps,
                    duration=float(scene["duration"]),
                    log_path=log_path,
                )
                os.replace(normalized_path, cache_path)
            shutil.copy2(cache_path, target)
            segment_paths.append(target)
            scene_technical = self._probe(target)
            scene_outputs.append({
                "scene_id": scene["id"],
                "scene_sha256": scene["scene_sha256"],
                "renderer": renderer,
                "cache_key": cache_key,
                "cache_hit": cache_hit,
                "output_sha256": scene_technical["sha256"],
                "duration_seconds": scene_technical["duration_seconds"],
                "renderer_evidence": renderer_evidence,
            })

        concat_file = work_dir / "concat.txt"
        concat_file.write_text(
            "".join(f"file '{path.as_posix()}'\n" for path in segment_paths),
            encoding="utf-8",
        )
        base_path = work_dir / "base.mp4"
        self.runner(
            [
                self.ffmpeg_path,
                "-y",
                "-hide_banner",
                "-loglevel",
                "warning",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_file),
                "-c",
                "copy",
                str(base_path),
            ],
            log_path,
        )

        visual_path = base_path
        if edl.get("captions"):
            srt_path = work_dir / "captions.srt"
            srt_path.write_text(_srt(edl["captions"]), encoding="utf-8")
            captioned = work_dir / "captioned.mp4"
            escaped = (
                str(srt_path).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
            )
            self.runner(
                [
                    self.ffmpeg_path,
                    "-y",
                    "-hide_banner",
                    "-loglevel",
                    "warning",
                    "-i",
                    str(base_path),
                    "-vf",
                    (
                        f"subtitles='{escaped}':force_style="
                        "'FontName=Sans,FontSize=18,Bold=1,Outline=2,"
                        "Alignment=2,MarginV=90'"
                    ),
                    "-an",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "veryfast",
                    "-crf",
                    "20",
                    "-pix_fmt",
                    "yuv420p",
                    str(captioned),
                ],
                log_path,
            )
            visual_path = captioned

        output_path = work_dir / "final.mp4"
        self._mux_audio(
            production=production,
            visual_path=visual_path,
            output_path=output_path,
            duration=float(edl["duration"]),
            log_path=log_path,
        )
        technical = self._probe(output_path) | {"scene_outputs": scene_outputs}
        if abs(float(technical["duration_seconds"]) - float(edl["duration"])) > 0.12:
            raise RuntimeError("rendered duration does not match the approved EDL")
        if technical["width"] != width or technical["height"] != height:
            raise RuntimeError("rendered dimensions do not match the approved EDL")
        return output_path, technical

    def _render_ffmpeg_scene(
        self,
        *,
        scene: dict[str, Any],
        user_id: str,
        canvas: dict[str, Any],
        output_path: Path,
        log_path: Path,
    ) -> None:
        if len(scene["visuals"]) != 1:
            raise ValueError("FFmpeg scenes require exactly one visual")
        visual = scene["visuals"][0]
        source = self._asset_path(visual["media_asset_id"], user_id=user_id)
        asset = self.media.get(asset_id=visual["media_asset_id"], user_id=user_id)
        input_args = (
            ["-loop", "1", "-i", str(source)]
            if asset["media_type"] == "image"
            else ["-ss", f"{visual['source_in']:.3f}", "-i", str(source)]
        )
        width, height, fps = canvas["width"], canvas["height"], canvas["fps"]
        visual_filter = (
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},setsar=1,fps={fps}"
            if visual["fit"] == "cover"
            else (
                f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,"
                f"setsar=1,fps={fps}"
            )
        )
        self.runner(
            [
                self.ffmpeg_path,
                "-y",
                "-hide_banner",
                "-loglevel",
                "warning",
                *input_args,
                "-t",
                f"{scene['duration']:.3f}",
                "-an",
                "-vf",
                visual_filter,
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "20",
                "-pix_fmt",
                "yuv420p",
                "-g",
                str(fps),
                "-keyint_min",
                str(fps),
                "-movflags",
                "+faststart",
                str(output_path),
            ],
            log_path,
        )

    def _normalize_scene_video(
        self,
        *,
        source_path: Path,
        output_path: Path,
        width: int,
        height: int,
        fps: int,
        duration: float,
        log_path: Path,
    ) -> None:
        self.runner(
            [
                self.ffmpeg_path,
                "-y",
                "-hide_banner",
                "-loglevel",
                "warning",
                "-i",
                str(source_path),
                "-t",
                f"{duration:.3f}",
                "-an",
                "-vf",
                (
                    f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                    f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,"
                    f"setsar=1,fps={fps},format=yuv420p"
                ),
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "20",
                "-g",
                str(fps),
                "-keyint_min",
                str(fps),
                "-movflags",
                "+faststart",
                str(output_path),
            ],
            log_path,
        )

    def _valid_cached_scene(
        self,
        path: Path,
        *,
        width: int,
        height: int,
        duration: float,
    ) -> bool:
        if not path.is_file():
            return False
        try:
            technical = self._probe(path)
        except (OSError, ValueError, subprocess.SubprocessError):
            path.unlink(missing_ok=True)
            return False
        valid = (
            technical["width"] == width
            and technical["height"] == height
            and abs(float(technical["duration_seconds"]) - duration) <= 0.12
        )
        if not valid:
            path.unlink(missing_ok=True)
        return valid

    def _mux_audio(
        self,
        *,
        production: dict[str, Any],
        visual_path: Path,
        output_path: Path,
        duration: float,
        log_path: Path,
    ) -> None:
        edl = production["edl"]
        command = [
            self.ffmpeg_path,
            "-y",
            "-hide_banner",
            "-loglevel",
            "warning",
            "-i",
            str(visual_path),
        ]
        filters: list[str] = []
        if edl.get("voice_asset_id"):
            command.extend([
                "-i",
                str(
                    self._asset_path(
                        edl["voice_asset_id"], user_id=production["user_id"]
                    )
                ),
            ])
            filters.append(f"[1:a]apad,atrim=0:{duration:.3f}[voice]")
        if edl.get("music_asset_id"):
            command.extend([
                "-stream_loop",
                "-1",
                "-i",
                str(
                    self._asset_path(
                        edl["music_asset_id"], user_id=production["user_id"]
                    )
                ),
            ])
            music_index = 2 if edl.get("voice_asset_id") else 1
            filters.append(
                f"[{music_index}:a]volume=0.18,afade=t=out:st={max(0, duration - 0.5):.3f}:d=0.5,"
                f"atrim=0:{duration:.3f}[music]"
            )
        if edl.get("voice_asset_id") and edl.get("music_asset_id"):
            filters.append(
                "[voice][music]amix=inputs=2:duration=longest:normalize=0[aout]"
            )
        elif edl.get("voice_asset_id"):
            filters.append("[voice]anull[aout]")
        elif edl.get("music_asset_id"):
            filters.append("[music]anull[aout]")
        else:
            command.extend([
                "-f",
                "lavfi",
                "-t",
                f"{duration:.3f}",
                "-i",
                "anullsrc=r=48000:cl=stereo",
            ])
            filters.append("[1:a]anull[aout]")
        command.extend([
            "-filter_complex",
            ";".join(filters),
            "-map",
            "0:v:0",
            "-map",
            "[aout]",
            "-t",
            f"{duration:.3f}",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "48000",
            "-movflags",
            "+faststart",
            str(output_path),
        ])
        self.runner(command, log_path)

    def _probe(self, path: Path) -> dict[str, Any]:
        result = subprocess.run(
            [
                self.ffprobe_path,
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=codec_name,width,height,r_frame_rate,pix_fmt",
                "-show_entries",
                "format=duration,size",
                "-of",
                "json",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        payload = json.loads(result.stdout)
        stream = (payload.get("streams") or [{}])[0]
        format_info = payload.get("format") or {}
        return {
            "duration_seconds": round(float(format_info.get("duration") or 0), 3),
            "size_bytes": int(format_info.get("size") or path.stat().st_size),
            "codec": stream.get("codec_name"),
            "width": int(stream.get("width") or 0),
            "height": int(stream.get("height") or 0),
            "frame_rate": stream.get("r_frame_rate"),
            "pixel_format": stream.get("pix_fmt"),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }

    def _ensure_schema(self) -> None:
        with self._connection() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS marketing_video_productions (
                    id TEXT PRIMARY KEY,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    user_id TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    source_asset_id TEXT NOT NULL REFERENCES content_assets(id),
                    source_asset_version INTEGER NOT NULL,
                    provider TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'prepared',
                    edl_json TEXT NOT NULL,
                    video_ir_json TEXT NOT NULL DEFAULT '{}',
                    render_plan_json TEXT NOT NULL DEFAULT '{}',
                    approval_ref TEXT,
                    voice_asset_id TEXT REFERENCES media_asset_library(id),
                    final_video_asset_id TEXT REFERENCES media_asset_library(id),
                    output_asset_id TEXT REFERENCES content_assets(id),
                    receipt_json TEXT NOT NULL DEFAULT '{}',
                    failure_code TEXT,
                    archived_from_status TEXT NOT NULL DEFAULT '',
                    archived_at TEXT,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    settled_at TEXT,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_video_production_scope
                    ON marketing_video_productions(user_id,account_id,status,updated_at);
                """
            )
            columns = {
                row["name"]
                for row in db.execute("PRAGMA table_info(marketing_video_productions)")
            }
            for column in ("video_ir_json", "render_plan_json"):
                if column not in columns:
                    db.execute(
                        f"ALTER TABLE marketing_video_productions "
                        f"ADD COLUMN {column} TEXT NOT NULL DEFAULT '{{}}'"
                    )
            if "archived_from_status" not in columns:
                db.execute(
                    """ALTER TABLE marketing_video_productions
                    ADD COLUMN archived_from_status TEXT NOT NULL DEFAULT ''"""
                )
            if "archived_at" not in columns:
                db.execute(
                    """ALTER TABLE marketing_video_productions
                    ADD COLUMN archived_at TEXT"""
                )


def _content_plan_id(content_json: str) -> str:
    try:
        content = json.loads(content_json or "{}")
    except (TypeError, ValueError):
        return ""
    if not isinstance(content, dict):
        return ""
    return str(content.get("_production_plan_id") or "").strip()


def _archive_related_content(
    db: sqlite3.Connection,
    *,
    asset_ids: Iterable[str | None],
    user_id: str,
    account_id: str,
    now: str,
) -> None:
    for asset_id in dict.fromkeys(item for item in asset_ids if item):
        row = db.execute(
            """SELECT status,content_json FROM content_assets
            WHERE id=? AND user_id=? AND account_id=?""",
            (asset_id, user_id, account_id),
        ).fetchone()
        if row is None or row["status"] not in {"draft", "review_ready"}:
            continue
        db.execute(
            """UPDATE content_assets
            SET status='archived',archived_from_status=?,archived_at=?,updated_at=?
            WHERE id=? AND user_id=? AND account_id=?""",
            (row["status"], now, now, asset_id, user_id, account_id),
        )
        plan_id = _content_plan_id(row["content_json"])
        if plan_id:
            db.execute(
                """UPDATE content_production_plans
                SET status='archived',updated_at=?
                WHERE id=? AND user_id=? AND account_id=?""",
                (now, plan_id, user_id, account_id),
            )


def _restore_related_content(
    db: sqlite3.Connection,
    *,
    asset_ids: Iterable[str | None],
    user_id: str,
    account_id: str,
    now: str,
) -> None:
    for asset_id in dict.fromkeys(item for item in asset_ids if item):
        row = db.execute(
            """SELECT status,archived_from_status,content_json FROM content_assets
            WHERE id=? AND user_id=? AND account_id=?""",
            (asset_id, user_id, account_id),
        ).fetchone()
        if row is None or row["status"] != "archived":
            continue
        restored_status = str(row["archived_from_status"] or "draft")
        if restored_status not in {"draft", "review_ready"}:
            restored_status = "draft"
        db.execute(
            """UPDATE content_assets
            SET status=?,archived_from_status='',archived_at=NULL,updated_at=?
            WHERE id=? AND user_id=? AND account_id=?""",
            (restored_status, now, asset_id, user_id, account_id),
        )
        plan_id = _content_plan_id(row["content_json"])
        if plan_id:
            db.execute(
                """UPDATE content_production_plans
                SET status=?,updated_at=?
                WHERE id=? AND user_id=? AND account_id=?""",
                (
                    "review_ready"
                    if restored_status == "review_ready"
                    else "draft_created",
                    now,
                    plan_id,
                    user_id,
                    account_id,
                ),
            )


def _timestamp(value: float) -> str:
    milliseconds = int(round(value * 1000))
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    seconds, milliseconds = divmod(milliseconds, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def _srt(cues: list[dict[str, Any]]) -> str:
    blocks = []
    for index, cue in enumerate(cues, start=1):
        text = str(cue["text"]).replace("\r", " ").strip()
        blocks.append(
            f"{index}\n{_timestamp(float(cue['start']))} --> "
            f"{_timestamp(float(cue['end']))}\n{text}\n"
        )
    return "\n".join(blocks)


def _record(row: sqlite3.Row) -> dict[str, Any]:
    value = dict(row)
    value["edl"] = json.loads(value.pop("edl_json"))
    value["video_ir"] = json.loads(value.pop("video_ir_json", "{}") or "{}")
    value["render_plan"] = json.loads(value.pop("render_plan_json", "{}") or "{}")
    value["receipt"] = json.loads(value.pop("receipt_json") or "{}")
    return value
