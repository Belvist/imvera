#!/usr/bin/env python3
"""One-command launcher for M5 MLX voice + Zoiper SIP lab."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUN = ROOT / ".run"


def _run(cmd: list[str], check: bool = True) -> int:
    print("+", " ".join(cmd))
    return subprocess.call(cmd, cwd=ROOT, check=check)


def main() -> int:
    profile = os.environ.get("IMVERA_VOICE_PROFILE", "m5-mlx")
    if profile != "m5-mlx":
        print(f"BLOCKED: unsupported profile {profile}", file=sys.stderr)
        return 1
    _run([sys.executable, "scripts/zoiper_info.py"], check=False)
    code = _run([sys.executable, "scripts/models_up.py"])
    if code != 0:
        return code
    RUN.mkdir(exist_ok=True)
    env = os.environ.copy()
    env.setdefault("IMVERA_STT_URL", "http://127.0.0.1:9101")
    env.setdefault("IMVERA_TTS_URL", "http://127.0.0.1:9102")
    env.setdefault("IMVERA_LLM_URL", "http://127.0.0.1:9103")
    env.setdefault(
        "IMVERA_PG_URL",
        "postgresql://imvera:imvera_dev_change_me@127.0.0.1:5432/imvera",
    )
    gw_log = RUN / "voice_gateway.log"
    print("Starting voice gateway on :9200...")
    gw = subprocess.Popen(
        [sys.executable, "-m", "services.voice_gateway.main"],
        cwd=ROOT,
        env=env,
        stdout=gw_log.open("w"),
        stderr=subprocess.STDOUT,
    )
    (RUN / "voice_gateway.pid").write_text(str(gw.pid))
    print("Voice stack up. Configure Zoiper with scripts/zoiper_info.py output.")
    print("Browser client: http://127.0.0.1:9200 is gateway only; use API /voice for browser.")
    print("Start Asterisk separately: docker compose -f docker/docker-compose.voice.yml up -d")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
