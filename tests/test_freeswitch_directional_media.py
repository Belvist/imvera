"""Directional media invariant tests — telephony-neutral (ADR-010 / ADR-013)."""

from __future__ import annotations

import tempfile
import wave
from pathlib import Path

from tools.telephony_gate.evidence import MediaGateEvidence, MediaGateFailure, classify_media_gate
from tools.telephony_gate.tone import (
    MEDIA_GATE_CALLER_HZ,
    analyze_duplex_probe,
    generate_tone_s16le,
    tone_present,
)


def _write_wav(path: Path, pcm: bytes, sample_rate: int = 16000) -> None:
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)


def test_tone_present_detects_440hz() -> None:
    pcm = generate_tone_s16le(frequency_hz=MEDIA_GATE_CALLER_HZ, duration_s=0.5)
    samples = [int.from_bytes(pcm[i : i + 2], "little", signed=True) for i in range(0, len(pcm), 2)]
    present, snr = tone_present([float(s) for s in samples], 16000, MEDIA_GATE_CALLER_HZ)
    assert present
    assert snr > 8.0


def test_directional_probe_pass() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        inbound = Path(tmp) / "raw_inbound.wav"
        downlink = Path(tmp) / "downlink.wav"
        _write_wav(inbound, generate_tone_s16le(frequency_hz=440.0, duration_s=0.5))
        _write_wav(downlink, generate_tone_s16le(frequency_hz=880.0, duration_s=0.5))
        spectral = analyze_duplex_probe(inbound_wav=inbound, downlink_path=downlink)
        assert spectral["inbound_has_440_hz"]
        assert not spectral["inbound_has_880_hz"]
        assert spectral["caller_downlink_has_880_hz"]


def test_classify_directional_violation() -> None:
    ev = MediaGateEvidence(
        call_id="fs-dir",
        fs_answered_at=1.0,
        bridge_ws_connected_at=1.1,
        bridge_rx_frames=10,
        nonzero_pcm_frames=5,
        inbound_rms_peak=500.0,
        inbound_has_440_hz=True,
        inbound_has_880_hz=True,
        caller_downlink_has_880_hz=True,
    )
    assert classify_media_gate(ev) == MediaGateFailure.VERA_IN_INBOUND


def test_classify_p0a_passed_without_bridge_tx() -> None:
    ev = MediaGateEvidence(
        call_id="fs-p0a",
        fs_answered_at=1.0,
        bridge_ws_connected_at=1.1,
        bridge_rx_frames=80,
        bridge_tx_frames=0,
        nonzero_pcm_frames=40,
        inbound_rms_peak=1200.0,
        inbound_has_440_hz=True,
        inbound_has_880_hz=False,
        caller_downlink_has_880_hz=True,
        synthetic_downlink_wav="/tmp/downlink.wav",
        gate_phase="p0a",
    )
    assert classify_media_gate(ev, phase="p0a") == MediaGateFailure.PASSED
