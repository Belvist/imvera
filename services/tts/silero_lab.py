"""Silero v5_5_ru — LOCAL LAB ONLY (CC BY-NC-SA 4.0, not for production).

# Silero v5_5_ru speaker ``kseniya`` ≈ English «Xenia» (friend's Silero Xenia).
# When torch is unavailable on macOS, falls back to native ``say`` for sub-2s lab TTS.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

SILERO_LICENSE = "CC BY-NC-SA 4.0"
SILERO_WARNING = (
    "Silero v5_5_ru (speaker kseniya) is NON-COMMERCIAL (CC BY-NC-SA 4.0). "
    "LOCAL LAB / listen-test reference only — not for IMVERA production or pilot."
)
MACOS_SAY_SENTINEL = "macos_say"
MACOS_RU_VOICE = os.environ.get("IMVERA_MACOS_SAY_VOICE", "Milena")


_silero_model: Any = None
_silero_device: Any = None


def silero_lab_acknowledged() -> bool:
    return os.environ.get("IMVERA_SILERO_LAB_ACK", "").strip() == "1"


def require_silero_lab() -> None:
    if not silero_lab_acknowledged():
        raise RuntimeError(
            f"{SILERO_WARNING} Set IMVERA_SILERO_LAB_ACK=1 to enable in local lab."
        )


def _torch_available() -> bool:
    try:
        import torch  # noqa: F401

        return True
    except ImportError:
        return False


def _synthesize_macos_say(text: str, sample_rate: int) -> tuple[Any, int]:
    import numpy as np
    import soundfile as sf

    aiff = Path(tempfile.mkstemp(suffix=".aiff")[1])
    wav = Path(tempfile.mkstemp(suffix=".wav")[1])
    try:
        subprocess.run(
            ["say", "-v", MACOS_RU_VOICE, "-o", str(aiff), text],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["afconvert", str(aiff), str(wav), "-d", f"LEI16@{sample_rate}"],
            check=True,
            capture_output=True,
        )
        data, sr = sf.read(str(wav), dtype="float32")
        arr = np.asarray(data, dtype=np.float32)
        if arr.ndim > 1:
            arr = arr.reshape(-1)
        return arr, int(sr)
    finally:
        aiff.unlink(missing_ok=True)
        wav.unlink(missing_ok=True)


def load_silero(silero_cfg: dict[str, Any]) -> tuple[Any, Any]:
    """Load Silero (torch) or macOS say sentinel for fast lab without torch."""
    global _silero_model, _silero_device
    if _silero_model is not None:
        return _silero_model, _silero_device

    require_silero_lab()
    if not _torch_available():
        if sys.platform == "darwin":
            _silero_model = MACOS_SAY_SENTINEL
            _silero_device = None
            print(
                "Lab TTS: macOS say (torch missing — install .[lab-silero] for Silero)",
                flush=True,
            )
            return _silero_model, _silero_device
        raise RuntimeError(
            "silero_lab requires torch on non-macOS: pip install -e '.[lab-silero]'"
        )

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


def lab_backend_name(silero_cfg: dict[str, Any]) -> str:
    model, _ = load_silero(silero_cfg)
    if model == MACOS_SAY_SENTINEL:
        return f"macos_say:{MACOS_RU_VOICE}"
    speaker = silero_cfg.get("speaker", "kseniya")
    return f"silero:{speaker}"


def synthesize_silero(
    text: str,
    silero_cfg: dict[str, Any],
) -> tuple[Any, int]:
    """
    Synthesize full phrase with Silero apply_tts or macOS say fallback.

    Returns (float32 mono numpy array, sample_rate).
    """
    import numpy as np

    model, _device = load_silero(silero_cfg)
    sample_rate = int(silero_cfg.get("sample_rate", 24000))
    if model == MACOS_SAY_SENTINEL:
        return _synthesize_macos_say(text, sample_rate)
    speaker = silero_cfg.get("speaker", "kseniya")
    audio = model.apply_tts(text=text, speaker=speaker, sample_rate=sample_rate)
    arr = np.asarray(audio, dtype=np.float32)
    if arr.ndim > 1:
        arr = arr.reshape(-1)
    return arr, sample_rate
