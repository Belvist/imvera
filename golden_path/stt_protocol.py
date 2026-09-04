"""STT protocol stubs for Stage B audio lab."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class STTBackend(ABC):
    """Transcribe mono WAV to text."""

    @abstractmethod
    def transcribe(self, wav_path: Path) -> str:
        raise NotImplementedError


class Qwen3AsrBackend(STTBackend):
    """Qwen3-ASR host adapter — not wired until Stage B owner pass."""

    def transcribe(self, wav_path: Path) -> str:
        raise NotImplementedError(
            "Qwen3AsrBackend is Stage B only; owner must accept Stage A first "
            f"(file={wav_path})"
        )


class GigaAmBackend(STTBackend):
    """GigaAM host adapter — not wired until Stage B owner pass."""

    def transcribe(self, wav_path: Path) -> str:
        raise NotImplementedError(
            "GigaAmBackend is Stage B only; owner must accept Stage A first "
            f"(file={wav_path})"
        )


def get_stt_backend(name: str) -> STTBackend:
    key = name.strip().lower()
    if key in ("qwen3", "qwen3-asr", "qwen"):
        return Qwen3AsrBackend()
    if key in ("gigaam", "giga"):
        return GigaAmBackend()
    raise ValueError(f"unknown STT backend: {name}")
