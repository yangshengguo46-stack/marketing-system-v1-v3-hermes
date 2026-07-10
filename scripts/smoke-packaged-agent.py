#!/usr/bin/env python3
"""Start the frozen backend and prove its staged Hermes runtime is usable."""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _request(base: str, token: str, method: str, path: str, body: dict | None = None) -> dict:
    payload = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(
        f"{base}{path}", method=method, data=payload,
        headers={"X-Marketing-OS-Token": token, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode() or "{}")


def smoke(backend: Path, hermes_root: Path, *, timeout: float = 45) -> dict:
    if not backend.is_file():
        raise FileNotFoundError(f"packaged backend missing: {backend}")
    if not (hermes_root / "run_agent.py").is_file():
        raise FileNotFoundError(f"packaged Hermes source missing: {hermes_root}")

    port = _free_port()
    token = "packaged-agent-smoke"
    with tempfile.TemporaryDirectory(prefix="marketing-os-packaged-") as temp:
        temp_path = Path(temp)
        env = {
            **os.environ,
            "MARKETING_OS_API_TOKEN": token,
            "MARKETING_OS_CONFIG_DIR": str(temp_path / "config"),
            "MARKETING_OS_USER_DATA": str(temp_path),
            "HERMES_AGENT_ROOT": str(hermes_root),
            "HERMES_HOME": str(temp_path / "agent-runtime"),
        }
        process = subprocess.Popen(
            [str(backend), "--port", str(port)],
            env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        base = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + timeout
        try:
            while True:
                if process.poll() is not None:
                    stdout, stderr = process.communicate(timeout=2)
                    raise RuntimeError(f"packaged backend exited early: {stderr or stdout}")
                try:
                    health = _request(base, token, "GET", "/health")
                    break
                except (urllib.error.URLError, ConnectionError, TimeoutError):
                    if time.monotonic() >= deadline:
                        raise TimeoutError("packaged backend did not become healthy")
                    time.sleep(0.25)

            runtime = _request(base, token, "GET", "/api/marketing-os/assistant/status")
            session = _request(base, token, "POST", "/agent/sessions", {"user_id": "packaged-smoke"})
            l0 = _request(base, token, "POST", "/api/tools/list_scraping_backends", {})

            assert health.get("status") == "ok"
            assert runtime.get("source_available") is True, runtime
            assert int(runtime.get("tool_count") or 0) > 0, runtime
            assert str(session.get("session_id") or "").startswith("sess_"), session
            assert isinstance(l0.get("backends"), list), l0
            return {
                "status": "ok",
                "runtime": runtime,
                "session_id": session["session_id"],
                "l0_backends": len(l0["backends"]),
            }
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", type=Path, default=ROOT / "backend" / "dist" / "marketing-os-server")
    parser.add_argument("--hermes-root", type=Path, default=ROOT / "build" / "hermes-runtime")
    args = parser.parse_args()
    try:
        result = smoke(args.backend, args.hermes_root)
    except Exception as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
