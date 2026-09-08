"""FreeSWITCH mod_audio_stream downlink — streamAudio JSON (v1.0.3+)."""

from __future__ import annotations

import base64
import json


def encode_stream_audio_json(pcm_s16le: bytes, sample_rate: int) -> str:
    """JSON text frame for mod_audio_stream STREAM_PLAYBACK auto-playback."""
    if not pcm_s16le:
        raise ValueError("pcm_s16le must not be empty")
    if sample_rate <= 0:
        raise ValueError("sample_rate must be positive")
    payload = {
        "type": "streamAudio",
        "data": {
            "audioDataType": "raw",
            "sampleRate": int(sample_rate),
            "audioData": base64.b64encode(pcm_s16le).decode("ascii"),
        },
    }
    return json.dumps(payload, separators=(",", ":"))
