#!/usr/bin/env python3
"""Start STT/TTS/LLM MLX workers and wait for readiness."""

from __future__ import annotations

import os
import sys
import time

import httpx
import yaml

from scripts.voice_process import ROOT, is_running, start, stop

CFG = ROOT / "config" / "voice-m5.yaml"
WORKERS = ("stt", "tts", "llm")


def _load_ports() -> dict[str, int]:
    with CFG.open() as f:
        cfg = yaml.safe_load(f)
    return cfg["ports"]


def _wait_ready(url: str, name: str, timeout_s: float = 600.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            r = httpx.get(f"{url}/health/ready", timeout=2.0)
            if r.status_code == 200:
                print(f"  {name}: ready")
                return True
        except httpx.HTTPError:
            pass
        time.sleep(2.0)
    print(f"BLOCKED: {name} not ready at {url}", file=sys.stderr)
    return False


def _worker_ready(port: int) -> bool:
    try:
        r = httpx.get(f"http://127.0.0.1:{port}/health/ready", timeout=2.0)
        return r.status_code == 200
    except httpx.HTTPError:
        return False


def _all_ready(ports: dict[str, int]) -> bool:
    return all(is_running(name) and _worker_ready(ports[name]) for name in WORKERS)


def main() -> int:
    ports = _load_ports()
    if _all_ready(ports):
        print("MLX workers already running and ready.")
        return 0

    env = os.environ.copy()
    for name in WORKERS:
        stop(name)

    for name in WORKERS:
        port = ports[name]
        print(f"Starting {name} on {port}...")
        start(
            name,
            [sys.executable, str(ROOT / "services" / name / "worker.py")],
            env={**env, f"IMVERA_{name.upper()}_PORT": str(port)},
        )

    ok = True
    for name in WORKERS:
        if not _wait_ready(f"http://127.0.0.1:{ports[name]}", name):
            ok = False
    if not ok:
        return 1
    print("All inference workers ready.")
    print(f"IMVERA_STT_URL=http://127.0.0.1:{ports['stt']}")
    print(f"IMVERA_TTS_URL=http://127.0.0.1:{ports['tts']}")
    print(f"IMVERA_LLM_URL=http://127.0.0.1:{ports['llm']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
