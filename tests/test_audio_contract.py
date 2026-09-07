"""Audio contract unit checks — ADR-008."""

from packages.voice_runtime.audio import (
    AudioEnvelope,
    StatefulResampler,
    belongs_to_active_output,
    pcm16_frame_bytes,
    pcm_rms_s16le,
)
from packages.voice_runtime.playback import split_pcm_frames


def test_pcm_rms_silence_and_signal() -> None:
    assert pcm_rms_s16le(b"\x00\x00" * 100) == 0.0
    assert pcm_rms_s16le(b"\x30\x00" * 100) > 0.0


def test_pcm16_frame_sizes() -> None:
    assert pcm16_frame_bytes(16000) == 640
    assert pcm16_frame_bytes(8000) == 320


def test_belongs_to_active_output() -> None:
    chunk = AudioEnvelope(
        call_id="c1",
        generation_id="g1",
        phrase_id="p1",
        sequence=0,
        sample_rate=16000,
        pcm_s16le=b"\x00\x00",
    )
    assert belongs_to_active_output(chunk, "c1", "g1")
    assert not belongs_to_active_output(chunk, "c1", "g2")


def test_resampler_8k_to_16k() -> None:
    resampler = StatefulResampler(8000, 16000)
    pcm8 = b"\x00\x01" * 160
    out = resampler.process(pcm8)
    assert len(out) >= 2


def test_resampler_chunked_matches_whole() -> None:
    source_rate = 24000
    target_rate = 16000
    one_second = b"\x10\x00" * source_rate
    whole = StatefulResampler(source_rate, target_rate)
    whole_out = whole.process(one_second) + whole.flush()

    chunked = StatefulResampler(source_rate, target_rate)
    parts: list[bytes] = []
    step = 997  # odd chunk size to stress alignment
    for offset in range(0, len(one_second), step * 2):
        parts.append(chunked.process(one_second[offset : offset + step * 2]))
    parts.append(chunked.flush())
    split_out = b"".join(parts)

    assert len(whole_out) == len(split_out)
    assert abs(len(whole_out) // 2 - target_rate) <= 2


def test_playback_carries_partial_until_flush() -> None:
    frame = pcm16_frame_bytes(16000, 20)
    partial = b"\x00\x01" * 50
    assert len(partial) < frame
    parts = split_pcm_frames(partial, 16000, 20)
    assert parts == []
