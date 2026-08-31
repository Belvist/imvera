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
export MOSS_ESL_PASSWORD="c864dbaf8393145ff78cdd1dd1fc9fdc"

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
