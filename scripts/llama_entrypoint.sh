#!/bin/sh
# Answers (LLM) service entrypoint for the Docker stack.
#
# Downloads the pinned Qwen3-4B GGUF into the shared /data/models volume on
# first boot (or when MOSS_LLM_GGUF_URL changes), then starts llama-server
# (OpenAI-compatible API on :9500). The volume survives image rebuilds, so
# `make update` never re-downloads the weights.
#
# Overrides:
#   MOSS_LLM_GGUF_URL   alternative GGUF URL (default unsloth Qwen3-4B Q4_K_M)
#   MOSS_LLM_GGUF_FILE  target path inside the container
#   MOSS_LLM_THREADS    llama.cpp threads (default 6)
#   MOSS_LLM_CTX        context size (default 4096)
set -eu

MODEL_URL="${MOSS_LLM_GGUF_URL:-https://huggingface.co/unsloth/Qwen3-4B-GGUF/resolve/main/Qwen3-4B-Q4_K_M.gguf}"
MODEL_FILE="${MOSS_LLM_GGUF_FILE:-/data/models/llm/Qwen3-4B-Q4_K_M.gguf}"

if [ ! -s "$MODEL_FILE" ]; then
  mkdir -p "$(dirname "$MODEL_FILE")"
  echo "[llama] downloading $MODEL_URL ..."
  curl -fL --retry 3 --retry-all-errors -o "$MODEL_FILE.part" "$MODEL_URL"
  mv "$MODEL_FILE.part" "$MODEL_FILE"
  echo "[llama] downloaded $(du -h "$MODEL_FILE" | cut -f1)"
fi

exec /app/llama-server \
  --host 0.0.0.0 --port 9500 \
  --model "$MODEL_FILE" \
  --threads "${MOSS_LLM_THREADS:-8}" \
  --ctx-size "${MOSS_LLM_CTX:-2048}" \
  --parallel 1 \
  --mlock \
  --cache-reuse 256 \
  --cont-batching