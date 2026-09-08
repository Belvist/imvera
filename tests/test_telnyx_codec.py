"""Telnyx codec tests — PCMU fallback + L16/16kHz production preferred."""

import audioop
import base64
import struct

import pytest

from packages.telephony.telnyx_codec import (
    TARGET_SAMPLE_RATE,
    TelnyxCodecError,
    TelnyxEncoding,
    TelnyxNegotiatedFormat,
    decode_inbound_payload,
    encode_outbound_b64,
    encode_outbound_payload,
)


def test_pcmu_decode_resamples_to_16k() -> None:
    pcm8 = b"\x10\x20" * 80
    ulaw = audioop.lin2ulaw(pcm8, 2)
    fmt = TelnyxNegotiatedFormat(TelnyxEncoding.PCMU, 8000, 1)
    b64 = base64.b64encode(ulaw).decode()
    out = decode_inbound_payload(b64, fmt, target_sample_rate=TARGET_SAMPLE_RATE)
    assert len(out) > len(pcm8)
    peak = max(
        abs(int.from_bytes(out[i : i + 2], "little", signed=True))
        for i in range(0, len(out), 2)
    )
    assert peak > 0


def test_l16_endian_exact_samples() -> None:
    samples = [100, -200, 300, -400]
    be = struct.pack(">4h", *samples)
    fmt = TelnyxNegotiatedFormat(TelnyxEncoding.L16, 16000, 1)
    b64 = base64.b64encode(be).decode()
    out = decode_inbound_payload(b64, fmt)
    le = struct.unpack("<4h", out)
    assert le == tuple(samples)


def test_l16_outbound_network_byte_order() -> None:
    pcm = struct.pack("<4h", 1, 2, 3, 4)
    fmt = TelnyxNegotiatedFormat(TelnyxEncoding.L16, 16000, 1)
    raw = encode_outbound_payload(pcm, 16000, fmt)
    assert raw == struct.pack(">4h", 1, 2, 3, 4)


def test_unsupported_encoding_raises() -> None:
    with pytest.raises(TelnyxCodecError):
        TelnyxNegotiatedFormat.from_start(
            {"encoding": "OPUS", "sample_rate": 16000, "channels": 1}
        )


def test_pcmu_wrong_rate_raises() -> None:
    with pytest.raises(TelnyxCodecError):
        TelnyxNegotiatedFormat.from_start(
            {"encoding": "PCMU", "sample_rate": 16000, "channels": 1}
        )


def test_outbound_pcmu_roundtrip_b64() -> None:
    pcm = b"\x12\x34" * 40
    fmt = TelnyxNegotiatedFormat(TelnyxEncoding.PCMU, 8000, 1)
    b64 = encode_outbound_b64(pcm, 16000, fmt)
    assert isinstance(b64, str)
    assert len(b64) > 0
