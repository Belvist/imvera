"""Turn FSM + UtteranceBuilder unit tests."""

import time

from packages.voice_runtime.echo_ref_gate import EchoVerdict
from packages.voice_runtime.turn_fsm import (
    ConversationPhase,
    TurnManager,
    policy_for_intent,
)
from packages.voice_runtime.utterance_builder import UtteranceBuilder


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
    frame = b"\x00\x01" * 160  # 20ms @ 16k
    # speech start
    assert builder.on_frame(frame, speech_started=True, speech_ended=False, speech_active=True) is None
    # continue speech
    for _ in range(5):
        assert (
            builder.on_frame(frame, speech_started=False, speech_ended=False, speech_active=True)
            is None
        )
    # micro pause — VAD ended but short silence
    assert builder.on_frame(frame, speech_started=False, speech_ended=True, speech_active=False) is None
    # resume speech within silence hold
    assert builder.on_frame(frame, speech_started=True, speech_ended=False, speech_active=True) is None
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


def test_suppress_speech_start_opening_without_barge_in() -> None:
    tm = TurnManager()
    tm.on_playback_started("opening_wellness", barge_in_enabled=False)
    assert tm.should_suppress_speech_start(
        playback_active=True,
        echo_verdict=EchoVerdict.USER,
    ) is True
