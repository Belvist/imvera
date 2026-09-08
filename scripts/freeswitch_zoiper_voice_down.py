#!/usr/bin/env python3
"""Stop Zoiper CallActor lab — host bridge + optional FS stack."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from scripts.voice_process import ROOT, stop

COMPOSE = ROOT / "infra" / "freeswitch" / "docker-compose.yml"
VOICE_OVERLAY = ROOT / "infra" / "freeswitch" / "docker-compose.zoiper-voice.yml"


def main() -> int:
    stop("freeswitch_media_bridge")
    cmd = [
        "docker",
        "compose",
        "-f",
        str(COMPOSE),
        "-f",
        str(VOICE_OVERLAY),
        "down",
    ]
    print("freeswitch-zoiper-voice-down:", " ".join(cmd))
    return subprocess.run(cmd, cwd=ROOT).returncode


if __name__ == "__main__":
    raise SystemExit(main())
