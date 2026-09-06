"""Silero v5_5_ru — LOCAL LAB ONLY (CC BY-NC-SA 4.0, not for production)."""

from __future__ import annotations

import os
from typing import Any

SILERO_LICENSE = "CC BY-NC-SA 4.0"
SILERO_WARNING = (
    "Silero v5_5_ru (speaker kseniya) is NON-COMMERCIAL (CC BY-NC-SA 4.0). "
    "LOCAL LAB / listen-test reference only — not for IMVERA production or pilot."
)

_silero_model: Any = None
_silero_device: Any = None


def silero_lab_acknowledged() -> bool:
    return os.environ.get("IMVERA_SILERO_LAB_ACK", "").strip() == "1"


def require_silero_lab() -> None:
    if not silero_lab_acknowledged():
        raise RuntimeError(
            f"{SILERO_WARNING} Set IMVERA_SILERO_LAB_ACK=1 to enable in local lab."
        )


def load_silero(silero_cfg: dict[str, Any]) -> tuple[Any, Any]:
    """Load Silero TTS model (torch hub). Requires torch."""
    global _silero_model, _silero_device
    if _silero_model is not None:
        return _silero_model, _silero_device

    require_silero_lab()
    import torch

    device = torch.device("cpu")
    language = silero_cfg.get("language", "ru")
    model_name = silero_cfg.get("model", "v5_5_ru")
    model, _ = torch.hub.load(
        repo_or_dir="snakers4/silero-models",
        model="silero_tts",
        language=language,
        speaker=model_name,
        trust_repo=True,
    )
    model.to(device)
    _silero_model = model
    _silero_device = device
    return model, device


def synthesize_silero(
    text: str,
    silero_cfg: dict[str, Any],
) -> tuple[Any, int]:
    """
    Synthesize full phrase with Silero apply_tts.

    Returns (float32 mono numpy array, sample_rate).
    """
    import numpy as np

    model, _device = load_silero(silero_cfg)
    speaker = silero_cfg.get("speaker", "kseniya")
    sample_rate = int(silero_cfg.get("sample_rate", 24000))
    audio = model.apply_tts(text=text, speaker=speaker, sample_rate=sample_rate)
    arr = np.asarray(audio, dtype=np.float32)
    if arr.ndim > 1:
        arr = arr.reshape(-1)
    return arr, sample_rate
