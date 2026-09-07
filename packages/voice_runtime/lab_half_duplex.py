"""Lab half-duplex listen gate — friend MVP for Zoiper/softphone stability.

TurnManager owns opening buffer-only (no VAD/STT during greeting TTS).
Lab default: always-listen (HALF_DUPLEX=0) + echo-ref gate ON.
Set IMVERA_LAB_HALF_DUPLEX=1 to restore mute-while-Vera (friend MVP).
"""

from __future__ import annotations

import os

_DEFAULT_PAUSE_MS = 100
_MIN_PAUSE_MS = 0
_MAX_PAUSE_MS = 2000
_DEFAULT_PREROLL_MS = 2000
_MIN_PREROLL_MS = 0
_MAX_PREROLL_MS = 4000


def lab_half_duplex_enabled() -> bool:
    """IMVERA_LAB_HALF_DUPLEX default OFF — always-listen; set 1 for mute-while-Vera."""
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


def uplink_preroll_ms() -> int:
    """Replay last N ms of blocked uplink when listen opens (half-duplex lab)."""
    raw = os.environ.get("IMVERA_UPLINK_PREROLL_MS", str(_DEFAULT_PREROLL_MS)).strip()
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_PREROLL_MS
    return max(_MIN_PREROLL_MS, min(_MAX_PREROLL_MS, value))


def apply_lab_half_duplex_env(env: dict[str, str]) -> dict[str, str]:
    """Apply lab listen-mode defaults without overriding explicit operator choices.

    Defaults: HALF_DUPLEX=0 (always-listen), ECHO_REF_GATE=1, BARGE_IN=0.
    Explicit HALF_DUPLEX=1 keeps mute-while-Vera without echo-ref unless set.
    """
    env.setdefault("IMVERA_LAB_HALF_DUPLEX", "0")
    env.setdefault("IMVERA_POST_SPEECH_PAUSE_MS", str(_DEFAULT_PAUSE_MS))
    env.setdefault("IMVERA_UPLINK_PREROLL_MS", str(_DEFAULT_PREROLL_MS))
    if "IMVERA_ECHO_REF_GATE" not in env:
        half = env.get("IMVERA_LAB_HALF_DUPLEX", "0").strip().lower()
        env["IMVERA_ECHO_REF_GATE"] = "0" if half in {"1", "true", "yes"} else "1"
    env.setdefault("IMVERA_LAB_BARGE_IN", "0")
    return env
