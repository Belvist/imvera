"""Silero VAD adapter tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from packages.voice_runtime.audio import pcm16_frame_bytes
from packages.voice_runtime.silero_vad import SileroVad, create_vad

MODEL = Path(__file__).resolve().parents[1] / "config" / "models" / "silero_vad.onnx"


@pytest.mark.skipif(not MODEL.exists(), reason="silero_vad.onnx not prepared")
def test_silero_vad_state_model_loads_and_feeds() -> None:
    vad = SileroVad(16000, model_path=MODEL)
    assert getattr(vad, "_uses_state", False)
    frame_bytes = pcm16_frame_bytes(16000, 20)
    silent = b"\x00\x00" * (frame_bytes // 2)
    for _ in range(4):
        vad.feed(silent)


def test_create_vad_prefers_silero_when_model_present() -> None:
    from packages.voice_runtime.vad import EnergyVad

    vad = create_vad(16000)
    if MODEL.exists():
        assert isinstance(vad, SileroVad)
    else:
        assert isinstance(vad, EnergyVad)
