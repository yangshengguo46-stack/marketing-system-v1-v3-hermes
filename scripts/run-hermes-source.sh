#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_HOME="$HOME/Library/Application Support/marketing-os-desktop"
SECRETS="$APP_HOME/secrets/providers.env"

if [[ -f "$SECRETS" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$SECRETS"
  set +a
fi

export HERMES_HOME="$APP_HOME/agent-runtime"
export HERMES_AGENT_ROOT="$ROOT/runtime/hermes-agent"
exec "$ROOT/runtime/hermes-agent/.venv/bin/hermes" "$@"

