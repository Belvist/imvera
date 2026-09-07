"""Lab listen policy — half-duplex mute (friend MVP) vs always-listen + echo ref.

Acoustic echo on softphones (Zoiper) feeds TTS into capture. Two lab modes:

1. Half-duplex mute (IMVERA_LAB_HALF_DUPLEX=1): Vera speaks → finish → pause → mic.
   Stable but feels "deaf" during TTS. Friend's MVP pattern.

2. Always-listen + reference echo gate (default): keep uplink open; drop frames that
   match recently injected downlink PCM. See echo_ref_gate.py.

Default toward always-listen once the reference gate is enabled.
"""

from __future__ import annotations

import os

from packages.voice_runtime.echo_ref_gate import apply_echo_ref_env

_DEFAULT_PAUSE_MS = 400
_MIN_PAUSE_MS = 0
_MAX_PAUSE_MS = 2000


def lab_half_duplex_enabled() -> bool:
    """IMVERA_LAB_HALF_DUPLEX — default off (always-listen + echo ref preferred)."""
    return os.environ.get("IMVERA_LAB_HALF_DUPLEX", "0").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def post_speech_pause_ms() -> int:
    """Quiet after playback drain before VAD/listen (ms). Used only when half-duplex on."""
    raw = os.environ.get("IMVERA_POST_SPEECH_PAUSE_MS", str(_DEFAULT_PAUSE_MS)).strip()
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_PAUSE_MS
    return max(_MIN_PAUSE_MS, min(_MAX_PAUSE_MS, value))


def apply_lab_half_duplex_env(env: dict[str, str]) -> dict[str, str]:
    """Lab listen defaults: echo ref on, half-duplex mute off, barge-in off."""
    apply_echo_ref_env(env)
    env.setdefault("IMVERA_LAB_HALF_DUPLEX", "0")
    env.setdefault("IMVERA_POST_SPEECH_PAUSE_MS", str(_DEFAULT_PAUSE_MS))
    return env
