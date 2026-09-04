#!/usr/bin/env bash
# Stage A text lab — minimal RAM footprint (LLM host only, no full Docker stack).
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE="docker compose -f ${REPO}/docker/docker-compose.yml"

_health_ready() {
  curl -sf http://127.0.0.1:9500/health 2>/dev/null \
    | python3 -c "import sys,json; d=json.load(sys.stdin); sys.exit(0 if d.get('ready') else 1)" \
    2>/dev/null
}

echo "[golden-dev-up] Stopping heavy production services (if running)..."
# Stage A text lab needs host LLM only — no telephony/STT/TTS/voice/workflow.
$COMPOSE stop telephony voice answers workflow scheduler 2>/dev/null || true
docker stop mossvoice-tg 2>/dev/null || true

if _health_ready; then
  echo "[golden-dev-up] LLM gateway already ready on :9500"
else
  echo "[golden-dev-up] Starting host LLM (run_llm_host.sh)..."
  bash "${REPO}/scripts/golden_dev_down.sh" >/dev/null 2>&1 || true
  nohup bash "${REPO}/scripts/run_llm_host.sh" >> /tmp/mossvoice_llm.log 2>&1 &
  for _ in $(seq 1 90); do
    if _health_ready; then
      break
    fi
    sleep 2
  done
fi

if _health_ready; then
  curl -sf http://127.0.0.1:9500/health
  echo ""
  echo "[golden-dev-up] Ready — text lab path: Golden Path + :9500 only."
  echo "  make test-golden-path"
  echo "  python3 scripts/run_vera_text_lab.py"
else
  echo "[golden-dev-up] LLM gateway not ready — check /tmp/mossvoice_llm.log" >&2
  exit 1
fi
