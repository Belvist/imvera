"""Turn FSM + UtteranceBuilder unit tests."""

import time

import pytest

from packages.voice_runtime.echo_ref_gate import EchoVerdict
from packages.voice_runtime.turn_fsm import (
    ConversationPhase,
    TurnManager,
    policy_for_intent,
)
from packages.voice_runtime.utterance_builder import UtteranceBuilder, UtteranceBuilderConfig


def test_opening_policy_buffers_during_bot_speech() -> None:
    tm = TurnManager()
    tm.on_playback_started("opening_wellness", barge_in_enabled=False)
    assert tm.phase == ConversationPhase.BOT_SPEAKING
    assert tm.should_buffer_only() is True
    assert tm.should_feed_vad() is False
    assert tm.should_emit_utterance() is False


def test_opening_echo_tail_then_listen() -> None:
    tm = TurnManager()
    tm.on_playback_started("opening_wellness", barge_in_enabled=False)
    now = time.monotonic()
    tm.on_playback_completed(now)
    assert tm.phase == ConversationPhase.ECHO_TAIL
    assert tm.should_feed_vad() is False
    tm.tick(now + 0.46)
    assert tm.phase == ConversationPhase.LISTENING
    assert tm.should_feed_vad() is True
    assert tm.should_emit_utterance() is True


def test_normal_policy_feeds_vad_during_bot_but_no_stt() -> None:
    tm = TurnManager()
    tm.on_playback_started("check_mood", barge_in_enabled=False)
    policy = policy_for_intent("check_mood", barge_in_enabled=False)
    assert policy.buffer_during_bot_speech is False
    assert tm.should_feed_vad() is True
    assert tm.should_emit_utterance() is False


def test_utterance_builder_merges_micro_pause() -> None:
    builder = UtteranceBuilder(16000)
    frame = b"\x00\x01" * 320
    # speech start
    assert builder.on_frame(
        frame, speech_started=True, speech_ended=False, speech_active=True
    ) is None
    # continue speech
    for _ in range(5):
        assert (
            builder.on_frame(frame, speech_started=False, speech_ended=False, speech_active=True)
            is None
        )
    # micro pause — VAD ended but short silence
    assert builder.on_frame(
        frame, speech_started=False, speech_ended=True, speech_active=False
    ) is None
    # resume speech within silence hold
    assert builder.on_frame(
        frame, speech_started=True, speech_ended=False, speech_active=True
    ) is None
    for _ in range(5):
        assert (
            builder.on_frame(frame, speech_started=False, speech_ended=False, speech_active=True)
            is None
        )
    # endpoint silence
    hold_frames = 500 // 20
    post_frames = 150 // 20
    built = None
    for i in range(hold_frames + post_frames + 5):
        built = builder.on_frame(
            frame,
            speech_started=False,
            speech_ended=i == 0,
            speech_active=False,
        )
        if built is not None:
            break
    assert built is not None
    assert built.duration_ms > 200


@pytest.mark.parametrize("sample_rate", [8000, 16000, 24000])
def test_utterance_builder_pcm16_duration_exact(sample_rate: int) -> None:
    builder = UtteranceBuilder(sample_rate)
    frames = [i.to_bytes(2, "little") * (sample_rate // 50) for i in range(50)]
    for i, frame in enumerate(frames):
        assert builder.on_frame(
            frame, speech_started=i == 0, speech_ended=False, speech_active=True
        ) is None
    built = builder.force_finalize()
    assert built is not None
    assert built.pcm == b"".join(frames)
    assert built.duration_ms == 1000
    assert built.speech_ms == 1000
    assert builder.force_finalize() is None


@pytest.mark.parametrize("resume_start", [True, False])
def test_resume_during_postroll_preserves_frame_order(resume_start: bool) -> None:
    builder = UtteranceBuilder(
        16000,
        UtteranceBuilderConfig(silence_hold_ms=40, post_roll_ms=60, min_speech_ms=20),
    )
    frames = [i.to_bytes(2, "little") * 320 for i in range(12)]
    speech = [True, False, False, False, True, True, True, False, False, False, False, False]
    for i, frame in enumerate(frames):
        built = builder.on_frame(
            frame,
            speech_started=i == 0 or (i == 4 and resume_start),
            speech_ended=i in (1, 7),
            speech_active=speech[i],
        )
        if i < len(frames) - 1:
            assert built is None, f"Premature finalization at frame {i}"
    assert built is not None
    assert built.pcm == b"".join(frames)
    assert built.duration_ms == 240
    assert built.speech_ms == 80
    assert built.silence_tail_ms == 100
    assert not builder.collecting
    assert builder.force_finalize() is None


def test_endpoint_reports_entire_silence_tail() -> None:
    builder = UtteranceBuilder(
        16000,
        UtteranceBuilderConfig(silence_hold_ms=40, post_roll_ms=60, min_speech_ms=20),
    )
    frame = b"\x01\x00" * 320
    assert builder.on_frame(
        frame, speech_started=True, speech_ended=False, speech_active=True
    ) is None
    for i in range(5):
        built = builder.on_frame(
            frame, speech_started=False, speech_ended=i == 0, speech_active=False
        )
        if i < 4:
            assert built is None
    assert built is not None
    assert built.silence_tail_ms == 100


def test_suppress_speech_start_opening_without_barge_in() -> None:
    tm = TurnManager()
    tm.on_playback_started("opening_wellness", barge_in_enabled=False)
    assert tm.should_suppress_speech_start(
        playback_active=True,
        echo_verdict=EchoVerdict.USER,
    ) is True
