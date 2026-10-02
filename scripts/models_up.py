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
_DEFAULT_WORKERS = ("stt", "tts", "llm")


def _workers() -> tuple[str, ...]:
    """IMVERA_MODELS_WORKERS=stt,tts skips LLM for product FreeSWITCH path."""
    raw = os.environ.get("IMVERA_MODELS_WORKERS", "").strip()
    if not raw:
        return _DEFAULT_WORKERS
    names = tuple(part.strip().lower() for part in raw.split(",") if part.strip())
    allowed = set(_DEFAULT_WORKERS)
    selected = tuple(n for n in names if n in allowed)
    return selected or _DEFAULT_WORKERS


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


def _selected_tts_engine(env: dict[str, str]) -> str:
    selected = env.get("IMVERA_TTS_ENGINE", "").strip().lower()
    if not selected:
        with CFG.open() as f:
            selected = str(yaml.safe_load(f)["models"]["tts"]["engine"]).strip().lower()
    return selected


def _tts_matches_lab_fast(port: int, env: dict[str, str] | None = None) -> bool:
    """The ready worker must match the selected engine, including explicit MLX."""
    from services.tts.lab_fast import apply_lab_fast_env

    env = env if env is not None else apply_lab_fast_env(os.environ.copy())
    selected = _selected_tts_engine(env)
    try:
        r = httpx.get(f"http://127.0.0.1:{port}/health/ready", timeout=2.0)
        if r.status_code != 200:
            return False
        revision = str(r.json().get("model_revision", ""))
        if selected == "silero_lab":
            return revision.startswith("silero_lab:silero:")
        return revision.startswith(f"{selected}:")
    except (httpx.HTTPError, ValueError):
        return False


def _all_ready(ports: dict[str, int]) -> bool:
    workers = _workers()
    if not all(is_running(name) and _worker_ready(ports[name]) for name in workers):
        return False
    if "tts" in workers:
        return _tts_matches_lab_fast(ports["tts"])
    return True


def _ensure_worker(name: str, port: int, env: dict[str, str]) -> bool:
    running = is_running(name)
    if (
        running
        and _worker_ready(port)
        and (name != "tts" or _tts_matches_lab_fast(port, env))
    ):
        print(f"  {name}: already ready — keeping warm")
        return True
    if running:
        print(f"  {name}: running but not ready for selected configuration — restarting")
    stop(name)
    print(f"Starting {name} on {port}...")
    worker_env = {**env, f"IMVERA_{name.upper()}_PORT": str(port)}
    start(
        name,
        [sys.executable, str(ROOT / "services" / name / "worker.py")],
        env=worker_env,
    )
    startup_timeout = 600.0
    if name == "tts":
        startup_timeout = 120.0
        if _selected_tts_engine(worker_env) != "silero_lab":
            # worker.py loads with this configurable limit, then warms for 180s
            # before binding HTTP. This does not change live synthesis deadlines.
            load_timeout = float(worker_env.get("IMVERA_TTS_MLX_LOAD_TIMEOUT_S", "120"))
            startup_timeout = load_timeout + 180.0 + 10.0
    if _wait_ready(f"http://127.0.0.1:{port}", name, timeout_s=startup_timeout):
        if name != "tts" or _tts_matches_lab_fast(port, env):
            return True
        print("BLOCKED: TTS revision does not match selected engine", file=sys.stderr)
    return False


def main() -> int:
    from services.tts.lab_fast import apply_lab_fast_env

    ports = _load_ports()
    if _all_ready(ports):
        print("MLX workers already running and ready.")
        return 0

    env = apply_lab_fast_env(os.environ.copy())
    workers = _workers()

    ok = True
    for name in workers:
        if not _ensure_worker(name, ports[name], env):
            ok = False
    if not ok:
        return 1
    print(f"Inference workers ready: {', '.join(workers)}")
    if "stt" in workers:
        print(f"IMVERA_STT_URL=http://127.0.0.1:{ports['stt']}")
    if "tts" in workers:
        print(f"IMVERA_TTS_URL=http://127.0.0.1:{ports['tts']}")
    if "llm" in workers:
        print(f"IMVERA_LLM_URL=http://127.0.0.1:{ports['llm']}")
    else:
        print("IMVERA_LLM_URL=(not started — not required for product CallActor)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
