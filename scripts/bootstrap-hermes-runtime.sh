#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HERMES_SOURCE="$ROOT/runtime/hermes-agent"
HERMES_REMOTE="https://github.com/NousResearch/hermes-agent.git"
HERMES_BASELINE="4488fe134b1de4359f3a4f1f8368576413e6e268"
HERMES_PRODUCT_TREE="39acd04e2b7d84424ac381c0f77c647127744e24"
PATCH_DIR="$ROOT/runtime/hermes-patches"
VENV="$HERMES_SOURCE/.venv"
APP_HOME="$HOME/Library/Application Support/marketing-os-desktop"
RUNTIME_HOME="$APP_HOME/agent-runtime"
SECRET_DIR="$APP_HOME/secrets"

if [[ ! -d "$HERMES_SOURCE/.git" ]]; then
  mkdir -p "$(dirname "$HERMES_SOURCE")"
  git clone --filter=blob:none --no-checkout "$HERMES_REMOTE" "$HERMES_SOURCE"
  git -C "$HERMES_SOURCE" checkout --detach "$HERMES_BASELINE"
fi

if [[ -n "$(git -C "$HERMES_SOURCE" status --porcelain)" ]]; then
  echo "Hermes source has local changes; refusing to overwrite $HERMES_SOURCE" >&2
  exit 1
fi

CURRENT_TREE="$(git -C "$HERMES_SOURCE" rev-parse HEAD^{tree})"
if [[ "$CURRENT_TREE" != "$HERMES_PRODUCT_TREE" ]]; then
  CURRENT_HEAD="$(git -C "$HERMES_SOURCE" rev-parse HEAD)"
  if [[ "$CURRENT_HEAD" != "$HERMES_BASELINE" ]]; then
    echo "Unexpected Hermes revision $CURRENT_HEAD (expected baseline or product tree)" >&2
    exit 1
  fi
  shopt -s nullglob
  PATCHES=("$PATCH_DIR"/*.patch)
  if [[ ${#PATCHES[@]} -eq 0 ]]; then
    echo "No Hermes product patches found in $PATCH_DIR" >&2
    exit 1
  fi
  git -C "$HERMES_SOURCE" am --committer-date-is-author-date "${PATCHES[@]}"
  CURRENT_TREE="$(git -C "$HERMES_SOURCE" rev-parse HEAD^{tree})"
fi

if [[ "$CURRENT_TREE" != "$HERMES_PRODUCT_TREE" ]]; then
  echo "Hermes product tree mismatch: $CURRENT_TREE" >&2
  exit 1
fi

echo "Hermes source verified: $(git -C "$HERMES_SOURCE" rev-parse --short HEAD)"

if [[ "${HERMES_SKIP_INSTALL:-0}" == "1" ]]; then
  exit 0
fi

mkdir -p "$RUNTIME_HOME" "$SECRET_DIR"
chmod 700 "$APP_HOME" "$RUNTIME_HOME" "$SECRET_DIR"

if [[ ! -x "$VENV/bin/python" ]]; then
  uv venv "$VENV" --python 3.13
fi

uv pip install --python "$VENV/bin/python" -e "$HERMES_SOURCE[mcp,feishu]"
uv pip install --python "$VENV/bin/python" aiohttp==3.13.4
uv pip install --python "$VENV/bin/python" "python-socks[asyncio]==2.8.2"

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
