"""Perception layer configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass

from packages.voice_perception.echo_ref_gate import echo_ref_gate_enabled, lab_barge_in_enabled


def _int_env(name: str, default: int, *, min_v: int, max_v: int) -> int:
    raw = os.environ.get(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(min_v, min(max_v, value))


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name, "1" if default else "0").strip().lower()
    return raw in {"1", "true", "yes"}


@dataclass(frozen=True)
class PerceptionConfig:
    """Runtime tuning for one perception session."""

    sample_rate: int = 16000
    echo_ref_gate: bool = False
    lab_half_duplex: bool = False
    lab_barge_in: bool = False
    post_speech_pause_ms: int = 100
    uplink_preroll_ms: int = 300


def perception_config_from_env(
    *,
    sample_rate: int = 16000,
    lab_half_duplex: bool | None = None,
) -> PerceptionConfig:
    """Build config from IMVERA_* env (same flags as CallActor lab)."""
    if lab_half_duplex is None:
        lab_half_duplex = _bool_env("IMVERA_LAB_HALF_DUPLEX", default=False)
    return PerceptionConfig(
        sample_rate=sample_rate,
        echo_ref_gate=echo_ref_gate_enabled(),
        lab_half_duplex=lab_half_duplex,
        lab_barge_in=lab_barge_in_enabled(),
        post_speech_pause_ms=_int_env(
            "IMVERA_POST_SPEECH_PAUSE_MS", 100, min_v=0, max_v=2000
        ),
        uplink_preroll_ms=_int_env(
            "IMVERA_UPLINK_PREROLL_MS", 300, min_v=0, max_v=4000
        ),
    )
