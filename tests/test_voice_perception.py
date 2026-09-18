"""Tests for voice_perception package."""

from __future__ import annotations

import math
import struct

from packages.voice_perception.config import PerceptionConfig
from packages.voice_perception.echo_ref_gate import DownlinkEchoRef, EchoRefConfig, EchoVerdict
from packages.voice_perception.session import PerceptionSession
from packages.voice_perception.text_echo import is_text_echo_of_bot, text_echo_similarity


def _pcm_sine(
    freq_hz: float, samples: int = 320, sample_rate: int = 16000, amp: int = 8000
) -> bytes:
    out = bytearray()
    for i in range(samples):
        t = i / sample_rate
        sample = int(amp * math.sin(2 * math.pi * freq_hz * t))
        out += struct.pack("<h", max(-32767, min(32767, sample)))
    return bytes(out)


def test_text_echo_detects_vera_question_bleed() -> None:
    from packages.voice_perception.text_echo import compute_text_similarity

    bot = "Как у вас настроение — хотя бы коротко?"
    stt = "Какое настроение, плохо себя чувствуешь?"
    assert text_echo_similarity(stt, bot) >= 0.4
    metrics = compute_text_similarity(stt, bot)
    assert float(metrics["jaccard"]) > 0
    assert is_text_echo_of_bot(stt, bot) is False


def test_text_echo_keeps_real_mood_answer() -> None:
    bot = "А какое у вас сегодня настроение?"
    stt = "Плохое настроение. Говорю, самочувствие плохое."
    assert is_text_echo_of_bot(stt, bot) is False


def test_perception_session_drops_echo_during_playback() -> None:
    ref = DownlinkEchoRef(EchoRefConfig(sample_rate=16000))
    vera = _pcm_sine(440.0)
    ref.push(vera)
    session = PerceptionSession(
        PerceptionConfig(sample_rate=16000, echo_ref_gate=True, lab_half_duplex=False)
    )
    session.push_downlink(vera)
    decision = session.process_uplink(vera, playback_active=True, now_mono=1.0)
    assert decision.feed_vad is False
    assert decision.echo_verdict in {EchoVerdict.ECHO, EchoVerdict.UNCERTAIN}


def test_perception_session_keeps_playback_ref_on_listen_enabled() -> None:
    session = PerceptionSession(
        PerceptionConfig(sample_rate=16000, echo_ref_gate=True, lab_half_duplex=False)
    )
    vera = _pcm_sine(523.0)
    session.push_downlink(vera)
    session.on_playback_completed(1.0)
    session.on_listen_enabled()
    assert session.playback_ref is not None
    assert session.playback_ref.buffered_samples > 0


def test_perception_session_echo_tail_blocks_vad() -> None:
    session = PerceptionSession(
        PerceptionConfig(sample_rate=16000, echo_ref_gate=False, lab_half_duplex=False)
    )
    session.on_playback_started("opening_wellness")
    session.on_playback_completed(1.0)
    decision = session.process_uplink(_pcm_sine(200.0), playback_active=False, now_mono=1.1)
    assert decision.feed_vad is False
    assert decision.buffer_only is True
