"""Lab half-duplex listen gate — mute fallback for Zoiper/softphone.

Pattern when enabled: Vera speaks → fully finishes → short pause → THEN enable mic.

Default lab path is always-listen + echo reference gate (echo_ref_gate.py).
Half-duplex mute is opt-in via IMVERA_LAB_HALF_DUPLEX=1 (friend MVP / mute fallback).
"""

from __future__ import annotations

import os

_DEFAULT_PAUSE_MS = 400
_MIN_PAUSE_MS = 0
_MAX_PAUSE_MS = 2000


def lab_half_duplex_enabled() -> bool:
    """IMVERA_LAB_HALF_DUPLEX default off — prefer always-listen + echo-ref gate."""
    return os.environ.get("IMVERA_LAB_HALF_DUPLEX", "0").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def post_speech_pause_ms() -> int:
    """Mandatory quiet after playback drain before VAD/listen (ms)."""
    raw = os.environ.get("IMVERA_POST_SPEECH_PAUSE_MS", str(_DEFAULT_PAUSE_MS)).strip()
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_PAUSE_MS
    return max(_MIN_PAUSE_MS, min(_MAX_PAUSE_MS, value))


def apply_lab_half_duplex_env(env: dict[str, str]) -> dict[str, str]:
    """Apply lab listen-mode defaults without overriding an explicit half-duplex choice.

    Defaults: HALF_DUPLEX=0 (always-listen), ECHO_REF_GATE=1, BARGE_IN=0.
    Explicit IMVERA_LAB_HALF_DUPLEX=1 remains the mute fallback; unmute fail-safes
    in CallActor stay active when that mode is selected.
    """
    env.setdefault("IMVERA_LAB_HALF_DUPLEX", "0")
    env.setdefault("IMVERA_POST_SPEECH_PAUSE_MS", str(_DEFAULT_PAUSE_MS))
    env.setdefault("IMVERA_ECHO_REF_GATE", "1")
    env.setdefault("IMVERA_LAB_BARGE_IN", "0")
    return env
