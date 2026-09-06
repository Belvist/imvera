#!/usr/bin/env python3
"""Stop voice stack processes and Asterisk container."""

from __future__ import annotations

import subprocess

from scripts.voice_process import ROOT, stop

VOICE_COMPOSE = ["docker", "compose", "-f", "docker/docker-compose.voice.yml"]


def main() -> int:
    for name in ("stt", "tts", "llm", "voice_gateway", "asterisk_app"):
        stop(name)
    subprocess.run([*VOICE_COMPOSE, "down"], cwd=ROOT, check=False)
    print("Voice stack stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
