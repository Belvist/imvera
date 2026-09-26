"""WAV load/save and RTP uplink playback for black-box caller."""

from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WavClip:
    pcm_u8: bytes
    sample_rate: int


def load_wav_u8(path: Path, *, target_rate: int = 8000) -> WavClip:
    """Load WAV → mono unsigned 8-bit @ target_rate (pyVoIP uplink format)."""
    if not path.is_file():
        raise FileNotFoundError(f"blackbox WAV missing: {path}")
    with tempfile.NamedTemporaryFile(suffix=".u8", delete=False) as tmp:
        u8_path = Path(tmp.name)
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(path),
                "-ac",
                "1",
                "-ar",
                str(target_rate),
                "-f",
                "u8",
                str(u8_path),
            ],
            check=True,
            capture_output=True,
        )
        pcm_u8 = u8_path.read_bytes()
    finally:
        u8_path.unlink(missing_ok=True)
    return WavClip(pcm_u8=pcm_u8, sample_rate=target_rate)


def save_pcm_u8_wav(pcm_u8: bytes, path: Path, *, sample_rate: int = 8000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "u8",
            "-ar",
            str(sample_rate),
            "-ac",
            "1",
            "-i",
            "pipe:0",
            str(path),
        ],
        input=pcm_u8,
        check=True,
        capture_output=True,
    )


class DownlinkRecorder:
    def __init__(self) -> None:
        self._buf = bytearray()

    def extend(self, chunk: bytes) -> None:
        if chunk:
            self._buf.extend(chunk)

    def bytes(self) -> bytes:
        return bytes(self._buf)

    def save(self, path: Path, *, sample_rate: int = 8000) -> None:
        save_pcm_u8_wav(self.bytes(), path, sample_rate=sample_rate)


def play_u8_on_call(
    call,
    pcm_u8: bytes,
    *,
    frame_bytes: int,
    frame_sleep_s: float = 0.02,
    leading_silence_ms: int = 200,
    trailing_silence_ms: int = 400,
) -> None:
    import time

    silence = bytes([128]) * frame_bytes
    if leading_silence_ms > 0:
        n_frames = max(1, int(leading_silence_ms / (frame_sleep_s * 1000)))
        for _ in range(n_frames):
            call.write_audio(silence)
            time.sleep(frame_sleep_s)
    for offset in range(0, len(pcm_u8), frame_bytes):
        frame = pcm_u8[offset : offset + frame_bytes]
        if len(frame) < frame_bytes:
            frame = frame + bytes([128]) * (frame_bytes - len(frame))
        call.write_audio(frame)
        time.sleep(frame_sleep_s)
    if trailing_silence_ms > 0:
        n_trail = max(1, int(trailing_silence_ms / (frame_sleep_s * 1000)))
        for _ in range(n_trail):
            call.write_audio(silence)
            time.sleep(frame_sleep_s)
