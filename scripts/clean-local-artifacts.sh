#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "[clean] removing generated app/build artifacts"
rm -rf release backend/build backend/dist dist build/mcp-runtime

echo "[clean] removing local test/browser caches"
rm -rf .playwright-mcp .pytest_cache .pytest-cache .ruff_cache .mypy_cache htmlcov .coverage

echo "[clean] removing Python bytecode outside vendored runtime/dependencies"
find . \
  -path './node_modules' -prune -o \
  -path './.venv' -prune -o \
  -path './runtime/hermes-agent' -prune -o \
  -name '__pycache__' -type d -prune -exec rm -rf {} +
find . \
  -path './node_modules' -prune -o \
  -path './.venv' -prune -o \
  -path './runtime/hermes-agent' -prune -o \
  -name '*.pyc' -type f -delete

echo "[clean] done"
