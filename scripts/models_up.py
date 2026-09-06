#!/usr/bin/env python3
"""Start STT/TTS/LLM MLX workers and wait for readiness."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
import yaml

ROOT = Path(__file__).resolve().parent.parent
PID_DIR = ROOT / ".run"
CFG = ROOT / "config" / "voice-m5.yaml"


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


def main() -> int:
    ports = _load_ports()
    PID_DIR.mkdir(exist_ok=True)
    env = os.environ.copy()
    procs: list[tuple[str, subprocess.Popen]] = []
    specs = [
        ("stt", ports["stt"]),
        ("tts", ports["tts"]),
        ("llm", ports["llm"]),
    ]
    for name, port in specs:
        log = PID_DIR / f"{name}.log"
        print(f"Starting {name} on {port}...")
        p = subprocess.Popen(
            [sys.executable, str(ROOT / "services" / name / "worker.py")],
            cwd=ROOT,
            env={**env, f"IMVERA_{name.upper()}_PORT": str(port)},
            stdout=log.open("w"),
            stderr=subprocess.STDOUT,
        )
        (PID_DIR / f"{name}.pid").write_text(str(p.pid))
        procs.append((name, p))

    ok = True
    for name, port in specs:
        if not _wait_ready(f"http://127.0.0.1:{port}", name):
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
