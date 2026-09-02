#!/usr/bin/env bash
# MossVoice VoiceRuntime launcher (P8, 2026-08-29).
#
# Runs the runtime supervisor (telephony/moss_supervisor.py --service runtime)
# in the FOREGROUND so launchd can keep it alive (KeepAlive=true). The
# runtime lives on the HOST next to FreeSWITCH: it reaches ESL at
# 127.0.0.1:8021 and the compose telephony at 127.0.0.1:9400, and shares
# /tmp/mossvoice with both (files must be the same paths for uuid_broadcast
# playback). A container cannot reach the loopback-bound ESL port, so this
# host-side deployment is the correct shape here.
#
# The FreeSWITCH ESL password is read from ~/.fs_cli_conf (chmod 600) so it
# never appears in the repo, a plist, or launchctl env. Override with
# MOSS_ESL_PASSWORD.
set -uo pipefail

REPO="${MOSS_REPO:-}"
if [ -z "$REPO" ]; then
  REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fi

# --- ESL password -------------------------------------------------------------
if [ -z "${MOSS_ESL_PASSWORD:-}" ]; then
  CONF="$HOME/.fs_cli_conf"
  if [ ! -r "$CONF" ]; then
    echo "run_runtime: $CONF not readable — set MOSS_ESL_PASSWORD" >&2
    exit 1
  fi
  PW="$(python3 - "$CONF" <<'PYEOF'
import os, re, sys
p = sys.argv[1]
try:
    s = open(p).read()
except OSError:
    raise SystemExit(1)
m = re.search(r"^password\s*=>\s*(\S+)", s, re.M)
print(m.group(1) if m else "")
PYEOF
)"
  if [ -z "$PW" ]; then
    echo "run_runtime: no password line in $CONF" >&2
    exit 1
  fi
  export MOSS_ESL_PASSWORD="$PW"
fi

# --- agent control-plane token -----------------------------------------------
# Docker Compose reads docker/.env automatically; the host VoiceRuntime does
# not. Load only this exact key (never source the whole file as shell code).
if [ -z "${MOSS_INTERNAL_API_TOKEN:-}" ] && [ -r "$REPO/docker/.env" ]; then
  API_TOKEN="$(python3 - "$REPO/docker/.env" <<'PYEOF'
import re
import sys

with open(sys.argv[1], encoding="utf-8") as config:
    match = re.search(r"^MOSS_INTERNAL_API_TOKEN=(\S+)\s*$",
                      config.read(), re.M)
print(match.group(1) if match else "")
PYEOF
)"
  if [ -n "$API_TOKEN" ]; then
    export MOSS_INTERNAL_API_TOKEN="$API_TOKEN"
  fi
fi

# --- interpreter --------------------------------------------------------------
PY="${MOSS_PY:-}"
if [ -z "$PY" ]; then
  if [ -x "$REPO/runtime/qwen-venv/bin/python" ]; then
    PY="$REPO/runtime/qwen-venv/bin/python"
  elif [ -x "$HOME/Library/Application Support/MossVoice/runtime/qwen-venv/bin/python" ]; then
    PY="$HOME/Library/Application Support/MossVoice/runtime/qwen-venv/bin/python"
  else
    PY="$(command -v python3)"
  fi
fi

# --- run (foreground; launchd KeepAlive restarts on exit) ---------------------
exec "$PY" "$REPO/telephony/moss_supervisor.py" start --service runtime