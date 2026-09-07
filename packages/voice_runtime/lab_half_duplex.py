"""Lab half-duplex listen gate — friend MVP pattern for Zoiper/softphone stability.

Pattern: Vera speaks → fully finishes → short pause → THEN enable mic.

Acoustic echo on softphones (Zoiper) feeds TTS into capture; continuous listen
caused self-barge-in (sip-31365dee13). Strict half-duplex is the lab default.

Optional always-listen + reference echo gate lives in echo_ref_gate.py and is
enabled only when IMVERA_LAB_HALF_DUPLEX=0 (explicit opt-out of mute).
"""

from __future__ import annotations

import os

_DEFAULT_PAUSE_MS = 400
_MIN_PAUSE_MS = 0
_MAX_PAUSE_MS = 2000


def lab_half_duplex_enabled() -> bool:
    """IMVERA_LAB_HALF_DUPLEX default on — no barge-in from uplink during Vera speech."""
    return os.environ.get("IMVERA_LAB_HALF_DUPLEX", "1").strip().lower() in {
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
    """Force lab half-duplex ON for Zoiper stability (friend MVP).

    Do not use setdefault for HALF_DUPLEX — a stale IMVERA_LAB_HALF_DUPLEX=0 in
    the parent shell (from always-listen experiments) would otherwise stick and
    leave the stack in the wrong mode.
    """
    env["IMVERA_LAB_HALF_DUPLEX"] = "1"
    env.setdefault("IMVERA_POST_SPEECH_PAUSE_MS", str(_DEFAULT_PAUSE_MS))
    env.setdefault("IMVERA_ECHO_REF_GATE", "1")
    env.setdefault("IMVERA_LAB_BARGE_IN", "0")
    return env
