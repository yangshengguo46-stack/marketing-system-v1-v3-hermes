#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SOURCE="$ROOT/runtime/index-tts"
MODEL_DIR="$SOURCE/checkpoints"
ZIP_URL="https://github.com/index-tts/index-tts/archive/refs/heads/main.zip"
MAX_WORKERS="${INDEXTTS2_DOWNLOAD_WORKERS:-4}"

mkdir -p "$ROOT/runtime"

if [[ ! -f "$SOURCE/indextts/cli_v2.py" ]]; then
  echo "[index-tts2] downloading official source zip"
  TMP_ZIP="${TMPDIR:-/tmp}/index-tts-main.zip"
  TMP_DIR="${TMPDIR:-/tmp}/index-tts-main"
  rm -rf "$SOURCE" "$TMP_ZIP" "$TMP_DIR"
  curl -L --fail --retry 3 --retry-delay 2 -o "$TMP_ZIP" "$ZIP_URL"
  unzip -q "$TMP_ZIP" -d "${TMPDIR:-/tmp}"
  mv "$TMP_DIR" "$SOURCE"
  printf '%s\n' "$ZIP_URL" > "$SOURCE/.source-url"
else
  echo "[index-tts2] source already present: $SOURCE"
fi

if ! command -v modelscope >/dev/null 2>&1; then
  echo "[index-tts2] installing ModelScope CLI with Python 3.11"
  PYTHON_311="${PYTHON_311:-}"
  if [[ -z "$PYTHON_311" ]]; then
    if command -v python3.11 >/dev/null 2>&1; then
      PYTHON_311="$(command -v python3.11)"
    elif [[ -x /usr/local/bin/python3.11 ]]; then
      PYTHON_311="/usr/local/bin/python3.11"
    else
      echo "[index-tts2] Python 3.11 is required for ModelScope CLI on this machine" >&2
      exit 1
    fi
  fi
  uv tool install --python "$PYTHON_311" --with 'setuptools<81' modelscope==1.27.0
fi

mkdir -p "$MODEL_DIR"
echo "[index-tts2] downloading model resources to $MODEL_DIR"
modelscope download --model IndexTeam/IndexTTS-2 --local_dir "$MODEL_DIR" --max-workers "$MAX_WORKERS"

echo "[index-tts2] done"
echo "Check with:"
echo "  cd \"$SOURCE\" && uv run indextts2 check --model-dir \"$MODEL_DIR\""
