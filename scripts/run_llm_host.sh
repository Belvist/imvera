#!/usr/bin/env bash
# MossVoice host LLM launcher (Metal llama.cpp, 2026-09-04).
#
# Runs llama-server on the HOST with GPU layers so telephony in Docker can
# reach it at host.docker.internal:9500. Mirrors scripts/llama_entrypoint.sh
# flags; STT already uses the same pattern on :9705 (com.mossvoice.stt).
#
# launchd: scripts/com.mossvoice.llm.plist (KeepAlive) — log /tmp/mossvoice_llm.log
# Copy this script to ~/Library/Application Support/MossVoice/ if launchd
# cannot execute from ~/Downloads (see docs/HOST_LLM_METAL.md).
set -uo pipefail

REPO="${MOSS_REPO:-}"
if [ -z "$REPO" ]; then
  REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fi

MODEL_URL="${MOSS_LLM_GGUF_URL:-https://huggingface.co/unsloth/Qwen3-4B-GGUF/resolve/main/Qwen3-4B-Q4_K_M.gguf}"
DEFAULT_MODEL_DIR="${MOSS_LLM_MODEL_DIR:-$HOME/Library/Application Support/MossVoice/models/llm}"
DEFAULT_MODEL_FILE="$DEFAULT_MODEL_DIR/Qwen3-4B-Q4_K_M.gguf"

find_llama_server() {
  if [ -n "${MOSS_LLM_SERVER_BIN:-}" ] && [ -x "$MOSS_LLM_SERVER_BIN" ]; then
    echo "$MOSS_LLM_SERVER_BIN"
    return 0
  fi
  local candidate brew_prefix
  candidate="$(command -v llama-server 2>/dev/null || true)"
  if [ -n "$candidate" ] && [ -x "$candidate" ]; then
    echo "$candidate"
    return 0
  fi
  for candidate in \
    /opt/homebrew/bin/llama-server \
    /usr/local/bin/llama-server; do
    if [ -x "$candidate" ]; then
      echo "$candidate"
      return 0
    fi
  done
  brew_prefix="$(brew --prefix llama.cpp 2>/dev/null || true)"
  if [ -n "$brew_prefix" ] && [ -x "$brew_prefix/bin/llama-server" ]; then
    echo "$brew_prefix/bin/llama-server"
    return 0
  fi
  echo "run_llm_host: llama-server not found — install with: brew install llama.cpp" >&2
  exit 1
}

docker_volume_model() {
  python3 - <<'PYEOF'
import json
import os
import subprocess
import sys

target = "llm/Qwen3-4B-Q4_K_M.gguf"
for name in ("docker_models", "mossvoice_models", "mossvoice-docker_models"):
    try:
        out = subprocess.check_output(
            ["docker", "volume", "inspect", name],
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        continue
    mount = json.loads(out)[0].get("Mountpoint") or ""
    for sub in ("_data", "llm"):
        candidate = os.path.join(mount, sub, "llm", "Qwen3-4B-Q4_K_M.gguf")
        if os.path.isfile(candidate) and os.path.getsize(candidate) > 0:
            print(candidate)
            raise SystemExit(0)
        candidate = os.path.join(mount, sub, "Qwen3-4B-Q4_K_M.gguf")
        if os.path.isfile(candidate) and os.path.getsize(candidate) > 0:
            print(candidate)
            raise SystemExit(0)
    candidate = os.path.join(mount, target)
    if os.path.isfile(candidate) and os.path.getsize(candidate) > 0:
        print(candidate)
        raise SystemExit(0)
PYEOF
}

resolve_model_file() {
  if [ -n "${MOSS_LLM_GGUF_FILE:-}" ]; then
    echo "$MOSS_LLM_GGUF_FILE"
    return 0
  fi
  if [ -s "$DEFAULT_MODEL_FILE" ]; then
    echo "$DEFAULT_MODEL_FILE"
    return 0
  fi
  local from_docker
  from_docker="$(docker_volume_model 2>/dev/null || true)"
  if [ -n "$from_docker" ] && [ -s "$from_docker" ]; then
    echo "$from_docker"
    return 0
  fi
  echo "$DEFAULT_MODEL_FILE"
}

download_model() {
  local dest="$1"
  mkdir -p "$(dirname "$dest")"
  echo "[llm-host] downloading $MODEL_URL ..."
  curl -fL --retry 3 --retry-all-errors -o "$dest.part" "$MODEL_URL"
  mv "$dest.part" "$dest"
  echo "[llm-host] downloaded $(du -h "$dest" | cut -f1)"
}

LLAMA_BIN="$(find_llama_server)"
MODEL_FILE="$(resolve_model_file)"
if [ ! -s "$MODEL_FILE" ]; then
  download_model "$MODEL_FILE"
fi
if [ ! -s "$MODEL_FILE" ]; then
  echo "run_llm_host: model missing at $MODEL_FILE" >&2
  exit 1
fi

PORT="${MOSS_LLM_PORT:-9500}"
HOST_BIND="${MOSS_LLM_HOST:-127.0.0.1}"
INTERNAL_PORT="${MOSS_LLM_INTERNAL_PORT:-9501}"
THREADS="${MOSS_LLM_THREADS:-4}"
CTX="${MOSS_LLM_CTX:-4096}"
GPU_LAYERS="${MOSS_LLM_N_GPU_LAYERS:-99}"

MODEL_BASENAME="$(basename "$MODEL_FILE" .gguf)"
export MOSS_LLM_MODEL_ID="${MOSS_LLM_MODEL_ID:-$MODEL_BASENAME}"
export MOSS_LLM_REVISION="${MOSS_LLM_REVISION:-main}"
export MOSS_LLM_BACKEND="${MOSS_LLM_BACKEND:-llama.cpp}"
export MOSS_LLM_PROTOCOL="${MOSS_LLM_PROTOCOL:-openai}"
export MOSS_LLM_DEVICE="${MOSS_LLM_DEVICE:-metal}"

echo "[llm-host] gateway ${HOST_BIND}:${PORT} → llama :${INTERNAL_PORT} model=$MOSS_LLM_MODEL_ID" >&2

exec python3 "$REPO/scripts/stage_a_llm_gateway.py" \
  --host "$HOST_BIND" \
  --port "$PORT" \
  --internal-port "$INTERNAL_PORT" \
  --llama-cmd \
  "$LLAMA_BIN" \
  --host "$HOST_BIND" \
  --port "$INTERNAL_PORT" \
  --model "$MODEL_FILE" \
  --threads "$THREADS" \
  --ctx-size "$CTX" \
  --parallel 1 \
  --n-gpu-layers "$GPU_LAYERS" \
  --mlock \
  --cache-reuse 256 \
  --cont-batching
