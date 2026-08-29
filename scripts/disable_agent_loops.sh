#!/usr/bin/env bash
# Disable the dev loopback agents that hammer the production 4400 route.
# These were started by an earlier tooling pass and pollute every live
# measurement (empty SILENT turns, paired-leg artifacts) — see AGENTS.md
# 2026-08-29. Idempotent; keeps the plists on disk for re-enable.
set -uo pipefail
for n in devpipe1 devpipe2 devpipe3 qapipe1 qapipe2 qapipe3 soak; do
  launchctl unload "$HOME/Library/LaunchAgents/com.mossvoice.agent-loop.$n.plist" \
    >/dev/null 2>&1
done
echo "agent-loop.* disabled (plists kept). Re-enable with launchctl load each."
