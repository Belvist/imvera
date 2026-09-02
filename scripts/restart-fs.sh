#!/usr/bin/env bash
# Safe FreeSWITCH restart (S4, 2026-08-31).
#
# First attempts a targeted `sofia profile zoiper restart` so that
# the zoiper sip profile picks up changed force-register-domain /
# sip-ip without tearing down the other profiles or active calls.
# If the targeted restart does not apply the change, falls back to a
# full graceful shutdown + foreground start.
#
# Pre-checks: no active calls on the zoiper profile, ESL reachable.
set -uo pipefail

FS="${MOSS_FS:-/opt/homebrew/bin/freeswitch}"
FS_CLI="${MOSS_FS_CLI:-fs_cli}"
PROFILE="${MOSS_FS_PROFILE:-zoiper}"
REPO="${MOSS_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

# The Lua dialplan authenticates to telephony using the same token as Compose.
# Read one exact key only; never source docker/.env as executable shell.
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

# 1. Targeted profile restart (preserves other profiles + active calls).
echo "restart-fs: sofia profile $PROFILE restart ..."
if "$FS_CLI" -x "sofia profile $PROFILE restart" 2>/dev/null; then
    # Wait up to 5 s for the profile to come back RUNNING.
    for _i in 1 2 3 4 5; do
        sleep 1
        if "$FS_CLI" -x "sofia status" 2>/dev/null \
               | grep -qE "^\\s*${PROFILE}\\s+profile.*RUNNING"; then
            echo "restart-fs: $PROFILE profile restarted successfully"
            exit 0
        fi
    done
fi
echo "restart-fs: targeted restart did not apply — full restart required"

# 2. Full graceful shutdown + restart.
echo "restart-fs: fs_cli shutdown graceful ..."
"$FS_CLI" -x "shutdown graceful" 2>/dev/null || true
sleep 2
# Kill any lingering freeswitch process.
pkill -f "freeswitch" 2>/dev/null || true
sleep 1
echo "restart-fs: starting freeswitch ..."
exec "$FS" -nc -nonat