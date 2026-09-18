#!/usr/bin/env python3
"""Voice call gate — TTS must emit first PCM within budget before live Zoiper."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import httpx

from packages.voice_runtime.tts_gate import measure_tts_first_pcm_s

ROOT = Path(__file__).resolve().parent.parent
TTS_URL = os.environ.get("IMVERA_TTS_URL", "http://127.0.0.1:9102")
GATEWAY_URL = os.environ.get("IMVERA_VOICE_GATEWAY_HTTP", "http://127.0.0.1:9200")
WARM_BUDGET_S = float(os.environ.get("IMVERA_TTS_WARM_FIRST_PCM_BUDGET_S", "2.0"))
COLD_BUDGET_S = float(os.environ.get("IMVERA_TTS_FIRST_PCM_BUDGET_S", "45.0"))


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def main() -> int:
    print(f"git_sha: {_git_sha()}")
    code = subprocess.call([sys.executable, str(ROOT / "scripts" / "voice_doctor.py")])
    if code != 0:
        return code

    try:
        first_s = measure_tts_first_pcm_s(TTS_URL)
    except httpx.HTTPError as exc:
        print(f"BLOCKED: TTS synthesize failed: {exc}", file=sys.stderr)
        return 1

    print(f"  TTS first_pcm: {first_s:.2f}s (warm budget {WARM_BUDGET_S:.1f}s)")
    if first_s <= 0:
        print("BLOCKED: TTS returned no PCM", file=sys.stderr)
        return 1
    if first_s > WARM_BUDGET_S:
        print(
            f"BLOCKED: TTS first_pcm {first_s:.1f}s exceeds warm budget {WARM_BUDGET_S:.1f}s — "
            f"(cold budget {COLD_BUDGET_S:.1f}s) restart TTS or run make voice-up",
            file=sys.stderr,
        )
        return 1

    try:
        r = httpx.post(
            f"{GATEWAY_URL}/internal/calls/gate-smoke/open",
            json={"family_id": "fam-voice", "elder_name": "Даниил"},
            timeout=5.0,
        )
        if r.status_code != 200:
            print(f"BLOCKED: gateway open returned {r.status_code}", file=sys.stderr)
            return 1
        httpx.post(f"{GATEWAY_URL}/internal/calls/gate-smoke/close", timeout=5.0)
    except httpx.HTTPError as exc:
        print(f"BLOCKED: gateway smoke failed: {exc}", file=sys.stderr)
        return 1

    print("voice-call-gate: PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
