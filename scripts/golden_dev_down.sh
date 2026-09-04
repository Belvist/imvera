#!/usr/bin/env bash
# Stop Stage A dev LLM host (does not restart full Docker stack).
set -euo pipefail

echo "[golden-dev-down] Stopping mossvoice LLM host processes..."
pkill -f "stage_a_llm_gateway.py" 2>/dev/null || true
pkill -f "llama-server.*9501" 2>/dev/null || true
pkill -f "run_llm_host.sh" 2>/dev/null || true
echo "[golden-dev-down] Done. Full stack: make up"
