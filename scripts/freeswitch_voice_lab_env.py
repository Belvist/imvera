"""Shared CallActor environment for FreeSWITCH Zoiper lab (= voice_up parity)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import httpx

from packages.voice_runtime.audio_audit import apply_audio_audit_env
from packages.voice_runtime.lab_half_duplex import apply_lab_half_duplex_env
from packages.voice_runtime.profile import apply_audio_env
from services.tts.lab_fast import apply_lab_fast_env

ROOT = Path(__file__).resolve().parent.parent


def build_freeswitch_voice_lab_env() -> dict[str, str]:
    """Same audio/listen/TTS lab flags as `make voice-up` CallActor path."""
    env = apply_audio_audit_env(
        apply_lab_half_duplex_env(apply_lab_fast_env(apply_audio_env(os.environ.copy())))
    )
    env.setdefault("IMVERA_STT_URL", "http://127.0.0.1:9101")
    env.setdefault("IMVERA_TTS_URL", "http://127.0.0.1:9102")
    env.setdefault("IMVERA_LLM_URL", "http://127.0.0.1:9103")
    env.setdefault(
        "IMVERA_PG_URL",
        "postgresql://imvera:imvera_dev_change_me@127.0.0.1:5432/imvera",
    )
    env.setdefault("IMVERA_DEV_FAMILY_ID", "fam-voice")
    env.setdefault("IMVERA_ELDER_DISPLAY_NAME", "Даниил")
    env.setdefault("IMVERA_MEDIA_BRIDGE_MODE", "callactor")
    env.setdefault("IMVERA_MEDIA_BRIDGE_PORT", "9210")
    env.setdefault(
        "IMVERA_MEDIA_BRIDGE_WS",
        "ws://host.docker.internal:9210/stream",
    )
    env.setdefault("IMVERA_TELEPHONY_STREAM", "1")
    env.setdefault("IMVERA_FS_ORIGINATE_TIMEOUT_S", "25")
    # Live TTS opening on phone — cached 24k→16k via JSON playback can clip «IMVERA».
    env.setdefault("IMVERA_OPENING_CACHE", "0")
    # Product opening: «Здравствуйте. Это сервис Амвера. <name>, Как вы себя чувствуете?»
    # Cyrillic brand — Latin «IMVERA» is skipped/garbled by Silero RU TTS.
    env.setdefault("IMVERA_VOICE_DIRECT_WELLNESS_OPENING", "1")
    # Single-writer DialogueEngine for daily-check pilot (must match session.py gate).
    env.setdefault("IMVERA_DIALOGUE_ENGINE", "1")
    # Product live loop is deterministic — do not enable Qwen interpret.
    env.setdefault("IMVERA_LLM_INTERPRET", "0")
    env.setdefault("IMVERA_MISSION_LLM_INTERPRET", "0")
    # Pilot 2026-09-13 (user directive): adaptive 5-domain coverage ladder +
    # reluctance early close (IMVERA_COVERAGE_LADDER=1) and tiny advisory
    # classifier route_clf (231KB sklearn, <1ms; deterministic RED/decline
    # checks always first; +1 bounded vote, never closes alone).
    env.setdefault("IMVERA_COVERAGE_LADDER", "1")
    env.setdefault("IMVERA_TINYLLM_MODEL", "route_clf")
    env.setdefault("IMVERA_NEGOTIATED_CODEC", "G722")
    env.setdefault("PYTHONPATH", str(ROOT))
    return env


def print_dialogue_engine_lab_truth() -> None:
    """Stdout banner when bringing up Zoiper lab — grep-friendly runtime truth."""
    from packages.dialogue_engine.runtime import runtime_truth

    truth = runtime_truth()
    print(
        f"  dialogue.engine.enabled={truth['dialogue.engine.enabled']} "
        f"dialogue.engine.mode={truth['dialogue.engine.mode']} "
        f"dialogue.engine.version={truth['dialogue.engine.version']}"
    )
    print(
        f"  IMVERA_DIALOGUE_ENGINE={truth['IMVERA_DIALOGUE_ENGINE']} "
        f"IMVERA_VOICE_DIRECT_WELLNESS_OPENING={truth['IMVERA_VOICE_DIRECT_WELLNESS_OPENING']}"
    )


def ensure_silero_opening_cache(env: dict[str, str]) -> bool:
    """Require Silero Xenia TTS and pre-render opening wellness (warm first phrase)."""
    tts_url = env.get("IMVERA_TTS_URL", "http://127.0.0.1:9102").rstrip("/")
    try:
        response = httpx.get(f"{tts_url}/health/ready", timeout=3.0)
        if response.status_code != 200:
            print(f"BLOCKED: TTS not ready ({response.status_code})", file=__import__("sys").stderr)
            return False
        tts_rev = str(response.json().get("model_revision", ""))
    except httpx.HTTPError as exc:
        print(f"BLOCKED: TTS unreachable: {exc}", file=__import__("sys").stderr)
        return False
    if "macos_say" in tts_rev or not tts_rev.startswith("silero_lab:silero:"):
        print(f"BLOCKED: TTS must be silero_lab (Silero), got {tts_rev!r}", file=__import__("sys").stderr)
        return False
    env["IMVERA_TTS_MODEL_REVISION"] = tts_rev
    print(f"  TTS revision: {tts_rev}")

    cache_dir = ROOT / ".run" / "cache"
    if cache_dir.is_dir():
        for stale in cache_dir.glob("opening_*.json"):
            stale.unlink()
            print(f"  dropped stale opening cache {stale.name}")

    print("Pre-rendering opening phrase cache...")
    result = subprocess.run(
        [os.environ.get("PYTHON", "python3"), str(ROOT / "scripts" / "prerender_opening.py")],
        cwd=ROOT,
        env=env,
        check=False,
    )
    if result.returncode != 0:
        print("WARN: opening prerender failed — first call may wait on TTS", file=__import__("sys").stderr)
    return True
