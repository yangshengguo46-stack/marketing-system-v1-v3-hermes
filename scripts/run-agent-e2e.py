#!/usr/bin/env python3
"""P0-4 end-to-end sample — prove the agent loop works with real model + tools.

Usage:
  runtime/hermes-agent/.venv/bin/python scripts/run-agent-e2e.py [--goal "..."]

Requires: Hermes runtime bootstrapped (npm run runtime:bootstrap)
          Provider secrets at ~/Library/Application Support/marketing-os-desktop/secrets/

The script:
  1. Creates an AgentCoreStore + HermesAgentService
  2. Opens a persistent session
  3. Sends a natural-language marketing goal
  4. Streams agent events (plan, tool calls, evidence, reply)
  5. Prints a structured summary
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "engine"
MARKETING_OS = ENGINE / "marketing-os"
HERMES_SRC = ROOT / "runtime" / "hermes-agent"
HERMES_VENV = HERMES_SRC / ".venv"

# Ensure our code, marketing tools, and Hermes runtime are all importable
sys.path.insert(0, str(ENGINE))
sys.path.insert(0, str(MARKETING_OS))
sys.path.insert(0, str(HERMES_SRC))
site_pkgs = HERMES_VENV / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages"
if site_pkgs.exists() and str(site_pkgs) not in sys.path:
    sys.path.insert(0, str(site_pkgs))

# Set up temporary config so server.py imports cleanly
os.environ.setdefault("MARKETING_OS_CONFIG_DIR", str(Path(tempfile.gettempdir()) / "mkt-e2e-config"))
os.environ.setdefault("HERMES_HOME", str(Path(tempfile.gettempdir()) / "mkt-e2e-hermes"))
os.environ.setdefault("HERMES_AGENT_ROOT", str(HERMES_SRC))


def load_provider_env() -> dict[str, str]:
    secrets_file = Path.home() / "Library" / "Application Support" / "marketing-os-desktop" / "secrets" / "providers.env"
    env: dict[str, str] = {}
    if secrets_file.exists():
        with open(secrets_file) as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("export "):
                    line = line[7:]
                sep = line.find("=")
                if sep > 0:
                    key = line[:sep].strip()
                    value = line[sep + 1:].strip().strip("\"'")
                    if key.isupper():
                        env[key] = value
    return env


def main():
    parser = argparse.ArgumentParser(description="P0-4 Agent E2E sample")
    parser.add_argument("--goal", default="帮我整理今天AI教育行业的热点，列出3条适合抖音科技号发布的趋势选题")
    parser.add_argument("--model", default="")
    parser.add_argument("--base-url", default="")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--dry-run", action="store_true", help="Only validate setup, don't call model")
    args = parser.parse_args()

    provider = load_provider_env()

    # Resolve model creds: CLI args > env vars > common provider keys
    model = args.model or provider.get("DEEPSEEK_MODEL", "deepseek-chat")
    base_url = args.base_url or provider.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    api_key = args.api_key or provider.get("DEEPSEEK_API_KEY", "")

    print("=" * 72)
    print("P0-4 端到端样板 — Agent loop + marketing-desktop 工具集")
    print("=" * 72)
    print(f"  Hermes source : {HERMES_SRC}")
    print(f"  Hermes venv   : {HERMES_VENV}")
    print(f"  Model         : {model}")
    print(f"  Base URL      : {base_url}")
    print(f"  API key       : {'***' if api_key else 'MISSING (set DEEPSEEK_API_KEY in providers.env)'}")
    if provider:
        known_keys = [k for k in sorted(provider) if 'KEY' in k or 'MODEL' in k or 'URL' in k]
        print(f"  Provider keys : {known_keys if known_keys else '(none found)'}")
    print()

    if not api_key:
        print("[SKIP] 缺少 API key — 请确认 secrets/providers.env 已配置 DEEPSEEK_API_KEY")
        print("       或通过 --api-key 传入")
        return

    # Import our modules after path setup. A dry run must validate the actual
    # source runtime and tool registry, not only the presence of an API key.
    from agent_core import AgentCoreStore, HermesAgentService
    from agent_core.tool_manifest import all_tools
    from agent_core.tool_gateway import ensure_registered

    print(f"  已注册工具    : {ensure_registered()}")
    for spec in all_tools():
        approval = " [需确认]" if spec.requires_approval else ""
        print(f"    {spec.name:44} L{spec.level.value}{approval}")
    print()

    store = AgentCoreStore(Path(tempfile.gettempdir()) / "mkt-e2e-agent-core.db")
    svc = HermesAgentService(
        store=store,
        hermes_home=Path(os.environ["HERMES_HOME"]),
        agent_root=HERMES_SRC,
        model=model,
        base_url=base_url,
        api_key=api_key,
        enabled_toolsets=["marketing-desktop"],
    )

    if args.dry_run:
        print(f"[OK] 源码 runtime、SessionDB、Agent Core 与 {len(all_tools())} 个受控营销工具均已加载 (dry-run)")
        return

    import asyncio

    async def run():
        print("── 创建 session ──")
        session = await svc.create_session("e2e-user")
        sid = session["session_id"]
        print(f"  session_id: {sid}\n")

        print(f"── 发送目标 ──")
        print(f"  {args.goal}\n")
        result = await svc.send_message(sid, args.goal)
        task_id = result["task_id"]
        print(f"  task_id: {task_id}\n")

        print("── Agent 事件流 ──")
        print(f"  {'时间':<22} {'类型':<28} {'详情'}")
        print(f"  {'-'*21} {'-'*27} {'-'*40}")

        step_count = 0
        tool_count = 0
        final_reply = ""

        async for event in svc.stream_events(task_id):
            event_type = event.get("type", "")
            timestamp = event.get("timestamp", "")[:22]
            detail = ""

            if event_type == "task.started":
                detail = "agent loop 启动"
            elif event_type == "step.update":
                step_count += 1
                label = event.get("label", "")
                status = event.get("status", "")
                detail = f"[{status}] {label}: {event.get('detail', '')}"
            elif event_type == "tool.started":
                tool_count += 1
                detail = f"调用 {event.get('tool', '')}"
            elif event_type == "tool.completed":
                result_data = event.get("result", "")
                if isinstance(result_data, str) and len(result_data) > 120:
                    result_data = result_data[:120] + "..."
                detail = f"✓ {event.get('tool', '')}"
            elif event_type == "tool.blocked":
                detail = f"🚫 阻止: {event.get('reason', '')}"
            elif event_type == "approval.requested":
                detail = f"🔒 等待审批: {event.get('tool', '')}"
            elif event_type in ("task.completed", "task.failed", "task.cancelled"):
                final_reply = event.get("reply", event.get("error", ""))
                detail = f"{'✅' if event_type == 'task.completed' else '❌'} {event_type}"
            elif event_type == "done":
                break
            elif event_type == "heartbeat":
                continue
            else:
                detail = json.dumps(event, ensure_ascii=False)[:150]

            if detail:
                print(f"  {timestamp:<22} {event_type:<28} {detail}")

        print()
        print("── 结果 ──")
        status = await svc.get_task_status(task_id)
        print(f"  状态    : {status['status']}")
        print(f"  步骤数  : {step_count}")
        print(f"  工具调用: {tool_count}")
        print(f"  事件数  : {status.get('event_count', 0)}")

        if final_reply:
            print(f"\n  Agent 回复:\n  {'─'*50}")
            for line in final_reply.splitlines()[:30]:
                print(f"  {line}")

        print()
        print("── 任务事件（来自数据库）──")
        for event in store.list_events(task_id):
            print(f"  [{event['event_type']}] {event['created_at'][:25]}")
            payload = event.get("payload", {})
            if payload:
                payload_str = json.dumps(payload, ensure_ascii=False)[:200]
                print(f"    {payload_str}")

    asyncio.run(run())


if __name__ == "__main__":
    main()
