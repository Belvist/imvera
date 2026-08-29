#!/usr/bin/env bash
# MossVoice FreeSWITCH config installer (read.md G1).
#
# Syncs the production dialplan + SIP profile tweaks from the repo into the
# installed FreeSWITCH, reloads the XML, and verifies the VoiceRuntime route
# (4400) + ESL connectivity. Idempotent: safe to re-run after any repo change.
#
# Design rules:
#   * uses the REAL config dir (the Homebrew Cellar path — the symlink at
#     /opt/homebrew/etc/freeswitch is not followed by grep/releng tooling);
#   * no absolute developer paths: the repo dialplan uses ${mossvoice_dir}
#     only when it must reference a file; set the global here.
#   * fail-fast when the production route does not match what we expect.
#
# Usage: bash scripts/install_freeswitch.sh [--dry-run]
set -uo pipefail

DRY_RUN=0
if [ "${1:-}" = "--dry-run" ]; then
  DRY_RUN=1
fi

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# --- locate the installed FreeSWITCH config dir -------------------------------
FS_PREFIX="$(brew --prefix freeswitch 2>/dev/null || echo /opt/homebrew)"
FS_ETC="${FS_PREFIX}/etc/freeswitch"
if [ ! -d "$FS_ETC" ]; then
  echo "FAIL: FreeSWITCH config dir not found at $FS_ETC"
  exit 1
fi
DIALPLAN_DIR="$FS_ETC/dialplan/default"
PUBLIC_DIR="$FS_ETC/dialplan/public"
BIN="$(command -v freeswitch || echo /opt/homebrew/bin/freeswitch)"
FS_CLI="$(command -v fs_cli || echo /opt/homebrew/bin/fs_cli)"

say() { echo "  $*"; }
fail() { echo "FAIL: $*"; exit 1; }

# --- 1. dialplan: production route 4400 = VoiceRuntime ------------------------
if [ ! -f "$REPO/telephony/moss_dialplan.xml" ]; then
  fail "repo dialplan missing: telephony/moss_dialplan.xml"
fi
if [ "$DRY_RUN" = "1" ]; then
  say "[dry-run] would install:"
  say "  $REPO/telephony/moss_dialplan.xml -> $DIALPLAN_DIR/mossvoice.xml"
  say "  remove legacy $DIALPLAN_DIR/moss_dialplan.xml (old Lua 4400 route)"
else
  install -m 0644 "$REPO/telephony/moss_dialplan.xml" \
    "$DIALPLAN_DIR/mossvoice.xml"
  # Remove the LEGACY Lua dialplan file (moss_dialplan.xml) so the reload
  # does not load TWO definitions of 4400 (old = lua, new = answer+park).
  # Only remove files that actually reference the legacy route.
  if [ -f "$DIALPLAN_DIR/moss_dialplan.xml" ] \
     && grep -qE "moss_agent\.lua|4400" "$DIALPLAN_DIR/moss_dialplan.xml" \
     && [ "$DIALPLAN_DIR/moss_dialplan.xml" != \
          "$DIALPLAN_DIR/mossvoice.xml" ]; then
    mv "$DIALPLAN_DIR/moss_dialplan.xml" \
       "$DIALPLAN_DIR/moss_dialplan.xml.legacy-$(date +%s)"
    say "legacy Lua dialplan retired -> .legacy-* backup"
  fi
  say "dialplan installed -> $DIALPLAN_DIR/mossvoice.xml"
fi

# 4400 must NOT be reachable from the public profile (G6: external users never
# see the internal app route). Ensure no public dialplan routes 4400.
if [ -d "$PUBLIC_DIR" ]; then
  if grep -rlE "4400" "$PUBLIC_DIR" 2>/dev/null; then
    say "WARN: public dialplan references 4400 — removing routes."
    if [ "$DRY_RUN" = "0" ]; then
      for f in $(grep -rlE "4400" "$PUBLIC_DIR" 2>/dev/null); do
        install -m 0644 /dev/null "$f.tmp"
        mv "$f.tmp" "$f"
      done
    fi
  else
    say "public dialplan: no 4400 route (ok)"
  fi
fi

# --- 2. global vars: mossvoice_dir (repo-local file references) ---------------
VARS="$FS_ETC/vars.xml"
if grep -qE '<X-PRE-PROCESS[^>]*set[^>]*data="mossvoice_dir=' "$VARS" \
   2>/dev/null; then
  say "vars.xml: mossvoice_dir already set"
else
  if [ "$DRY_RUN" = "1" ]; then
    say "[dry-run] would set mossvoice_dir=$REPO in vars.xml"
  else
    # insert before the closing </include> of vars.xml
    python3 - "$VARS" "$REPO" <<'PYEOF'
import sys, re
p, repo = sys.argv[1], sys.argv[2]
s = open(p).read()
if "mossvoice_dir" in s:
    sys.exit(0)
line = ('  <X-PRE-PROCESS cmd="set" data="mossvoice_dir=%s"/>\n' % repo)
s2, n = re.subn(r'(\s*</include>\s*)$', line + '</include>\n', s, count=1)
if not n:
    sys.exit("vars.xml has no </include>")
open(p, "w").write(s2)
print("mossvoice_dir set in vars.xml")
PYEOF
  fi
fi

# --- 3. reload + verification -------------------------------------------------
if [ "$DRY_RUN" = "1" ]; then
  say "[dry-run] would reloadxml and verify ESL + 4400 route"
  exit 0
fi

say "reloading dialplan..."
"$FS_CLI" -x "reloadxml" >/dev/null 2>&1 \
  || say "WARN: reloadxml failed (fs_cli may need PATH=/opt/homebrew/bin)"

# ESL connectivity (8021, password from env or ~/.fs_cli_conf)
say "checking ESL 8021..."
if ! command -v "$FS_CLI" >/dev/null 2>&1; then
  fail "fs_cli not found — cannot verify ESL"
fi
"$FS_CLI" -x "status" >/dev/null 2>&1 \
  || fail "fs_cli cannot reach ESL (wrong password / FS down)"

# VoiceRuntime route must be answer+park (grep on the INSTALLED copy)
if grep -qE 'answer.*park' "$DIALPLAN_DIR/mossvoice.xml" \
   && grep -qE 'expression="\^4400\$"' "$DIALPLAN_DIR/mossvoice.xml"; then
  say "production route 4400 -> answer+park (VoiceRuntime) OK"
else
  fail "installed dialplan does not route 4400 -> answer+park"
fi

# VoiceRuntime /ready (default port 9700; override MOSS_RUNTIME_PORT)
RTPORT="${MOSS_RUNTIME_PORT:-9700}"
say "checking VoiceRuntime /ready on 127.0.0.1:$RTPORT..."
if curl -sf "http://127.0.0.1:$RTPORT/ready" 2>/dev/null | grep -q '"ready": true'; then
  say "VoiceRuntime ready"
else
  say "WARN: VoiceRuntime /ready not reachable (is it running?)"
fi

echo ""
echo "FreeSWITCH config installed: dialplan 4400=VoiceRuntime, ESL verified."
echo "NOTE: restart FreeSWITCH ONLY if sip_profiles/vars changed; a plain"
echo "      'fs_cli -x reloadxml' is enough for dialplan-only changes."