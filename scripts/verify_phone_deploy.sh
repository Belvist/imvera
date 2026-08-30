#!/usr/bin/env bash
# Post-deploy smoke test for IMVERA phone path (run ON THE MAC after make up).
set -uo pipefail

AGENT_PORT="${MOSS_AGENT_PORT:-9400}"
STT_PORT="${MOSS_STT_HOST_PORT:-9705}"
RT_PORT="${MOSS_RUNTIME_PORT:-9700}"
FS_CLI="$(command -v fs_cli || echo /opt/homebrew/bin/fs_cli)"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

fail=0
ok()  { echo "  OK  $*"; }
warn(){ echo "  WARN $*"; fail=1; }
bad() { echo "  FAIL $*"; fail=1; }

echo "=== IMVERA phone deploy verify ==="

# 1. Telephony health (STT + TTS must be usable)
echo "[1] telephony /health :$AGENT_PORT"
if H=$(curl -sf -m 5 "http://127.0.0.1:$AGENT_PORT/health" 2>/dev/null); then
  python3 - "$H" <<'PY' || bad "telephony health JSON unexpected"
import json, sys
d = json.loads(sys.argv[1])
c = d.get("components") or {}
if not c.get("stt"): sys.exit("stt not ready")
if not c.get("tts"): sys.exit("tts not ready")
if d.get("ok") is not True: sys.exit("ok!=true")
print("stt+tts ready, ok=true")
PY
  ok "telephony healthy"
else
  bad "cannot reach http://127.0.0.1:$AGENT_PORT/health"
fi

# 2. STT host (Qwen3 on Mac)
echo "[2] STT host /ready :$STT_PORT"
if curl -sf -m 3 "http://127.0.0.1:$STT_PORT/ready" 2>/dev/null | grep -q '"ready"'; then
  ok "STT host reachable"
else
  warn "STT host not ready (launchctl start com.mossvoice.stt)"
fi

# 3. check_in arms on bare POST /calls (core fix 2dad91d)
echo "[3] POST /calls -> check_in agenda"
CID=$(curl -sf -m 5 -X POST "http://127.0.0.1:$AGENT_PORT/calls" \
  -H 'Content-Type: application/json' -d '{"mode":"check_in"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin).get('call_id',''))" 2>/dev/null)
if [ -n "$CID" ]; then
  curl -sf -m 5 -X POST "http://127.0.0.1:$AGENT_PORT/calls/$CID/end" \
    -H 'Content-Type: application/json' -d '{}' >/dev/null 2>&1 || true
  ok "new_call check_in (call_id=$CID)"
else
  bad "POST /calls failed"
fi

# 4. Container has the fix (grep start_check_in in deployed code)
echo "[4] telephony image contains check_in fix"
if command -v docker >/dev/null 2>&1; then
  if docker compose -f "$REPO/docker/docker-compose.yml" ps telephony 2>/dev/null \
     | grep -qE 'Up|healthy|running'; then
    if docker compose -f "$REPO/docker/docker-compose.yml" exec -T telephony \
       grep -q 'start_check_in()' /app/telephony/core/orchestrator.py 2>/dev/null; then
      ok "orchestrator start_check_in in container"
    else
      bad "container missing fix — run: make up telephony"
    fi
  else
    warn "telephony container not Up — run: make up telephony"
  fi
else
  warn "docker not in PATH — skip container grep"
fi

# 5. FreeSWITCH + dialplan 4400
echo "[5] FreeSWITCH 4400 route"
if "$FS_CLI" -x "status" >/dev/null 2>&1; then
  ok "fs_cli connected"
  DP=$("$FS_CLI" -x "xml_locate dialplan" 2>/dev/null | grep -c '4400' || true)
  if [ "${DP:-0}" -gt 0 ]; then
    ok "dialplan mentions 4400"
  else
    warn "no 4400 in dialplan — check mossvoice.xml or moss_dialplan.xml"
  fi
  if "$FS_CLI" -x 'eval ${default_password}' 2>/dev/null | grep -qx '1234'; then
    bad "default_password still 1234 — 10s silence before answer!"
  else
    ok "default_password not stock 1234"
  fi
else
  warn "fs_cli cannot connect — is FreeSWITCH running?"
fi

# 6. Lua script (if legacy route)
FS_SCRIPTS="${FS_PREFIX:-/opt/homebrew}/etc/freeswitch/scripts"
[ -d "/opt/homebrew/Cellar/freeswitch" ] && \
  FS_SCRIPTS="$(ls -d /opt/homebrew/Cellar/freeswitch/*/etc/freeswitch/scripts 2>/dev/null | tail -1)"
echo "[6] moss_agent.lua check_in (if Lua route)"
if [ -f "$FS_SCRIPTS/moss_agent.lua" ]; then
  if grep -q 'mode":"check_in"' "$FS_SCRIPTS/moss_agent.lua" 2>/dev/null \
     || grep -q "mode\":\"check_in\"" "$FS_SCRIPTS/moss_agent.lua" 2>/dev/null; then
    ok "installed moss_agent.lua has check_in"
  else
    warn "moss_agent.lua OLD — cp $REPO/telephony/moss_agent.lua $FS_SCRIPTS/ (or rely on server-side fix if telephony rebuilt)"
  fi
else
  ok "no moss_agent.lua (VoiceRuntime route — check runtime /ready)"
  if curl -sf -m 3 "http://127.0.0.1:$RT_PORT/ready" 2>/dev/null | grep -q '"ready": true'; then
    ok "VoiceRuntime ready on :$RT_PORT"
  else
    warn "VoiceRuntime /ready not OK — launchctl start com.mossvoice.runtime"
  fi
fi

echo ""
if [ "$fail" -eq 0 ]; then
  echo "RESULT: PASS — можно звонить на 4400 (Zoiper, микрофон MacBook, не AirPods)."
  exit 0
fi
echo "RESULT: WARN/FAIL — исправь пункты FAIL/WARN выше, затем перезапусти."
exit 1
