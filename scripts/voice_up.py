#!/usr/bin/env python3
"""One-command launcher for M5 MLX voice + Zoiper SIP lab."""

from __future__ import annotations

import os
import subprocess
import sys
import time

import httpx

from scripts.local_sip_config import load_or_create
from scripts.voice_process import ROOT, start

VOICE_COMPOSE = ["docker", "compose", "-f", "docker/docker-compose.voice.yml"]


def _wait_http(url: str, name: str, timeout_s: float = 600.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            r = httpx.get(url, timeout=2.0)
            if r.status_code == 200:
                print(f"  {name}: ready")
                return True
        except httpx.HTTPError:
            pass
        time.sleep(2.0)
    print(f"BLOCKED: {name} not ready at {url}", file=sys.stderr)
    return False


def _wait_ari_registered(cfg: dict) -> bool:
    url = os.environ.get("IMVERA_ASTERISK_ARI_URL", "http://127.0.0.1:8088/ari")
    auth = (cfg["ari_user"], cfg["ari_password"])
    deadline = time.time() + 120.0
    app = cfg["stasis_app"]
    while time.time() < deadline:
        try:
            r = httpx.get(f"{url}/applications", auth=auth, timeout=3.0)
            if r.status_code == 200 and app in r.json():
                print(f"  ARI app '{app}' registered")
                return True
        except httpx.HTTPError:
            pass
        time.sleep(2.0)
    print(f"BLOCKED: ARI application '{app}' not registered", file=sys.stderr)
    return False


def main() -> int:
    profile = os.environ.get("IMVERA_VOICE_PROFILE", "m5-mlx")
    if profile != "m5-mlx":
        print(f"BLOCKED: unsupported profile {profile}", file=sys.stderr)
        return 1

    cfg = load_or_create()
    print("SIP credentials synced to config/local/asterisk/")

    code = subprocess.run(
        [sys.executable, "scripts/models_up.py"],
        cwd=ROOT,
        check=False,
    ).returncode
    if code != 0:
        return code

    env = os.environ.copy()
    env.setdefault("IMVERA_STT_URL", "http://127.0.0.1:9101")
    env.setdefault("IMVERA_TTS_URL", "http://127.0.0.1:9102")
    env.setdefault("IMVERA_LLM_URL", "http://127.0.0.1:9103")
    env.setdefault(
        "IMVERA_PG_URL",
        "postgresql://imvera:imvera_dev_change_me@127.0.0.1:5432/imvera",
    )
    env["IMVERA_ASTERISK_ARI_URL"] = os.environ.get(
        "IMVERA_ASTERISK_ARI_URL", "http://127.0.0.1:8088/ari"
    )
    env["IMVERA_ASTERISK_ARI_USER"] = cfg["ari_user"]
    env["IMVERA_ASTERISK_ARI_PASSWORD"] = cfg["ari_password"]
    env["IMVERA_STASIS_APP"] = cfg["stasis_app"]
    env.setdefault("IMVERA_VOICE_GATEWAY_HTTP", "http://127.0.0.1:9200")
    env.setdefault("IMVERA_ASTERISK_APP_HTTP", "http://127.0.0.1:9201")
    env.setdefault("IMVERA_DEV_FAMILY_ID", "fam-voice")
    env.setdefault("IMVERA_DEV_FAMILY_ID", "fam-voice")
    env.setdefault("IMVERA_ELDER_DISPLAY_NAME", "Даниил")

    print("Starting voice gateway on :9200...")
    start(
        "voice_gateway",
        [sys.executable, str(ROOT / "services" / "voice_gateway" / "main.py")],
        env=env,
    )
    if not _wait_http("http://127.0.0.1:9200/health/ready", "gateway", 30):
        return 1

    print("Starting Asterisk Stasis app on :9201...")
    start(
        "asterisk_app",
        [sys.executable, str(ROOT / "services" / "asterisk_app" / "main.py")],
        env=env,
    )
    if not _wait_http("http://127.0.0.1:9201/health/live", "asterisk_app", 30):
        return 1

    print("Starting Asterisk container...")
    subprocess.run([*VOICE_COMPOSE, "up", "-d", "--build"], cwd=ROOT, check=False)
    if not _wait_ari_registered(cfg):
        return 1

    print("\nVoice stack up.")
    print(f"  Zoiper: {cfg['username']}@{cfg['sip_server']}:{cfg['port']}")
    print(f"  Password: {cfg['password']}")
    print(f"  Dial: {cfg['vera_extension']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
