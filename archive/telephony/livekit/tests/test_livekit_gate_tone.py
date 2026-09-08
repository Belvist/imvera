"""Unit tests for LiveKit gate tone probe."""

from __future__ import annotations

import struct
import wave
from pathlib import Path

from packages.telephony.livekit_gate_tone import (
    MEDIA_GATE_CALLER_HZ,
    MEDIA_GATE_PROBE_OUTBOUND_HZ,
    analyze_duplex_probe,
    generate_tone_s16le,
    tone_present,
)


def _write_wav(path: Path, pcm: bytes, sample_rate: int) -> None:
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)


def test_tone_present_on_generated_s16(tmp_path: Path) -> None:
    pcm = generate_tone_s16le(frequency_hz=440.0, duration_s=0.5, sample_rate=16000)
    samples = [struct.unpack_from("<h", pcm, i)[0] for i in range(0, len(pcm), 2)]
    ok, snr = tone_present([float(s) for s in samples], 16000, 440.0)
    assert ok
    assert snr > 8.0


def test_duplex_probe_pass(tmp_path: Path) -> None:
    inbound = tmp_path / "in.wav"
    downlink = tmp_path / "down.u8"
    _write_wav(
        inbound,
        generate_tone_s16le(frequency_hz=MEDIA_GATE_CALLER_HZ, duration_s=1.0),
        16000,
    )
    downlink.write_bytes(
        bytes(
            127 + int(100 * __import__("math").sin(2 * __import__("math").pi * MEDIA_GATE_PROBE_OUTBOUND_HZ * i / 8000))
            for i in range(8000)
        )
    )
    result = analyze_duplex_probe(inbound_wav=inbound, downlink_path=downlink)
    assert result["inbound_has_440_hz"] is True
    assert result["inbound_has_880_hz"] is False
    assert result["caller_downlink_has_880_hz"] is True
