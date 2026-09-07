"""Lab half-duplex listen gate — friend MVP for Zoiper/softphone stability.

Pattern: Vera speaks → fully finishes → short pause → THEN enable mic.

Tonight default is half-duplex ON. Always-listen + echo-ref gate remains available
via IMVERA_LAB_HALF_DUPLEX=0 and IMVERA_ECHO_REF_GATE=1, but live Zoiper evidence
(sip-dad36ca2bf) showed echo speech.started during greeting and no user STT after.
"""

from __future__ import annotations

import os

_DEFAULT_PAUSE_MS = 400
_MIN_PAUSE_MS = 0
_MAX_PAUSE_MS = 2000


def lab_half_duplex_enabled() -> bool:
    """IMVERA_LAB_HALF_DUPLEX default ON — mute while Vera speaks (friend MVP)."""
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
    """Apply lab listen-mode defaults without overriding explicit operator choices.

    Defaults for Zoiper lab tonight: HALF_DUPLEX=1, ECHO_REF_GATE=0, BARGE_IN=0.
    Explicit HALF_DUPLEX=0 keeps always-listen; unmute fail-safes stay in CallActor.
    """
    env.setdefault("IMVERA_LAB_HALF_DUPLEX", "1")
    env.setdefault("IMVERA_POST_SPEECH_PAUSE_MS", str(_DEFAULT_PAUSE_MS))
    env.setdefault("IMVERA_ECHO_REF_GATE", "0")
    env.setdefault("IMVERA_LAB_BARGE_IN", "0")
    return env
