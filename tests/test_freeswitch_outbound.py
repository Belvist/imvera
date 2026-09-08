"""streamAudio JSON encoder for mod_audio_stream."""

from __future__ import annotations

import base64
import json

import pytest

from packages.telephony.freeswitch_outbound import encode_stream_audio_json


def test_encode_stream_audio_json_roundtrip_shape() -> None:
    pcm = b"\x00\x01" * 80
    raw = encode_stream_audio_json(pcm, 16000)
    data = json.loads(raw)
    assert data["type"] == "streamAudio"
    assert data["data"]["audioDataType"] == "raw"
    assert data["data"]["sampleRate"] == 16000
    assert base64.b64decode(data["data"]["audioData"]) == pcm


def test_encode_stream_audio_json_rejects_empty() -> None:
    with pytest.raises(ValueError):
        encode_stream_audio_json(b"", 16000)
