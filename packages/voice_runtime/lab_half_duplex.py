"""Lab half-duplex listen gate — friend MVP pattern for Zoiper/softphone stability.

Pattern: Vera speaks → fully finishes → short pause → THEN enable mic.

Acoustic echo on softphones (Zoiper) feeds TTS into capture; continuous listen
caused self-barge-in (sip-31365dee13). Strict half-duplex is the lab default.
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
    """Ensure lab half-duplex defaults are present for voice stack workers."""
    env.setdefault("IMVERA_LAB_HALF_DUPLEX", "1")
    env.setdefault("IMVERA_POST_SPEECH_PAUSE_MS", str(_DEFAULT_PAUSE_MS))
    return env
