"""Audio contract unit checks — ADR-008."""

from packages.voice_runtime.audio import (
    AudioEnvelope,
    StatefulResampler,
    belongs_to_active_output,
    pcm16_frame_bytes,
)


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
