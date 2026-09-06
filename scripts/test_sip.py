#!/usr/bin/env python3
"""SIP lab gate — requires voice-up and ARI registration."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    code = subprocess.call([sys.executable, str(ROOT / "scripts" / "voice_doctor.py")])
    if code != 0:
        print(
            "BLOCKED: run make voice-up first (STT/TTS/LLM/gateway/asterisk_app/Asterisk)",
            file=sys.stderr,
        )
        return code
    print("test-sip: lab SIP path prerequisites OK — dial 7000 from Zoiper")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
