"""Tone generation + spectral probe for LiveKit media gate (440-in / 880-out duplex)."""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

MEDIA_GATE_CALLER_HZ = 440.0
MEDIA_GATE_PROBE_OUTBOUND_HZ = 880.0
DEFAULT_TONE_SNR_MIN = 8.0


def generate_tone_s16le(
    *,
    frequency_hz: float,
    duration_s: float,
    sample_rate: int = 16000,
    amplitude: float = 0.25,
) -> bytes:
    samples = int(sample_rate * duration_s)
    out = bytearray(samples * 2)
    for i in range(samples):
        sample = int(amplitude * 32767.0 * math.sin(2.0 * math.pi * frequency_hz * i / sample_rate))
        struct.pack_into("<h", out, i * 2, sample)
    return bytes(out)


def _goertzel_power(samples: list[float], sample_rate: int, frequency_hz: float) -> float:
    n = len(samples)
    if n == 0:
        return 0.0
    k = int(0.5 + (n * frequency_hz) / sample_rate)
    w = (2.0 * math.pi * k) / n
    cosine = math.cos(w)
    coeff = 2.0 * cosine
    s0 = 0.0
    s1 = 0.0
    s2 = 0.0
    for x in samples:
        s0 = x + coeff * s1 - s2
        s2 = s1
        s1 = s0
    return (s1 * s1 + s2 * s2 - coeff * s1 * s2) / n


def tone_snr(
    samples: list[float],
    sample_rate: int,
    target_hz: float,
    *,
    reference_offset_hz: float = 200.0,
) -> float:
    target = _goertzel_power(samples, sample_rate, target_hz)
    reference = _goertzel_power(samples, sample_rate, target_hz + reference_offset_hz)
    return target / max(reference, 1e-9)


def tone_present(
    samples: list[float],
    sample_rate: int,
    target_hz: float,
    *,
    min_snr: float = DEFAULT_TONE_SNR_MIN,
) -> tuple[bool, float]:
    snr = tone_snr(samples, sample_rate, target_hz)
    return snr >= min_snr, snr


def read_wav_mono(path: Path) -> tuple[list[float], int]:
    with wave.open(str(path), "rb") as wf:
        sample_rate = wf.getframerate()
        channels = wf.getnchannels()
        sample_width = wf.getsampwidth()
        frames = wf.readframes(wf.getnframes())
    if sample_width != 2:
        raise ValueError(f"expected 16-bit PCM wav, got width={sample_width}")
    count = len(frames) // 2
    samples = [
        struct.unpack_from("<h", frames, i * 2)[0] for i in range(0, count, channels)
    ]
    return [float(s) for s in samples], sample_rate


def read_u8_mono(path: Path, sample_rate: int = 8000) -> tuple[list[float], int]:
    raw = path.read_bytes()
    # unsigned 8-bit G.711-style center at 128
    return [float(b - 128) for b in raw], sample_rate


def analyze_duplex_probe(
    *,
    inbound_wav: Path,
    downlink_path: Path,
    caller_hz: float = MEDIA_GATE_CALLER_HZ,
    probe_outbound_hz: float = MEDIA_GATE_PROBE_OUTBOUND_HZ,
    min_snr: float = DEFAULT_TONE_SNR_MIN,
) -> dict[str, float | bool]:
    inbound_samples, inbound_sr = read_wav_mono(inbound_wav)
    if downlink_path.suffix.lower() == ".wav":
        downlink_samples, downlink_sr = read_wav_mono(downlink_path)
    else:
        downlink_samples, downlink_sr = read_u8_mono(downlink_path)

    inbound_440, inbound_440_snr = tone_present(
        inbound_samples, inbound_sr, caller_hz, min_snr=min_snr
    )
    inbound_880, inbound_880_snr = tone_present(
        inbound_samples, inbound_sr, probe_outbound_hz, min_snr=min_snr
    )
    downlink_880, downlink_880_snr = tone_present(
        downlink_samples, downlink_sr, probe_outbound_hz, min_snr=min_snr
    )
    return {
        "inbound_has_440_hz": inbound_440,
        "inbound_has_880_hz": inbound_880,
        "caller_downlink_has_880_hz": downlink_880,
        "inbound_440_snr": round(inbound_440_snr, 2),
        "inbound_880_snr": round(inbound_880_snr, 2),
        "caller_880_snr": round(downlink_880_snr, 2),
    }
