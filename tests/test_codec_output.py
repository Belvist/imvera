"""Codec-aware PCM output rates."""

from packages.voice_runtime.codec_output import (
    bridge_audio_rates,
    resampler_chain_summary,
    target_pcm_rate_for_codec,
)


def test_g722_targets_tts_native_24k() -> None:
    assert target_pcm_rate_for_codec("G722") == 24000


def test_pcmu_targets_8k() -> None:
    assert target_pcm_rate_for_codec("PCMU") == 8000


def test_opus_targets_48k() -> None:
    assert target_pcm_rate_for_codec("opus") == 48000


def test_g722_resampler_chain_is_not_48k_hop() -> None:
    chain = resampler_chain_summary(
        tts_native_rate=24000,
        bridge_output_rate=24000,
        negotiated_codec="G722",
    )
    assert chain["bridge_output_rate"] == 24000
    assert chain["resampler_count"] == 0
    assert "48" not in chain["resampler_hops"]


def test_bridge_audio_rates_default_g722_lab() -> None:
    capture, playback = bridge_audio_rates("G722")
    assert capture == 16000
    assert playback == 24000
