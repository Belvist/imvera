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


def _tts_matches_lab_fast(port: int) -> bool:
    from services.tts.lab_fast import lab_fast_tts_enabled

    if not lab_fast_tts_enabled():
        return True
    try:
        r = httpx.get(f"http://127.0.0.1:{port}/health/ready", timeout=2.0)
        if r.status_code != 200:
            return False
        return str(r.json().get("model_revision", "")).startswith("silero_lab:")
    except httpx.HTTPError:
        return False


def _all_ready(ports: dict[str, int]) -> bool:
    if not all(is_running(name) and _worker_ready(ports[name]) for name in WORKERS):
        return False
    return _tts_matches_lab_fast(ports["tts"])


def _ensure_worker(name: str, port: int, env: dict[str, str]) -> bool:
    if is_running(name) and _worker_ready(port):
        print(f"  {name}: already ready — keeping warm")
        return True
    if is_running(name) and not _worker_ready(port):
        print(f"  {name}: running but not ready — restarting")
    stop(name)
    print(f"Starting {name} on {port}...")
    worker_env = {**env, f"IMVERA_{name.upper()}_PORT": str(port)}
    start(
        name,
        [sys.executable, str(ROOT / "services" / name / "worker.py")],
        env=worker_env,
    )
    tts_timeout = 120.0 if name == "tts" else 600.0
    if _wait_ready(f"http://127.0.0.1:{port}", name, timeout_s=tts_timeout):
        return True
    if name != "tts" or worker_env.get("IMVERA_TTS_ENGINE") == "silero_lab":
        return False
    print("  tts: MLX not ready — restarting with silero_lab (lab fast path)", file=sys.stderr)
    stop(name)
    fallback_env = {
        **worker_env,
        "IMVERA_TTS_ENGINE": "silero_lab",
        "IMVERA_SILERO_LAB_ACK": "1",
        "IMVERA_LAB_FAST_TTS": "1",
    }
    start(
        name,
        [sys.executable, str(ROOT / "services" / name / "worker.py")],
        env=fallback_env,
    )
    return _wait_ready(f"http://127.0.0.1:{port}", name, timeout_s=90.0)


def main() -> int:
    from services.tts.lab_fast import apply_lab_fast_env

    ports = _load_ports()
    if _all_ready(ports):
        print("MLX workers already running and ready.")
        return 0

    env = apply_lab_fast_env(os.environ.copy())

    ok = True
    for name in WORKERS:
        if not _ensure_worker(name, ports[name], env):
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
