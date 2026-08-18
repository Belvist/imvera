#!/bin/zsh
# MossVoice Telegram voice bridge — start tunnel + tg_server + bot together.
#
# On every run it (re)starts cloudflared, waits for the fresh trycloudflare URL,
# and (re)starts the bot with that URL, so the Telegram button always points at
# a live tunnel.
#
#   ./start_tg.sh                # uses $MOSSVOICE_BOT_TOKEN or reads ./bot.token
#   MOSSVOICE_BOT_TOKEN=... ./start_tg.sh
set -e

TG="$(cd "$(dirname "$0")" && pwd)"
if [[ -n "${MOSS_PY:-}" ]]; then
  PY="$MOSS_PY"
elif [[ -x "$TG/../../runtime/qwen-venv/bin/python" ]]; then
  PY="$(cd "$TG/../.." && pwd)/runtime/qwen-venv/bin/python"
else
  PY="$HOME/Library/Application Support/MossVoice/runtime/qwen-venv/bin/python"
fi
TG_SERVER_PORT=8600
CFLOG="$TG/cloudflared.log"
BOTLOG="$TG/bot.log"
TOKEN_FILE="$TG/bot.token"

# --- 0. Bot token ---------------------------------------------------------
if [[ -z "${MOSSVOICE_BOT_TOKEN:-}" && -f "$TOKEN_FILE" ]]; then
  MOSSVOICE_BOT_TOKEN="$(tr -d '\n' < "$TOKEN_FILE")"
fi
if [[ -z "${MOSSVOICE_BOT_TOKEN:-}" ]]; then
  echo "ERROR: set MOSSVOICE_BOT_TOKEN or put the token in $TOKEN_FILE" >&2
  exit 1
fi

log() { echo "[tg] $*"; }

# --- 0.5. Core services (voice + answers + telephony) ---------------------
# The Telegram gateway needs the call agent on 9400. If the supervisor is not
# running (nothing on 9400), bring it up first so the bridge never hangs on a
# dead downstream.
if ! curl -sf "http://127.0.0.1:9400/health" >/dev/null 2>&1; then
  log "Core services not running — starting supervisor first..."
  "$PY" "$TG/../moss_supervisor.py" start --daemon || true
  for i in {1..30}; do
    curl -sf "http://127.0.0.1:9400/health" >/dev/null 2>&1 && break
    sleep 1
  done
fi

# --- 1. tg_server ---------------------------------------------------------
# SECURITY: pass the token via ENV (MOSSVOICE_BOT_TOKEN) instead of a CLI arg,
# so it never shows up in `ps` for every local user on this machine.
export MOSSVOICE_BOT_TOKEN
pkill -f "tg_server.py.*--port $TG_SERVER_PORT" 2>/dev/null || true
sleep 1
EXTRA_ARGS=()
if [[ "${MOSS_TG_ALLOW_UNVERIFIED:-}" == "1" ]]; then
  EXTRA_ARGS+=(--allow-unverified)
  log "Starting tg_server on $TG_SERVER_PORT (initData check: OFF — DEV MODE, browser testing)..."
else
  log "Starting tg_server on $TG_SERVER_PORT (initData check: on)..."
fi
nohup "$PY" "$TG/tg_server.py" --port "$TG_SERVER_PORT" --web-dir "$TG/web" "${EXTRA_ARGS[@]}" \
  > "$TG/tg_server.log" 2>&1 &
for i in {1..40}; do
  curl -sf "http://127.0.0.1:$TG_SERVER_PORT/health" >/dev/null 2>&1 && break
  sleep 0.5
done
curl -sf "http://127.0.0.1:$TG_SERVER_PORT/health" >/dev/null 2>&1 \
  || { log "ERROR: tg_server did not come up"; exit 1; }
log "tg_server ready."

# --- 2. cloudflared -------------------------------------------------------
pkill -x cloudflared 2>/dev/null || true
sleep 1
log "Starting cloudflared tunnel -> http://127.0.0.1:$TG_SERVER_PORT ..."
nohup /opt/homebrew/bin/cloudflared tunnel \
  --url "http://127.0.0.1:$TG_SERVER_PORT" > "$CFLOG" 2>&1 &

URL=""
for i in {1..40}; do
  URL="$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$CFLOG" | head -1)"
  [[ -n "$URL" ]] && break
  sleep 0.5
done
if [[ -z "$URL" ]]; then
  log "ERROR: could not obtain trycloudflare URL from $CFLOG"; exit 1
fi
log "Tunnel ready: $URL"

# --- 3. bot ---------------------------------------------------------------
# SECURITY: same as above — token travels via MOSSVOICE_BOT_TOKEN env, not argv.
pkill -f "$TG/bot.py" 2>/dev/null || true
sleep 1
log "Starting bot with webapp=$URL ..."
nohup "$PY" "$TG/bot.py" --webapp-url "$URL" > "$BOTLOG" 2>&1 &
sleep 3
if pgrep -f "$TG/bot.py" >/dev/null 2>&1; then
  log "Bot running. Press the Позвонить button in Telegram."
else
  log "ERROR: bot exited — see $BOTLOG"; tail -5 "$BOTLOG"; exit 1
fi
