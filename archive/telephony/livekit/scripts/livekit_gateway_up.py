#!/usr/bin/env python3
"""Start voice gateway for LiveKit SIP lab (webhook :9200 → IMVERA rtc participant)."""

from __future__ import annotations

import os
import sys
import time

import httpx

from scripts.voice_process import ROOT, is_running, start

GATEWAY_URL = os.environ.get("IMVERA_VOICE_GATEWAY_HTTP", "http://127.0.0.1:9200")


def _gateway_ready() -> bool:
    try:
        r = httpx.get(f"{GATEWAY_URL}/health/ready", timeout=2.0)
        return r.status_code == 200
    except httpx.HTTPError:
        return False


def _build_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("LIVEKIT_URL", "ws://127.0.0.1:7880")
    env.setdefault("LIVEKIT_API_KEY", "devkey")
    env.setdefault("LIVEKIT_API_SECRET", "secret")
    env.setdefault("IMVERA_STT_URL", "http://127.0.0.1:9101")
    env.setdefault("IMVERA_TTS_URL", "http://127.0.0.1:9102")
    env.setdefault("IMVERA_LLM_URL", "http://127.0.0.1:9103")
    env.setdefault("IMVERA_VOICE_GATEWAY_HTTP", "http://127.0.0.1:9200")
    env.pop("IMVERA_LIVEKIT_MEDIA_GATE", None)
    return env


def ensure_livekit_gateway(*, restart: bool = False, wait_s: float = 30.0) -> int:
    if not restart and is_running("voice_gateway") and _gateway_ready():
        print(f"livekit-gateway: already up ({GATEWAY_URL})")
        return 0

    env = _build_env()
    print(f"livekit-gateway: starting voice_gateway → {GATEWAY_URL}")
    start(
        "voice_gateway",
        [sys.executable, str(ROOT / "services" / "voice_gateway" / "main.py")],
        env=env,
    )
    deadline = time.time() + wait_s
    while time.time() < deadline:
        if _gateway_ready():
            print("livekit-gateway: ready")
            return 0
        time.sleep(0.5)
    print(f"BLOCKED: voice gateway not ready at {GATEWAY_URL}/health/ready", file=sys.stderr)
    return 1


def main() -> int:
    restart = "--restart" in sys.argv
    return ensure_livekit_gateway(restart=restart)


if __name__ == "__main__":
    raise SystemExit(main())
