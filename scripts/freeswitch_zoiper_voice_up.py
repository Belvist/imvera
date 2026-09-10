#!/usr/bin/env python3
"""Start Zoiper → FreeSWITCH → CallActor lab (MLX on host, FS in Docker)."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

from scripts.freeswitch_voice_lab_env import build_freeswitch_voice_lab_env, ensure_silero_opening_cache
from scripts.freeswitch_write_zoiper_runtime import write_zoiper_runtime_config
from scripts.freeswitch_zoiper_info import sync_freeswitch_zoiper_profile
from scripts.voice_process import ROOT, is_running, start, stop

COMPOSE = ROOT / "infra" / "freeswitch" / "docker-compose.yml"
VOICE_OVERLAY = ROOT / "infra" / "freeswitch" / "docker-compose.zoiper-voice.yml"
BRIDGE_URL = "http://127.0.0.1:9210/health/ready"


def _git_image_tag() -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
    )
    return proc.stdout.strip() if proc.returncode == 0 else "local"


def _find_preflight_marker(short_sha: str) -> Path | None:
    """Accept short-SHA marker (canonical) or legacy full-SHA marker."""
    marker_dir = ROOT / ".run" / "preflight"
    full_proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
    )
    candidates = [short_sha]
    if full_proc.returncode == 0:
        full_sha = full_proc.stdout.strip()
        if full_sha and full_sha not in candidates:
            candidates.append(full_sha)
    for name in candidates:
        path = marker_dir / f"{name}.ok"
        if path.is_file():
            return path
    return None


def _compose_cmd(*args: str) -> list[str]:
    return [
        "docker",
        "compose",
        "-f",
        str(COMPOSE),
        "-f",
        str(VOICE_OVERLAY),
        *args,
    ]


def _wait_http(url: str, name: str, timeout_s: float = 120.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            response = httpx.get(url, timeout=2.0)
            if response.status_code == 200:
                body = response.json()
                if body.get("status") == "ok" and body.get("mode") == "callactor":
                    print(f"  {name}: ready (callactor)")
                    return True
        except httpx.HTTPError:
            pass
        time.sleep(1.5)
    print(f"BLOCKED: {name} not ready at {url}", file=sys.stderr)
    return False


def _ensure_mlx_workers() -> int:
    if is_running("stt") and is_running("tts") and is_running("llm"):
        for port in (9101, 9102, 9103):
            try:
                response = httpx.get(f"http://127.0.0.1:{port}/health/ready", timeout=2.0)
                if response.status_code != 200:
                    break
            except httpx.HTTPError:
                break
        else:
            print("MLX workers already running")
            return 0
    print("Starting MLX workers (make voice-up or models_up)...")
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "models_up.py")],
        cwd=ROOT,
        check=False,
    ).returncode


def main() -> int:
    sync_freeswitch_zoiper_profile()

    if _ensure_mlx_workers() != 0:
        print("BLOCKED: MLX workers failed to start", file=sys.stderr)
        return 1

    lab_env = build_freeswitch_voice_lab_env()
    if not ensure_silero_opening_cache(lab_env):
        return 1

    media_host = sync_freeswitch_zoiper_profile()["sip_host"]
    write_zoiper_runtime_config(media_host)
    print(f"  FreeSWITCH RTP/SIP external IP: {media_host}")

    elder = lab_env.get("IMVERA_ELDER_DISPLAY_NAME", "Даниил")
    print(f"CallActor lab: elder={elder}, opening=IMVERA wellness → dialogue by state")
    from scripts.freeswitch_voice_lab_env import print_dialogue_engine_lab_truth

    print_dialogue_engine_lab_truth()

    print("Starting FreeSWITCH (voice overlay, bridge on host)...")
    subprocess.run(_compose_cmd("stop", "media-bridge"), cwd=ROOT, check=False)
    compose_env = os.environ.copy()
    compose_env["IMVERA_FS_IMAGE_TAG"] = _git_image_tag()
    up = subprocess.run(
        _compose_cmd("up", "-d", "--build", "--no-deps", "freeswitch"),
        cwd=ROOT,
        check=False,
        env=compose_env,
    )
    if up.returncode != 0:
        return up.returncode

    readiness = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "freeswitch_readiness_check.py"), "--wait", "120"],
        cwd=ROOT,
        check=False,
    )
    if readiness.returncode != 0:
        print(
            "BLOCKED: FreeSWITCH not ready — calls would get silence. "
            "Rebuild imvera-freeswitch image (not vanilla safarov).",
            file=sys.stderr,
        )
        return readiness.returncode

    subprocess.run(_compose_cmd("stop", "media-bridge"), cwd=ROOT, check=False)

    stop("freeswitch_media_bridge")
    start(
        "freeswitch_media_bridge",
        [sys.executable, str(ROOT / "services" / "imvera_media_bridge" / "main.py")],
        env=lab_env,
    )

    if not _wait_http(BRIDGE_URL, "media-bridge"):
        return 1

    expected_sha = _git_image_tag()
    preflight_marker = _find_preflight_marker(expected_sha)
    if preflight_marker is None:
        print(
            f"BLOCKED: no preflight marker for {expected_sha}. "
            "Run: make preflight-gates",
            file=sys.stderr,
        )
        return 1
    try:
        bridge_health = httpx.get(BRIDGE_URL, timeout=3.0).json()
        runtime_sha = str((bridge_health.get("dialogue") or {}).get("dialogue.engine.version", ""))
        if runtime_sha != expected_sha:
            print(
                f"BLOCKED: runtime SHA mismatch — git={expected_sha} bridge={runtime_sha}. "
                "Restart bridge after pull.",
                file=sys.stderr,
            )
            return 1
        print(f"  runtime SHA verified: {runtime_sha}")
    except httpx.HTTPError as exc:
        print(f"BLOCKED: cannot verify bridge runtime SHA: {exc}", file=sys.stderr)
        return 1

    data = sync_freeswitch_zoiper_profile()
    print("\n=== Zoiper → Vera (FreeSWITCH CallActor) ===\n")
    print(f"  Zoiper: Registered → dial {data['dial_number']}")
    print(f"  SIP:    {data['sip_host']}:{data['sip_port']}")
    print(f"  Elder:  {elder}")
    print(f'  Opening: «Здравствуйте. Это сервис Амвера. {elder}, Как вы себя чувствуете?»')
    print("  Then: issue-first scheduler (wellness → issues → important_to_share → close)")
    print("\n  Logs:   .run/freeswitch_media_bridge.log")
    print("  Forensic after call: make freeswitch-forensic-collect UUID=<fs_uuid> CALL_ID=fs-xxxxxxxx")
    print("  Stop:   make freeswitch-zoiper-voice-down")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
