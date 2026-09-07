"""Lab fast TTS — Silero for Zoiper lab (<2s warm first_pcm). MLX remains prod default."""

from __future__ import annotations

import os


def lab_fast_tts_enabled() -> bool:
    """Zoiper lab: prefer Silero over MLX unless explicitly disabled."""
    return os.environ.get("IMVERA_LAB_FAST_TTS", "1").strip().lower() in {"1", "true", "yes"}


def apply_lab_fast_env(env: dict[str, str]) -> dict[str, str]:
    """Set Silero lab engine when IMVERA_LAB_FAST_TTS=1 (default on)."""
    if lab_fast_tts_enabled():
        env.setdefault("IMVERA_TTS_ENGINE", "silero_lab")
        env.setdefault("IMVERA_SILERO_LAB_ACK", "1")
        env.setdefault("IMVERA_OPENING_CACHE", "1")
    return env


def effective_tts_engine(tts_cfg: dict) -> str:
    """Resolve engine with lab-fast override."""
    from services.tts.gen_params import tts_engine

    if lab_fast_tts_enabled() and not os.environ.get("IMVERA_TTS_ENGINE", "").strip():
        return "silero_lab"
    return tts_engine(tts_cfg)
