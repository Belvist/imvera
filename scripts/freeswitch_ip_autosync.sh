#!/usr/bin/env bash
# MossVoice — FreeSWITCH LAN-IP auto-sync for DHCP-assigned Macs.
#
# The Mac's LAN IP changes with DHCP (this box has already drifted
# 192.168.1.236 -> .120 -> .194). FreeSWITCH pins `local_ip_v4` in vars.xml,
# so a lease change silently makes SIP unreachable ("Request Timeout" then
# "503 no transports left to try"). This script:
#   1. discovers the current private LAN IPv4 (en0 -> en1 -> default route),
#   2. if it differs from the pinned value, rewrites the X-PRE-PROCESS line,
#   3. hot-reloads xml and restarts the sofia profiles so the change applies
#      WITHOUT restarting the whole FreeSWITCH process.
#
# Runs from a launchd agent (com.mossvoice.freeswitch-ip-sync) every ~90s and
# on network mount. Safe to run manually: exits 0 immediately when nothing
# changed.
#
# Why `local_ip_v4=auto` is NOT used: FreeSWITCH's autodetect once picked the
# phantom 240.0.0.2 (a multicast-ish alias) instead of the LAN address and
# broke SIP. This script chooses the LAN address deliberately and only ever
# writes private-range IPv4s.
set -uo pipefail

# launchd PATH is /usr/bin:/bin — Homebrew fs_cli never resolves. The whole
# point of this script is to RESTART sofia when the IP changes; without an
# explicit PATH the patch happened but the profiles never reloaded
# (2026-08-29: "fs_cli: command not found" — SIP kept listening on the old
# pinned address after a DHCP drift). Resolve fs_cli once, deliberately.
if command -v fs_cli >/dev/null 2>&1; then
  FS_CLI="$(command -v fs_cli)"
elif [ -x /opt/homebrew/bin/fs_cli ]; then
  FS_CLI=/opt/homebrew/bin/fs_cli
else
  FS_CLI=fs_cli  # let the shell resolve; the invocation will fail loudly
fi

VARS="/opt/homebrew/etc/freeswitch/vars.xml"
# Brew's vars.xml is a symlink into Cellar; BSD sed -i refuses symlinks
# ("in-place editing only works for regular files"), so resolve the real file.
REAL_VARS="$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$VARS" 2>/dev/null || echo "$VARS")"
LOG="/tmp/mossvoice_fs_ip_sync.log"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "$LOG"; }

# --- 1. discover current private LAN IPv4 ------------------------------ #
LAN_IP=""
for iface in en0 en1 en2; do
  LAN_IP="$(ipconfig getifaddr "$iface" 2>/dev/null || true)"
  [ -n "$LAN_IP" ] && break
done
if [ -z "$LAN_IP" ]; then
  iface="$(route -n get default 2>/dev/null | awk '/interface:/{print $2}')"
  [ -n "$iface" ] && LAN_IP="$(ipconfig getifaddr "$iface" 2>/dev/null || true)"
fi

# sanity: only private-range IPv4 is acceptable (rejects 240.* phantom, 127.*, etc.)
case "$LAN_IP" in
  192.168.*|10.*|172.1[6-9].*|172.2[0-9].*|172.3[0-1].*)
    ;;
  *)
    log "no usable private LAN IP found ('${LAN_IP:-<empty>}'); skip"
    exit 1
    ;;
esac

# --- 2. compare with pinned value -------------------------------------- #
PINNED="$(grep -oE 'data="local_ip_v4=[^"]*"' "$REAL_VARS" | head -1 | grep -oE '[0-9.]+$')"
if [ "$PINNED" = "$LAN_IP" ]; then
  exit 0  # nothing to do
fi

# --- 3. rewrite vars.xml line (match the <X-PRE-PROCESS> line only) ------- #
if ! sed -i '' 's#data="local_ip_v4=[^"]*"#data="local_ip_v4='"$LAN_IP"'"#' "$REAL_VARS"; then
  log "failed to patch $REAL_VARS"
  exit 1
fi
log "LAN IP changed: ${PINNED:-<unset>} -> $LAN_IP (patched $REAL_VARS)"

# --- 4. hot-apply without restarting the process ------------------------ #
if pgrep -x freeswitch >/dev/null 2>&1; then
  "$FS_CLI" -x "reloadxml"  >> "$LOG" 2>&1 || true
  "$FS_CLI" -x "sofia profile internal restart" >> "$LOG" 2>&1 || true
  "$FS_CLI" -x "sofia profile external restart" >> "$LOG" 2>&1 || true
  log "sofia profiles restarted on $LAN_IP"
fi

exit 0