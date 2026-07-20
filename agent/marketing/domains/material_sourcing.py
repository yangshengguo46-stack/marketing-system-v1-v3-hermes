"""Licensed material discovery and selection owned by Hermes state."""

from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from agent.marketing.data_paths import MarketingDataPaths
from agent.marketing.domains.media_assets import MediaAssetRepository
from agent.marketing.domains.storage import MarketingDomainRepository
from agent.marketing.providers.materials import (
    ensure_default_material_providers,
    get_material_provider,
    list_material_providers,
)


_ROLES = {"scene", "broll", "prop", "storyboard", "other"}
_ORIENTATIONS = {"", "landscape", "portrait", "square"}
_MEDIA_TYPES = {"either", "image", "video"}
_FRAME_LINE = re.compile(
    r"^- `(?P<path>[^`]+)` \(t=(?P<minutes>\d+):(?P<seconds>\d+), reason=(?P<reason>[^)]+)\)$"
)
_MAX_CAPTURE_SECONDS = 30 * 60
_MAX_SOURCE_BYTES = 500 * 1024 * 1024


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _candidate_record(row) -> dict[str, Any]:
    value = dict(row)
    value["score_breakdown"] = json.loads(value.pop("score_json") or "{}")
    value["metadata"] = json.loads(value.pop("metadata_json") or "{}")
    # Download URLs are provider execution details, not presentation data.
    value.pop("download_url", None)
    return value


