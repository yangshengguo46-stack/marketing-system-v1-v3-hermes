"""Pinned offline scene renderers for the native Marketing OS runtime."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable

from agent.marketing.domains.video_ir import HYPERFRAMES_RENDERER, REMOTION_RENDERER


RUNTIME_VERSION = "marketing.video.renderers.v1"
PINNED_PACKAGES = {
    "@remotion/cli": "4.0.488",
    "gsap": "3.14.2",
    "hyperframes": "0.7.57",
    "react": "19.2.4",
    "react-dom": "19.2.4",
    "remotion": "4.0.488",
}
REMOTION_UPGRADE_REQUIREMENTS = [
    "explicit_user_approval",
    "license_review",
    "renderer_regression",
]
_RendererRunner = Callable[[list[str], Path, dict[str, str]], None]


def _default_runner(command: list[str], log_path: Path, env: dict[str, str]) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("ab") as log:
        subprocess.run(
            command,
            check=True,
            stdout=log,
            stderr=log,
            env=env,
            timeout=900,
        )


def _repository_renderer_root() -> Path:
    return Path(__file__).resolve().parents[3] / "video-renderers"


class VideoRendererRuntime:
    """Discover and execute the product's exact, local renderer toolchain."""

    def __init__(
        self,
        *,
        root: str | Path | None = None,
        node_executable: str | Path | None = None,
        browser_executable: str | Path | None = None,
        runner: _RendererRunner | None = None,
    ) -> None:
        self.root = (
            Path(
                root
                or os.environ.get("MARKETING_OS_VIDEO_RENDERERS_ROOT")
                or _repository_renderer_root()
            )
            .expanduser()
            .resolve()
        )
        self.node_executable = Path(
            node_executable
            or os.environ.get("MARKETING_OS_VIDEO_NODE_EXECUTABLE")
            or shutil.which("node")
            or ""
        ).expanduser()
        self.browser_executable = Path(
            browser_executable
            or os.environ.get("MARKETING_OS_VIDEO_BROWSER_EXECUTABLE")
            or os.environ.get("HERMES_BROWSER_EXECUTABLE")
            or ""
        ).expanduser()
        self.runner = runner or _default_runner
        self._health: dict[str, Any] | None = None

    def health(self, *, refresh: bool = False) -> dict[str, Any]:
        if self._health is not None and not refresh:
            return self._health
        failures: list[str] = []
        package_path = self.root / "package.json"
        policy_path = self.root / "version-policy.json"
        lock_path = self.root / "package-lock.json"
        installed_lock = self.root / "node_modules" / ".package-lock.json"
        scripts = {
            REMOTION_RENDERER: self.root / "render-remotion.mjs",
            HYPERFRAMES_RENDERER: self.root / "render-hyperframes.mjs",
        }
        package_versions: dict[str, str] = {}
        policy_versions: dict[str, str] = {}
        lock_versions: dict[str, str] = {}
        installed_versions: dict[str, str] = {}
        installed_package_versions: dict[str, str] = {}
        remotion_upgrade_gate: dict[str, Any] = {}
        if not package_path.is_file():
            failures.append("renderer package manifest is missing")
        else:
            try:
                package = json.loads(package_path.read_text(encoding="utf-8"))
                package_versions = package.get("dependencies") or {}
            except (OSError, json.JSONDecodeError):
                failures.append("renderer package manifest is unreadable")
        for label, target in (
            ("version policy", policy_path),
            ("source lockfile", lock_path),
            ("installed lockfile", installed_lock),
        ):
            if not target.is_file():
                failures.append(f"renderer {label} is missing")
                continue
            try:
                payload = json.loads(target.read_text(encoding="utf-8"))
                if label == "version policy":
                    policy_versions = payload.get("dependencies") or {}
                    remotion_upgrade_gate = payload.get("remotion_upgrade_gate") or {}
                elif label == "source lockfile":
                    packages = payload.get("packages") or {}
                    lock_versions = {
                        name: (packages.get(f"node_modules/{name}") or {}).get(
                            "version"
                        )
                        for name in PINNED_PACKAGES
                    }
                else:
                    packages = payload.get("packages") or {}
                    installed_versions = {
                        name: (packages.get(f"node_modules/{name}") or {}).get(
                            "version"
                        )
                        for name in PINNED_PACKAGES
                    }
            except (OSError, json.JSONDecodeError):
                failures.append(f"renderer {label} is unreadable")
        for name in PINNED_PACKAGES:
            installed_package = self.root / "node_modules" / name / "package.json"
            try:
                payload = json.loads(installed_package.read_text(encoding="utf-8"))
                installed_package_versions[name] = payload.get("version")
            except (OSError, json.JSONDecodeError):
                failures.append(f"renderer installed package is unreadable: {name}")
        for label, versions in (
            ("manifest", package_versions),
            ("version policy", policy_versions),
            ("source lockfile", lock_versions),
            ("installed lockfile", installed_versions),
            ("installed packages", installed_package_versions),
        ):
            if any(
                versions.get(name) != version
                for name, version in PINNED_PACKAGES.items()
            ):
                failures.append(f"renderer {label} does not match product pins")
        if (
            remotion_upgrade_gate.get("locked_version") != PINNED_PACKAGES["remotion"]
            or remotion_upgrade_gate.get("blocked_major") != 5
            or remotion_upgrade_gate.get("requires")
            != REMOTION_UPGRADE_REQUIREMENTS
        ):
            failures.append("renderer Remotion upgrade gate does not match policy")
        if not installed_lock.is_file():
            failures.append("renderer production dependencies are not installed")
        if not self.node_executable.is_file():
            failures.append("Node executable is missing")
        if not self.browser_executable.is_file():
            failures.append("renderer browser executable is missing")
        for renderer, script in scripts.items():
            if not script.is_file():
                failures.append(f"{renderer} entrypoint is missing")

        node_version = ""
        if self.node_executable.is_file():
            try:
                env = os.environ.copy()
                if os.environ.get("MARKETING_OS_VIDEO_NODE_IS_ELECTRON") == "1":
                    env["ELECTRON_RUN_AS_NODE"] = "1"
                result = subprocess.run(
                    [str(self.node_executable), "-p", "process.versions.node"],
                    check=True,
                    capture_output=True,
                    text=True,
                    env=env,
                    timeout=10,
                )
                node_version = result.stdout.strip()
                if int(node_version.split(".", 1)[0]) < 22:
                    failures.append("Node 22 or newer is required")
            except (OSError, ValueError, subprocess.SubprocessError):
                failures.append("Node version could not be verified")

        enabled = [] if failures else [REMOTION_RENDERER, HYPERFRAMES_RENDERER]
        fingerprint = hashlib.sha256()
        for relative in (
            "package-lock.json",
            "version-policy.json",
            "render-remotion.mjs",
            "render-hyperframes.mjs",
            "remotion/index.ts",
            "remotion/root.tsx",
            "remotion/scene.tsx",
        ):
            target = self.root / relative
            if target.is_file():
                fingerprint.update(relative.encode("utf-8"))
                fingerprint.update(target.read_bytes())
        self._health = {
            "version": RUNTIME_VERSION,
            "ready": not failures,
            "enabled_renderers": enabled,
            "root": str(self.root),
            "node_version": node_version,
            "browser_executable": str(self.browser_executable),
            "package_versions": {
                name: package_versions.get(name) for name in PINNED_PACKAGES
            },
            "runtime_sha256": fingerprint.hexdigest(),
            "failures": failures,
        }
        return self._health

    def render_scene(
        self,
        *,
        renderer: str,
        scene: dict[str, Any],
        canvas: dict[str, Any],
        visual_assets: list[dict[str, Any]],
        work_dir: Path,
        output_path: Path,
    ) -> dict[str, Any]:
        health = self.health()
        if renderer not in health["enabled_renderers"]:
            raise RuntimeError(f"renderer is unavailable: {renderer}")
        if len(visual_assets) != len(scene["visuals"]):
            raise ValueError("every scene visual must have one materialized asset")
        scene_root = work_dir.resolve()
        assets_root = scene_root / "assets"
        assets_root.mkdir(parents=True, exist_ok=True)
        visuals = []
        for index, (visual, asset) in enumerate(zip(scene["visuals"], visual_assets)):
            source = Path(asset["path"]).resolve()
            if not source.is_file():
                raise ValueError("scene visual asset is unavailable")
            suffix = source.suffix.lower()
            target = assets_root / f"visual-{index:03d}{suffix}"
            shutil.copy2(source, target)
            visuals.append({
                "file": target.relative_to(scene_root).as_posix(),
                "mediaType": asset["media_type"],
                "sourceIn": visual["source_in"],
                "fit": visual["fit"],
            })
        spec = {
            "canvas": canvas,
            "duration": scene["duration"],
            "purpose": scene["purpose"],
            "visuals": visuals,
            "text": [
                {
                    "text": layer["text"],
                    "role": layer["role"],
                    "styleToken": layer["style_token"],
                }
                for layer in scene["text"]
            ],
            "motionIntent": scene["motion_intent"],
        }
        spec_path = scene_root / "scene.json"
        spec_path.write_text(
            json.dumps(spec, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        script = {
            REMOTION_RENDERER: "render-remotion.mjs",
            HYPERFRAMES_RENDERER: "render-hyperframes.mjs",
        }.get(renderer)
        if not script:
            raise ValueError(f"unsupported advanced renderer: {renderer}")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        log_path = scene_root / f"{renderer}.log"
        env = os.environ.copy()
        if os.environ.get("MARKETING_OS_VIDEO_NODE_IS_ELECTRON") == "1":
            env["ELECTRON_RUN_AS_NODE"] = "1"
        env["NO_UPDATE_NOTIFIER"] = "1"
        self.runner(
            [
                str(self.node_executable),
                str(self.root / script),
                str(spec_path),
                str(output_path),
                str(self.browser_executable),
            ],
            log_path,
            env,
        )
        if not output_path.is_file() or output_path.stat().st_size == 0:
            raise RuntimeError(f"{renderer} did not produce a video")
        return {
            "runtime_version": RUNTIME_VERSION,
            "runtime_sha256": health["runtime_sha256"],
            "renderer": renderer,
            "scene_sha256": scene["scene_sha256"],
            "spec_sha256": hashlib.sha256(spec_path.read_bytes()).hexdigest(),
            "renderer_log_available": log_path.is_file(),
        }
