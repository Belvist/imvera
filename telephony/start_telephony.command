#!/bin/zsh
# MossVoice Telephony — production start (one supervisor, four services):
#   1. FreeSWITCH (SIP server) — only if installed
#   2. moss_supervisor.py ->
#        answers    llm_server.py   127.0.0.1:9500  (генерация ответов, Qwen3)
#        voice      tts_server.py   127.0.0.1:9600  (TTS only — --no-stt)
#        telephony  call_agent.py   127.0.0.1:9400  (legacy STT + диалоговый движок)
#        runtime    voice_runtime.py 127.0.0.1:9700 (VoiceRuntime / G3)
#   read.md rev-3/rev-4: STT (Whisper) lives in the telephony process on the
#   phone path; the voice daemon deploys --no-stt so Whisper is NOT loaded
#   twice. If/when a separate STT service lands, update ONLY this block.
set -e

TEL="$(cd "$(dirname "$0")" && pwd)"
RUNTIME="$HOME/Library/Application Support/MossVoice/runtime"
PY="$RUNTIME/qwen-venv/bin/python"
FS_BIN="/opt/homebrew/opt/freeswitch/bin/freeswitch"
FS_CLI="/opt/homebrew/opt/freeswitch/bin/fs_cli"

# Never embed ESL credentials in a tracked launcher. Use the same protected
# source as scripts/run_runtime.sh so a password rotation cannot leave one
# process on a stale hardcoded value.
if [[ -z "${MOSS_ESL_PASSWORD:-}" ]]; then
  ESL_CONF="$HOME/.fs_cli_conf"
  if [[ ! -r "$ESL_CONF" ]]; then
    echo "[moss] ERROR: $ESL_CONF not readable — set MOSS_ESL_PASSWORD" >&2
    exit 1
  fi
  MOSS_ESL_PASSWORD="$(
    python3 - "$ESL_CONF" <<'PYEOF'
import re
import sys

with open(sys.argv[1], encoding="utf-8") as config:
    match = re.search(r"^password\s*=>\s*(\S+)", config.read(), re.M)
print(match.group(1) if match else "")
PYEOF
  )"
  if [[ -z "$MOSS_ESL_PASSWORD" ]]; then
    echo "[moss] ERROR: no ESL password in $ESL_CONF" >&2
    exit 1
  fi
  export MOSS_ESL_PASSWORD
fi

# Host FreeSWITCH/Lua must use the same optional control-plane token as the
# Compose services. Parse one exact key; never `source` docker/.env.
if [[ -z "${MOSS_INTERNAL_API_TOKEN:-}" && -r "$TEL/../docker/.env" ]]; then
  MOSS_INTERNAL_API_TOKEN="$(
    python3 - "$TEL/../docker/.env" <<'PYEOF'
import re
import sys

with open(sys.argv[1], encoding="utf-8") as config:
    match = re.search(r"^MOSS_INTERNAL_API_TOKEN=(\S+)\s*$",
                      config.read(), re.M)
print(match.group(1) if match else "")
PYEOF
  )"
  if [[ -n "$MOSS_INTERNAL_API_TOKEN" ]]; then
    export MOSS_INTERNAL_API_TOKEN
  fi
fi

log() { echo "[moss] $*"; }

if [[ ! -x "$PY" ]]; then
  log "ERROR: $PY not found — install the backend first (MossVoice.app -> Установить)"
  exit 1
fi

# --- 1. FreeSWITCH (optional; SIP calls only) ------------------------------
if [[ -x "$FS_BIN" ]]; then
  if ! pgrep -f "bin/freeswitch" >/dev/null 2>&1; then
    log "Starting FreeSWITCH..."
    "$FS_BIN" -nc -nonat > "$TEL/freeswitch.log" 2>&1 &
    sleep 8
  else
    log "FreeSWITCH already running."
  fi
else
  log "FreeSWITCH not installed — SIP extension 4401 unavailable (Telegram bridge still works)."
fi

# --- 2. The three core services --------------------------------------------
log "Starting the service supervisor (voice + answers + telephony)..."
"$PY" "$TEL/moss_supervisor.py" start --daemon

for i in {1..60}; do
  "$PY" "$TEL/moss_supervisor.py" status 2>/dev/null | grep -q "running pid" && break
  sleep 1
done

"$PY" "$TEL/moss_supervisor.py" status

log ""
log "=== СЕРВИСЫ ЗАПУЩЕНЫ ==="
log "Голос (voice)       : http://127.0.0.1:9600"
log "Генерация (answers) : http://127.0.0.1:9500"
log "Телефония (agent)   : http://127.0.0.1:9400"
if [[ -x "$FS_CLI" ]]; then
  log "SIP: номер агента 4400 (алиас 4401); тест: $FS_CLI -x \"originate loopback/4402/default &echo\""
fi
log "Остановка: $(dirname "$0")/moss_supervisor.py stop"