class MaterialSourcingRepository(MarketingDomainRepository):
    """Normalize provider results and materialize only rights-reviewed binaries."""

    def __init__(self, paths: MarketingDataPaths | None = None) -> None:
        super().__init__(paths)
        self.media = MediaAssetRepository(self.paths)

    def search(
        self,
        *,
        user_id: str,
        account_id: str,
        query: str,
        role: str = "broll",
        orientation: str = "",
        media_type: str = "either",
        target_duration: float = 0,
        limit: int = 12,
        locale: str = "zh-CN",
        request_ref: str = "",
    ) -> dict[str, Any]:
        user_id = self._required(user_id, "user_id")
        account_id = self._required(account_id, "account_id")
        query = self._required(query, "query", limit=300)
        role = str(role or "broll").strip().lower()
        if role not in _ROLES:
            raise ValueError("unsupported material role")
        orientation = str(orientation or "").strip().lower()
        if orientation not in _ORIENTATIONS:
            raise ValueError("unsupported material orientation")
        media_type = str(media_type or "either").strip().lower()
        if media_type not in _MEDIA_TYPES:
            raise ValueError("unsupported material media type")
        safe_limit = max(1, min(int(limit), 40))
        duration = max(0.0, min(float(target_duration or 0), 600.0))
        request_ref = str(request_ref or "").strip()
        if len(request_ref) > 240:
            raise ValueError("request_ref must not exceed 240 characters")
        search_id = f"material_search_{uuid.uuid4().hex}"
        request = {
            "query": query,
            "role": role,
            "orientation": orientation,
            "media_type": media_type,
            "target_duration": round(duration, 3),
            "limit": safe_limit,
            "locale": str(locale or "zh-CN")[:20],
            "request_ref": request_ref or None,
        }
        if request_ref:
            with self._connection() as db:
                existing = db.execute(
                    """SELECT id FROM material_searches
                    WHERE user_id=? AND account_id=?
                      AND json_extract(query_json,'$.request_ref')=?
                    ORDER BY created_at ASC LIMIT 1""",
                    (user_id, account_id, request_ref),
                ).fetchone()
            if existing is not None:
                return self.get_search(
                    search_id=existing["id"],
                    user_id=user_id,
                    account_id=account_id,
                )
        now = _now()
        with self._transaction() as db:
            db.execute(
                """INSERT INTO material_searches
                (id,user_id,account_id,query_json,status,provider_errors_json,created_at,updated_at)
                VALUES (?,?,?,?,?,'{}',?,?)""",
                (search_id, user_id, account_id, _json(request), "running", now, now),
            )

        candidates = self._local_candidates(
            user_id=user_id,
            account_id=account_id,
            request=request,
        )
        provider_errors: dict[str, str] = {}
        ensure_default_material_providers()
        for provider in list_material_providers():
            try:
                results = provider.search(request)
            except Exception as exc:
                provider_errors[provider.name] = f"{type(exc).__name__}: {exc}"[:500]
                continue
            for candidate in results:
                try:
                    normalized = self._normalize_provider_candidate(
                        candidate, role=role
                    )
                except ValueError as exc:
                    provider_errors[provider.name] = f"invalid candidate: {exc}"[:500]
                    continue
                if media_type != "either" and normalized["media_type"] != media_type:
                    continue
                normalized["score_breakdown"] = self._score(normalized, request)
                normalized["score"] = round(
                    sum(normalized["score_breakdown"].values()), 4
                )
                candidates.append(normalized)

        candidates.sort(key=lambda item: (-float(item["score"]), item["provider"]))
        candidates = candidates[:safe_limit]
        with self._transaction() as db:
            for candidate in candidates:
                candidate_id = f"material_candidate_{uuid.uuid4().hex}"
                candidate["id"] = candidate_id
                db.execute(
                    """INSERT INTO material_candidates
                    (id,search_id,user_id,account_id,provider,provider_asset_id,
                     media_type,role,source_url,preview_url,download_url,creator,
                     creator_url,license_name,license_url,provider_home_url,width,
                     height,duration,score,score_json,metadata_json,status,created_at,updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'candidate',?,?)""",
                    (
                        candidate_id,
                        search_id,
                        user_id,
                        account_id,
                        candidate["provider"],
                        candidate["provider_asset_id"],
                        candidate["media_type"],
                        candidate["role"],
                        candidate.get("source_url", ""),
                        candidate.get("preview_url", ""),
                        candidate.get("download_url", ""),
                        candidate.get("creator", ""),
                        candidate.get("creator_url", ""),
                        candidate.get("license_name", ""),
                        candidate.get("license_url", ""),
                        candidate.get("provider_home_url", ""),
                        int(candidate.get("width") or 0),
                        int(candidate.get("height") or 0),
                        float(candidate.get("duration") or 0),
                        float(candidate["score"]),
                        _json(candidate["score_breakdown"]),
                        _json(candidate.get("metadata") or {}),
                        now,
                        now,
                    ),
                )
            status = "completed" if candidates else "unavailable"
            db.execute(
                """UPDATE material_searches
                SET status=?,provider_errors_json=?,updated_at=? WHERE id=?""",
                (status, _json(provider_errors), _now(), search_id),
            )
        return self.get_search(
            search_id=search_id,
            user_id=user_id,
            account_id=account_id,
        )

    def get_search(
        self, *, search_id: str, user_id: str, account_id: str
    ) -> dict[str, Any]:
        with self._connection() as db:
            search = db.execute(
                """SELECT * FROM material_searches
                WHERE id=? AND user_id=? AND account_id=?""",
                (search_id, user_id, account_id),
            ).fetchone()
            rows = db.execute(
                """SELECT * FROM material_candidates
                WHERE search_id=? AND user_id=? AND account_id=?
                ORDER BY score DESC,created_at ASC""",
                (search_id, user_id, account_id),
            ).fetchall()
        if search is None:
            raise KeyError("material search not found in account scope")
        value = dict(search)
        value["query"] = json.loads(value.pop("query_json") or "{}")
        value["provider_errors"] = json.loads(value.pop("provider_errors_json") or "{}")
        value["candidates"] = [_candidate_record(row) for row in rows]
        return value

    def register_web_video(
        self,
        *,
        search_id: str,
        user_id: str,
        account_id: str,
        source_url: str,
        title: str,
        provider_asset_id: str,
        download_url: str = "",
        preview_url: str = "",
        creator: str = "",
        creator_url: str = "",
        duration: float = 0,
        width: int = 0,
        height: int = 0,
        discovery_query: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Attach a browser/Web-discovered video URL to one native search.

        Discovery is not rights review.  The candidate remains a URL plus
        metadata until it is inspected and a precise excerpt is imported as a
        ``rights_pending`` library clip.
        """

        search_id = self._required(search_id, "search_id")
        user_id = self._required(user_id, "user_id")
        account_id = self._required(account_id, "account_id")
        source_url = self._https_url(source_url, "source_url")
        download_url = self._optional_https_url(download_url, "download_url")
        preview_url = self._optional_https_url(preview_url, "preview_url")
        title = self._required(title, "title", limit=500)
        provider_asset_id = self._required(
            provider_asset_id, "provider_asset_id", limit=500
        )
        metadata_value = dict(metadata or {})
        metadata_value.update({
            "title": title,
            "discovery_query": str(discovery_query or "").strip()[:500],
            "rights_status": "rights_pending",
            "discovery_host": str(urlparse(source_url).hostname or ""),
        })
        with self._connection() as db:
            search = db.execute(
                """SELECT id FROM material_searches
                WHERE id=? AND user_id=? AND account_id=?""",
                (search_id, user_id, account_id),
            ).fetchone()
            existing = db.execute(
                """SELECT * FROM material_candidates
                WHERE search_id=? AND user_id=? AND account_id=?
                  AND provider='web_video' AND provider_asset_id=?""",
                (search_id, user_id, account_id, provider_asset_id),
            ).fetchone()
        if search is None:
            raise KeyError("material search not found in account scope")
        if existing is not None:
            return _candidate_record(existing)
        now = _now()
        candidate_id = f"material_candidate_{uuid.uuid4().hex}"
        with self._transaction() as db:
            db.execute(
                """INSERT INTO material_candidates
                (id,search_id,user_id,account_id,provider,provider_asset_id,
                 media_type,role,source_url,preview_url,download_url,creator,
                 creator_url,license_name,license_url,provider_home_url,width,
                 height,duration,score,score_json,metadata_json,status,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'candidate',?,?)""",
                (
                    candidate_id,
                    search_id,
                    user_id,
                    account_id,
                    "web_video",
                    provider_asset_id,
                    "video",
                    "broll",
                    source_url,
                    preview_url,
                    download_url,
                    str(creator or "").strip()[:300],
                    str(creator_url or "").strip()[:1000],
                    "",
                    "",
                    f"https://{urlparse(source_url).hostname or ''}/",
                    max(0, int(width or 0)),
                    max(0, int(height or 0)),
                    max(0.0, float(duration or 0)),
                    0.0,
                    _json({"retrieval_only": 0.0}),
                    _json(metadata_value),
                    now,
                    now,
                ),
            )
            db.execute(
                """UPDATE material_searches SET status='completed',updated_at=?
                WHERE id=?""",
                (now, search_id),
            )
            row = db.execute(
                "SELECT * FROM material_candidates WHERE id=?", (candidate_id,)
            ).fetchone()
        return _candidate_record(row)

    def prepare_video_analysis(
        self,
        *,
        candidate_id: str,
        user_id: str,
        account_id: str,
        work_dir: Path,
        watch_script: Path | None = None,
        max_frames: int = 18,
    ) -> dict[str, Any]:
        """Create a free 720p analysis proxy, frames and native-caption report.

        The bundled ``watch`` skill is invoked with ``--no-whisper``.  No model
        call occurs here; the Material Scout must inspect returned frame paths
        and explicitly submit its grounded assessment in a separate step.
        """

        candidate = self._candidate_internal(
            candidate_id=candidate_id, user_id=user_id, account_id=account_id
        )
        if str(candidate["media_type"]) != "video":
            raise ValueError("video analysis requires a video candidate")
        source = self._candidate_source(candidate, user_id=user_id)
        if watch_script is None:
            from tools.skill_manager_tool import _find_skill

            skill = _find_skill("watch")
            if not skill:
                raise RuntimeError("the required watch skill is not installed")
            watch_script = Path(skill["path"]) / "scripts" / "watch.py"
        watch_script = Path(watch_script).expanduser().resolve()
        if not watch_script.is_file():
            raise RuntimeError("the installed watch skill has no watch.py entrypoint")
        target = Path(work_dir).expanduser().resolve() / candidate_id
        if target.exists():
            shutil.rmtree(target)
        target.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            [
                sys.executable,
                str(watch_script),
                source,
                "--detail",
                "balanced",
                "--max-frames",
                str(max(6, min(int(max_frames), 30))),
                "--resolution",
                "768",
                "--no-whisper",
                "--out-dir",
                str(target),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode != 0:
            shutil.rmtree(target, ignore_errors=True)
            raise RuntimeError(f"watch analysis failed: {result.stderr[-1200:]}")
        report = result.stdout
        report_path = target / "watch-report.md"
        report_path.write_text(report, encoding="utf-8")
        frames: list[dict[str, Any]] = []
        for line in report.splitlines():
            match = _FRAME_LINE.match(line.strip())
            if not match:
                continue
            frame = Path(match.group("path")).expanduser().resolve()
            if target not in frame.parents or not frame.is_file():
                continue
            frames.append({
                "path": str(frame),
                "timestamp_seconds": int(match.group("minutes")) * 60
                + int(match.group("seconds")),
                "reason": match.group("reason"),
            })
        if not frames:
            shutil.rmtree(target, ignore_errors=True)
            raise RuntimeError("watch analysis produced no inspectable frames")
        media_paths = sorted(
            path
            for path in (target / "download").glob("video.*")
            if path.suffix.lower() in {".mp4", ".mkv", ".webm", ".mov"}
        )
        video_path = self._first_video_path(media_paths)
        if video_path is None:
            raise RuntimeError("watch analysis produced no 720p proxy")
        probe = self._probe_video(video_path)
        if probe["duration_seconds"] > _MAX_CAPTURE_SECONDS:
            shutil.rmtree(target, ignore_errors=True)
            raise ValueError("source video exceeds the 30 minute analysis limit")
        return {
            "candidate_id": candidate_id,
            "source_url": str(candidate["source_url"]),
            "analysis_dir": str(target),
            "proxy_path": str(video_path),
            "report_path": str(report_path),
            "frames": frames,
            "source_probe": probe,
            "native_captions_only": True,
            "whisper_used": False,
            "cost_cny": 0,
        }

    def import_video_excerpt(
        self,
        *,
        candidate_id: str,
        user_id: str,
        account_id: str,
        source_in: float,
        source_out: float,
        asset_name: str,
        inspection_id: str,
        relevance_score: float,
        relevance_evidence: str,
        collection: str,
        work_dir: Path,
    ) -> dict[str, Any]:
        """Download <=1080p, cut an exact excerpt, verify it and import it.

        The source download and analysis proxy are deleted only after the
        library-owned copy has passed decode, duration and black-frame checks.
        """

        candidate = self._candidate_internal(
            candidate_id=candidate_id, user_id=user_id, account_id=account_id
        )
        start = max(0.0, float(source_in))
        end = float(source_out)
        if end <= start or end - start < 0.5 or end - start > 30:
            raise ValueError("excerpt must be between 0.5 and 30 seconds")
        score = max(0.0, min(1.0, float(relevance_score)))
        evidence = self._required(relevance_evidence, "relevance_evidence", limit=2000)
        if score < 0.72:
            raise ValueError("candidate did not pass the 0.72 relevance threshold")
        work_root = Path(work_dir).expanduser().resolve() / candidate_id
        raw_dir = work_root / "source-1080"
        raw_dir.mkdir(parents=True, exist_ok=True)
        source = self._candidate_source(candidate, user_id=user_id)
        if candidate["provider"] == "user_library":
            source_path = Path(source).resolve()
        else:
            template = str(raw_dir / "source.%(ext)s")
            downloaded = subprocess.run(
                [
                    "yt-dlp",
                    "-N",
                    "8",
                    "-f",
                    "bv*[height<=1080]+ba/b[height<=1080]/bv+ba/b",
                    "--merge-output-format",
                    "mp4",
                    "--no-playlist",
                    "--max-filesize",
                    str(_MAX_SOURCE_BYTES),
                    "-o",
                    template,
                    "--",
                    source,
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=900,
            )
            source_paths = sorted(
                path
                for path in raw_dir.glob("source.*")
                if path.suffix.lower() in {".mp4", ".mkv", ".webm", ".mov"}
            )
            source_path = self._first_video_path(source_paths)
            if downloaded.returncode != 0 or source_path is None:
                raise RuntimeError(f"1080p source download failed: {downloaded.stderr[-1200:]}")
        source_probe = self._probe_video(source_path)
        if end > source_probe["duration_seconds"] + 0.05:
            raise ValueError("source_out exceeds the original video duration")
        clip_path = work_root / "excerpt.mp4"
        cut = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(source_path),
                "-ss",
                f"{start:.3f}",
                "-t",
                f"{end - start:.3f}",
                "-map",
                "0:v:0",
                "-map",
                "0:a?",
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-movflags",
                "+faststart",
                str(clip_path),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if cut.returncode != 0 or not clip_path.is_file():
            raise RuntimeError(f"excerpt cut failed: {cut.stderr[-1200:]}")
        clip_probe = self._probe_video(clip_path)
        expected_duration = end - start
        if abs(clip_probe["duration_seconds"] - expected_duration) > 0.25:
            raise RuntimeError("excerpt duration differs from requested timecode")
        decoded = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(clip_path), "-f", "null", "-"],
            check=False,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if decoded.returncode != 0 or decoded.stderr.strip():
            raise RuntimeError("excerpt failed full decode validation")
        black_scan = subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-nostats",
                "-i",
                str(clip_path),
                "-vf",
                "blackdetect=d=0.4:pic_th=0.98",
                "-an",
                "-f",
                "null",
                "-",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if black_scan.returncode != 0:
            raise RuntimeError("excerpt failed black-frame validation")
        black_seconds = sum(
            float(value)
            for value in re.findall(r"black_duration:([0-9.]+)", black_scan.stderr)
        )
        if black_seconds > 0:
            raise RuntimeError("excerpt contains a black segment lasting at least 0.4 seconds")
        provider_asset_id = (
            f"{candidate['provider_asset_id']}#t={start:.3f},{end:.3f}"
        )
        asset = self.media.import_generated_file(
            user_id=user_id,
            account_id=account_id,
            name=self._required(asset_name, "asset_name", limit=512),
            media_type="video",
            role="broll",
            path=clip_path,
            mime_type="video/mp4",
            provider=str(candidate["provider"]),
            provider_asset_id=provider_asset_id,
            source_type="web_clip",
            rights_status="rights_pending",
            metadata={
                "collection": self._required(collection, "collection", limit=256),
                "source_url": str(candidate["source_url"]),
                "original_video_id": str(candidate["provider_asset_id"]),
                "original_duration_seconds": source_probe["duration_seconds"],
                "source_in": round(start, 3),
                "source_out": round(end, 3),
                "clip_duration_seconds": clip_probe["duration_seconds"],
                "width": clip_probe["width"],
                "height": clip_probe["height"],
                "has_audio": clip_probe["has_audio"],
                "black_seconds": round(black_seconds, 3),
                "inspection_id": inspection_id,
                "relevance_score": score,
                "relevance_evidence": evidence,
                "rights_status": "rights_pending",
                "publish_blocked": True,
            },
            receipt={
                "version": "marketing.material.clip.receipt.v1",
                "candidate_id": candidate_id,
                "inspection_id": inspection_id,
                "source_url": str(candidate["source_url"]),
                "source_in": round(start, 3),
                "source_out": round(end, 3),
                "cost_cny": 0,
                "paid_services": [],
                "watch_no_whisper": True,
                "imported_at": _now(),
            },
        )
        local_path = self.media.resolve_local_path(asset_id=asset["id"], user_id=user_id)
        if not local_path or hashlib.sha256(Path(local_path).read_bytes()).hexdigest() != asset["sha256"]:
            raise RuntimeError("library copy failed hash verification")
        shutil.rmtree(work_root, ignore_errors=True)
        return {"asset": asset, "local_path": local_path, "probe": clip_probe}

    def _candidate_internal(
        self, *, candidate_id: str, user_id: str, account_id: str
    ) -> dict[str, Any]:
        with self._connection() as db:
            row = db.execute(
                """SELECT * FROM material_candidates
                WHERE id=? AND user_id=? AND account_id=?""",
                (candidate_id, user_id, account_id),
            ).fetchone()
        if row is None:
            raise KeyError("material candidate not found in account scope")
        return dict(row)

    def _candidate_source(self, candidate: dict[str, Any], *, user_id: str) -> str:
        if candidate["provider"] == "user_library":
            local = self.media.resolve_local_path(
                asset_id=str(candidate["provider_asset_id"]), user_id=user_id
            )
            if not local:
                raise ValueError("owned material file is unavailable")
            return local
        source = str(candidate.get("download_url") or candidate.get("source_url") or "")
        return self._https_url(source, "candidate source URL")

    @staticmethod
    def _first_video_path(paths: list[Path]) -> Path | None:
        for path in paths:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-select_streams",
                    "v:0",
                    "-show_entries",
                    "stream=index",
                    "-of",
                    "csv=p=0",
                    str(path),
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0 and result.stdout.strip():
                return path
        return None

    @staticmethod
    def _probe_video(path: Path) -> dict[str, Any]:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                str(Path(path).resolve()),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(f"ffprobe failed: {result.stderr[-800:]}")
        payload = json.loads(result.stdout or "{}")
        streams = payload.get("streams") or []
        video = next((item for item in streams if item.get("codec_type") == "video"), None)
        if not video:
            raise ValueError("media has no video stream")
        audio = next((item for item in streams if item.get("codec_type") == "audio"), None)
        duration = float((payload.get("format") or {}).get("duration") or video.get("duration") or 0)
        return {
            "duration_seconds": round(duration, 3),
            "width": int(video.get("width") or 0),
            "height": int(video.get("height") or 0),
            "video_codec": str(video.get("codec_name") or ""),
            "audio_codec": str(audio.get("codec_name") or "") if audio else "",
            "has_audio": audio is not None,
            "size_bytes": int((payload.get("format") or {}).get("size") or 0),
        }

    @staticmethod
    def _https_url(value: Any, field: str) -> str:
        text = str(value or "").strip()
        parsed = urlparse(text)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError(f"{field} must be an https URL")
        return text

    @classmethod
    def _optional_https_url(cls, value: Any, field: str) -> str:
        text = str(value or "").strip()
        return cls._https_url(text, field) if text else ""

    def materialize(
        self,
        *,
        candidate_id: str,
        user_id: str,
        account_id: str,
        rights_reviewed: bool,
    ) -> dict[str, Any]:
        if not rights_reviewed:
            raise ValueError("explicit source and license review is required")
        self.media.cleanup_expired(user_id=user_id)
        with self._connection() as db:
            row = db.execute(
                """SELECT * FROM material_candidates
                WHERE id=? AND user_id=? AND account_id=?""",
                (candidate_id, user_id, account_id),
            ).fetchone()
        if row is None:
            raise KeyError("material candidate not found in account scope")
        candidate = dict(row)
        if candidate.get("selected_media_asset_id"):
            try:
                return {
                    "candidate": _candidate_record(row),
                    "asset": self.media.get(
                        asset_id=candidate["selected_media_asset_id"], user_id=user_id
                    ),
                }
            except KeyError:
                # An unreferenced temporary binary may have expired since selection.
                # Keep the durable candidate and materialize it again below.
                candidate["selected_media_asset_id"] = None
        if candidate["provider"] == "user_library":
            asset = self.media.get(
                asset_id=candidate["provider_asset_id"], user_id=user_id
            )
        else:
            if not candidate["license_name"] or not candidate["license_url"]:
                raise ValueError("provider candidate has no durable license evidence")
            asset = self.media.find_provider_asset(
                user_id=user_id,
                account_id=account_id,
                provider=candidate["provider"],
                provider_asset_id=candidate["provider_asset_id"],
            )
            if asset is None:
                provider = get_material_provider(candidate["provider"])
                payload, filename, mime_type = provider.download(candidate)
                asset = self.media.import_provider_bytes(
                    user_id=user_id,
                    account_id=account_id,
                    name=f"{candidate['provider']} {candidate['provider_asset_id']}",
                    media_type=candidate["media_type"],
                    role=candidate["role"],
                    payload=payload,
                    filename=filename,
                    mime_type=mime_type,
                    provider=candidate["provider"],
                    provider_asset_id=candidate["provider_asset_id"],
                    metadata={
                        "source_url": candidate["source_url"],
                        "creator": candidate["creator"],
                        "creator_url": candidate["creator_url"],
                        "license_name": candidate["license_name"],
                        "license_url": candidate["license_url"],
                        "provider_home_url": candidate["provider_home_url"],
                        "rights_caveat": (
                            "Check people, property, trademarks and context-specific releases before publication."
                        ),
                    },
                    receipt={
                        "version": "marketing.material.receipt.v1",
                        "candidate_id": candidate_id,
                        "search_id": candidate["search_id"],
                        "provider": candidate["provider"],
                        "provider_asset_id": candidate["provider_asset_id"],
                        "source_url": candidate["source_url"],
                        "license_name": candidate["license_name"],
                        "license_url": candidate["license_url"],
                        "rights_reviewed": True,
                        "materialized_at": _now(),
                    },
                    storage_tier="temporary",
                )
        with self._transaction() as db:
            db.execute(
                """UPDATE material_candidates
                SET status='selected',selected_media_asset_id=?,updated_at=?
                WHERE id=? AND user_id=? AND account_id=?""",
                (asset["id"], _now(), candidate_id, user_id, account_id),
            )
            selected = db.execute(
                "SELECT * FROM material_candidates WHERE id=?", (candidate_id,)
            ).fetchone()
        return {"candidate": _candidate_record(selected), "asset": asset}

    def _local_candidates(
        self, *, user_id: str, account_id: str, request: dict[str, Any]
    ) -> list[dict[str, Any]]:
        query_terms = _semantic_query_terms(str(request["query"]))
        results = []
        for asset in self.media.list(user_id=user_id, account_id=account_id)["assets"]:
            if (
                asset["media_type"] not in {"image", "video"}
                or (
                    request.get("media_type") != "either"
                    and asset["media_type"] != request.get("media_type")
                )
                or asset["role"] not in _ROLES
                or not asset.get("local_path")
            ):
                continue
            haystack = f"{asset['name']} {_json(asset.get('metadata') or {})}".lower()
            if not any(term in haystack for term in query_terms):
                continue
            metadata = asset.get("metadata") or {}
            preview_path = self.media.resolve_local_path(
                asset_id=str(asset["id"]), user_id=user_id
            )
            if not preview_path:
                continue
            semantic = _semantic_coverage(
                query_terms=query_terms,
                candidate_text=haystack,
            )
            breakdown = {
                "source_priority": 0.36,
                "semantic_fit": round(0.28 * semantic, 4),
                "rights_confidence": 0.2,
                "quality_fit": 0.08,
                "continuity_fit": 0.04,
            }
            results.append({
                "provider": "user_library",
                "provider_asset_id": asset["id"],
                "media_type": asset["media_type"],
                "role": request["role"],
                "source_url": str(metadata.get("source_url") or ""),
                "preview_url": str(preview_path),
                "download_url": "",
                "creator": str(metadata.get("creator") or ""),
                "creator_url": str(metadata.get("creator_url") or ""),
                "license_name": str(
                    metadata.get("license_name") or "User-confirmed rights"
                ),
                "license_url": str(metadata.get("license_url") or ""),
                "provider_home_url": str(metadata.get("provider_home_url") or ""),
                "width": int(metadata.get("width") or 0),
                "height": int(metadata.get("height") or 0),
                "duration": float(metadata.get("duration") or 0),
                "score_breakdown": breakdown,
                "score": round(sum(breakdown.values()), 4),
                "metadata": {
                    "asset_name": asset["name"],
                    "original_provider": asset.get("provider") or "",
                    "original_provider_asset_id": asset.get("provider_asset_id") or "",
                },
            })
        return results

    @staticmethod
    def _normalize_provider_candidate(
        candidate: dict[str, Any], *, role: str
    ) -> dict[str, Any]:
        if not isinstance(candidate, dict):
            raise ValueError("material provider returned a non-object candidate")
        required = (
            "provider",
            "provider_asset_id",
            "media_type",
            "source_url",
            "download_url",
            "license_name",
            "license_url",
        )
        if any(not str(candidate.get(field) or "").strip() for field in required):
            raise ValueError(
                "material provider candidate is missing required provenance"
            )
        if candidate["media_type"] not in {"image", "video"}:
            raise ValueError("material provider returned an unsupported media type")
        value = dict(candidate)
        value["role"] = role
        value["metadata"] = (
            value.get("metadata") if isinstance(value.get("metadata"), dict) else {}
        )
        return value

    @staticmethod
    def _score(candidate: dict[str, Any], request: dict[str, Any]) -> dict[str, float]:
        width = max(0, int(candidate.get("width") or 0))
        height = max(0, int(candidate.get("height") or 0))
        long_edge = max(width, height)
        quality = min(1.0, long_edge / 1920) if long_edge else 0.35
        orientation = request.get("orientation")
        orientation_fit = 1.0
        if orientation == "portrait":
            orientation_fit = 1.0 if height >= width else 0.3
        elif orientation == "landscape":
            orientation_fit = 1.0 if width >= height else 0.3
        elif orientation == "square" and width and height:
            orientation_fit = max(0.3, 1 - abs(math.log(width / height)))
        duration_fit = 0.7
        target_duration = float(request.get("target_duration") or 0)
        actual_duration = float(candidate.get("duration") or 0)
        if target_duration and actual_duration:
            duration_fit = max(0.2, min(1.0, actual_duration / target_duration))
        metadata = candidate.get("metadata") or {}
        candidate_text = " ".join(
            str(value or "")
            for value in (
                metadata.get("title"),
                metadata.get("query"),
                metadata.get("tags"),
                candidate.get("source_url"),
            )
        ).lower()
        semantic = _semantic_coverage(
            query_terms=_semantic_query_terms(str(request.get("query") or "")),
            candidate_text=candidate_text,
        )
        return {
            "source_priority": 0.1,
            "semantic_fit": round(0.3 * semantic, 4),
            "rights_confidence": 0.14,
            "quality_fit": round(0.18 * quality, 4),
            "orientation_fit": round(0.12 * orientation_fit, 4),
            "duration_fit": round(0.08 * duration_fit, 4),
            "novelty": 0.02,
        }

    @staticmethod
    def _required(value: Any, field: str, *, limit: int = 256) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError(f"{field} is required")
        if len(text) > limit:
            raise ValueError(f"{field} must be at most {limit} characters")
        return text


def _semantic_query_terms(query: str) -> set[str]:
    """Tokenize Latin words and CJK bigrams for conservative library matching."""

    terms = {term.lower() for term in re.findall(r"[a-zA-Z0-9]+", query)}
    for run in re.findall(r"[\u3400-\u9fff]+", query):
        if len(run) == 1:
            terms.add(run)
        else:
            terms.update(run[index : index + 2] for index in range(len(run) - 1))
    return terms


def _semantic_coverage(*, query_terms: set[str], candidate_text: str) -> float:
    """Use lexical coverage only for retrieval ordering, never as QA proof."""

    if not query_terms:
        return 0.0
    haystack = str(candidate_text or "").lower()
    matched = sum(1 for term in query_terms if term and term in haystack)
    return max(0.0, min(1.0, matched / len(query_terms)))
