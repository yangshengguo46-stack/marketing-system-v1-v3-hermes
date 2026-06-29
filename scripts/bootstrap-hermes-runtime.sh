#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HERMES_SOURCE="$ROOT/runtime/hermes-agent"
VENV="$HERMES_SOURCE/.venv"
APP_HOME="$HOME/Library/Application Support/marketing-os-desktop"
RUNTIME_HOME="$APP_HOME/agent-runtime"
SECRET_DIR="$APP_HOME/secrets"

if [[ ! -d "$HERMES_SOURCE/.git" ]]; then
  echo "Hermes source is missing at $HERMES_SOURCE" >&2
  exit 1
fi

mkdir -p "$RUNTIME_HOME" "$SECRET_DIR"
chmod 700 "$APP_HOME" "$RUNTIME_HOME" "$SECRET_DIR"

if [[ ! -x "$VENV/bin/python" ]]; then
  uv venv "$VENV" --python 3.13
fi

uv pip install --python "$VENV/bin/python" -e "$HERMES_SOURCE"

if [[ -f "$SECRET_DIR/provider-config.yaml" && ! -f "$RUNTIME_HOME/config.yaml" ]]; then
  cp "$SECRET_DIR/provider-config.yaml" "$RUNTIME_HOME/config.yaml"
  chmod 600 "$RUNTIME_HOME/config.yaml"
fi

export HERMES_HOME="$RUNTIME_HOME"
export HERMES_AGENT_ROOT="$HERMES_SOURCE"
"$VENV/bin/hermes" config migrate </dev/null
"$VENV/bin/hermes" config set memory.write_approval true
"$VENV/bin/hermes" config set skills.write_approval true
"$VENV/bin/hermes" config set skills.guard_agent_created true
"$VENV/bin/hermes" config set skills.inline_shell false
"$VENV/bin/hermes" config set delegation.subagent_auto_approve false
"$VENV/bin/hermes" config set approvals.mode manual
"$VENV/bin/hermes" config set approvals.cron_mode deny
"$VENV/bin/hermes" config set security.tirith_fail_open false

echo "Hermes source runtime ready: $VENV"
echo "Product runtime data: $RUNTIME_HOME"
