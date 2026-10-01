"""PCM/runtime contracts; synthetic timing is not a live voice quality score."""

from __future__ import annotations

import asyncio
import math
import struct
from types import SimpleNamespace

import pytest

from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.session import CallSession
from packages.voice_perception.turn_fsm import ConversationPhase
from packages.voice_runtime.audio import AudioEnvelope
from packages.voice_runtime.call_actor import CallActor, CallActorConfig, MediaCallbacks
from packages.voice_runtime.playback import PlaybackQueue
from packages.voice_runtime.utterance_builder import UtteranceBuilder
from packages.voice_runtime.vad import EnergyVad, VadConfig


def tone(hz: int = 200) -> bytes:
    return b"".join(struct.pack("<h", int(4000 * math.sin(2 * math.pi * hz * i / 16000)))
                    for i in range(320))


async def noop(*args, **kwargs):
    return None


def actor_for_audio(*, media=None, tts=None, llm=None):
    session = CallSession(call_id="realtime-contract", family_id="family",
                          store=InMemoryCallRecordStore())
    actor = CallActor(
        call_id=session.state.call_id, family_id="family", session=session,
        stt=SimpleNamespace(), tts=tts or SimpleNamespace(cancel=noop),
        llm=llm or SimpleNamespace(cancel_request=noop),
        media=media or MediaCallbacks(noop, noop, noop, noop),
        config=CallActorConfig(lab_half_duplex=False, echo_ref_gate=True,
                               lab_barge_in=True, telephony_stream=False),
    )
    actor._vad = EnergyVad(16000, VadConfig(min_speech_ms=100, min_silence_ms=650))
    actor._utterance_builder = UtteranceBuilder(16000)
    actor._collector = actor._utterance_builder
    actor._playback = PlaybackQueue(actor.call_id, sample_rate=16000)
    return actor


@pytest.mark.parametrize("pause_ms", [0, 100, 300, 500])
def test_endpoint_counts_vad_silence_once_and_preserves_a_micro_pause(pause_ms):
    async def scenario():
        actor = actor_for_audio()
        captured = []

        async def capture(pcm, seq):
            captured.append((pcm, seq))

        actor._handle_utterance = capture
        phrase = [tone()] * 25 + [bytes(640)] * (pause_ms // 20) + [tone(250)] * 25
        for frame in phrase:
            await actor._process_uplink_vad_frame(frame, playback_active=False)
        assert not captured
        quiet_frames = 0
        for _ in range(70):
            quiet_frames += 1
            await actor._process_uplink_vad_frame(bytes(640), playback_active=False)
            await asyncio.sleep(0)
            if captured:
                break
        assert len(captured) == 1
        # 660ms quantized VAD endpoint + 140ms post-roll; no second 500ms hold.
        assert quiet_frames * 20 <= 820
        pcm, seq = captured[0]
        assert b"".join(phrase[5:]) in pcm  # complete post-onset phrase, in order
        assert seq == 1

    asyncio.run(scenario())


@pytest.mark.parametrize("blocker", ["storage", "llm"])
def test_audio_is_cancelled_before_slow_storage_or_remote_llm(blocker, monkeypatch):
    async def scenario():
        blocked = asyncio.Event()
        release = asyncio.Event()
        stopped = asyncio.Event()
        calls = []

        async def slow(*args, **kwargs):
            blocked.set()
            await release.wait()

        async def cancel(gen):
            calls.append(("local", gen))
            return {"generation_id": gen, "purged_frames": 1}

        async def stop():
            calls.append(("downstream", "old"))
            stopped.set()
            return {"ok": True}

        actor = actor_for_audio(
            media=MediaCallbacks(noop, noop, noop, noop, cancel_generation=cancel,
                                 request_downstream_stop=stop),
            llm=SimpleNamespace(cancel_request=slow if blocker == "llm" else noop),
        )
        actor._playback.begin_phrase("old", "p", "Как вы себя чувствуете?")
        actor._active_generation = "old"
        if blocker == "storage":
            actor._outbox_action_id = "old-action"
            monkeypatch.setattr(actor, "_finalize_outbox_action", slow)
        else:
            actor._active_llm_request_id = "old-llm"
        task = asyncio.create_task(actor._interrupt_playback(flush=True))
        try:
            await asyncio.wait_for(blocked.wait(), timeout=1)
            assert stopped.is_set(), "audio stop must not wait on non-audio work"
            assert actor._playback.is_cancelled("old")
            assert actor._active_generation is None
            assert calls[:2] == [("local", "old"), ("downstream", "old")]
        finally:
            release.set()
            await task

    asyncio.run(scenario())


def test_barge_detection_precedes_stop_and_user_phase_survives(monkeypatch):
    async def scenario():
        events = []

        async def emit(event):
            events.append(event)

        async def stop():
            assert any(e.payload.get("stage") == "bargein_detected" for e in events)
            return {"ok": True}

        actor = actor_for_audio(media=MediaCallbacks(noop, noop, noop, emit,
                                                     request_downstream_stop=stop))
        actor._last_delivered_intent = "check_mood"
        actor._playback.begin_phrase("old", "p", "Как настроение?")
        actor._active_generation = "old"
        actor._on_bot_playback_started()
        # Isolate cancellation/phase from the separate acoustic admission test.
        monkeypatch.setattr(actor, "_should_suppress_speech_start_during_playback", lambda _: False)
        for _ in range(6):
            await actor._process_uplink_vad_frame(tone(), playback_active=True)
        assert actor._active_generation is None
        assert actor._turn_manager.phase == ConversationPhase.USER_SPEAKING
        assert actor._collector.collecting
        assert actor._playback.is_cancelled("old")
        stages = [e.payload.get("stage") for e in events]
        assert stages.index("bargein_detected") < stages.index("transport.cancel")

    asyncio.run(scenario())


@pytest.mark.parametrize("intent", ["opening_wellness", "confirm_identity", "confirm_consent"])
def test_barge_flag_does_not_bypass_protected_turn_policy(intent):
    async def scenario():
        actor = actor_for_audio()
        actor._last_delivered_intent = intent
        actor._active_generation = "protected"
        actor._playback.begin_phrase("protected", "p", "Здравствуйте.")
        actor._on_bot_playback_started()
        for _ in range(6):
            await actor._process_uplink_vad_frame(tone(), playback_active=True)
        assert actor._active_generation == "protected"
        assert not actor._playback.is_cancelled("protected")

    asyncio.run(scenario())


@pytest.mark.parametrize("pause_ms", [700, 740, 760])
def test_tail_speech_can_resume_in_the_same_utterance(pause_ms):
    async def scenario():
        actor = actor_for_audio()
        captured = []

        async def capture(pcm, seq):
            captured.append(pcm)

        actor._handle_utterance = capture
        frames = [tone()] * 25 + [bytes(640)] * (pause_ms // 20) + [tone(250)] * 25
        for frame in frames:
            await actor._process_uplink_vad_frame(frame, playback_active=False)
        assert not captured
        for _ in range(70):
            await actor._process_uplink_vad_frame(bytes(640), playback_active=False)
            await asyncio.sleep(0)
        assert len(captured) == 1
        assert b"".join(frames[5:]) in captured[0]

    asyncio.run(scenario())


@pytest.mark.parametrize("stop_kind", ["unsupported", "timeout", "missing"])
def test_failed_downstream_stop_keeps_local_cancel_and_reports_no_audible_proof(stop_kind):
    async def scenario():
        events = []

        async def emit(event):
            events.append(event)

        async def stop():
            if stop_kind == "timeout":
                await asyncio.Event().wait()
            return {"ok": False, "acked_at": None, "result": "-ERR unsupported"}

        actor = actor_for_audio(media=MediaCallbacks(
            noop, noop, noop, emit,
            request_downstream_stop=None if stop_kind == "missing" else stop,
        ))
        actor._playback.begin_phrase("old", "p", "Как настроение?")
        actor._active_generation = "old"
        await asyncio.wait_for(actor._interrupt_playback(flush=True), timeout=1)
        assert actor._playback.is_cancelled("old")
        assert actor._active_generation is None
        payload = next(e.payload for e in events if e.payload.get("stage") == "transport.cancel")
        assert payload.get("audible_stop_verified") is False
        assert not payload["downstream_ack"].get("ok")
        if stop_kind == "timeout":
            assert "TimeoutError" in payload["downstream_ack"]["error"]

    asyncio.run(scenario())


def test_echo_does_not_interrupt_and_clear_user_audio_still_reaches_stt():
    async def scenario():
        actor = actor_for_audio()
        actor._last_delivered_intent = "check_mood"
        actor._active_generation = "old"
        actor._playback.begin_phrase("old", "p", "Как настроение?")
        actor._on_bot_playback_started()
        captured = []

        async def capture(pcm, seq):
            captured.append(pcm)

        actor._handle_utterance = capture
        bot_audio, user_audio = tone(500), tone(200)
        for _ in range(20):
            actor._push_echo_downlink(bot_audio, 16000)
            await actor._feed_uplink_pcm(bot_audio)
        assert actor._active_generation == "old"
        assert not actor._collector.collecting
        for _ in range(25):
            await actor._feed_uplink_pcm(user_audio)
        assert actor._active_generation is None
        assert actor._turn_manager.phase == ConversationPhase.USER_SPEAKING
        for _ in range(50):
            await actor._feed_uplink_pcm(bytes(640))
            await asyncio.sleep(0)
        assert len(captured) == 1
        assert user_audio * 20 in captured[0]
        late = AudioEnvelope(call_id=actor.call_id, generation_id="old", phrase_id="p",
                             sequence=3, sample_rate=16000, pcm_s16le=bot_audio)
        assert not await actor._playback.enqueue_wait(late)

    asyncio.run(scenario())


def test_first_pcm_and_transport_start_are_measured_at_their_actual_boundaries():
    async def scenario():
        ready = asyncio.Event()
        release = asyncio.Event()
        sent = asyncio.Event()
        events = []

        async def emit(event):
            events.append(event)
            if event.event_type == "playback.started":
                sent.set()

        async def synthesize(*args, **kwargs):
            yield SimpleNamespace(pcm_s16le=tone(), sample_rate=16000)

        async def send(pcm):
            ready.set()
            await release.wait()

        actor = actor_for_audio(
            tts=SimpleNamespace(cancel=noop, synthesize=synthesize),
            media=MediaCallbacks(send, noop, noop, emit),
        )
        actor._render_generation = "gen"
        actor._hold_turn_finalize = True
        pump = asyncio.create_task(actor._playback_pump())
        speak = asyncio.create_task(actor._speak_phrase("Как настроение?", "gen"))
        try:
            await asyncio.wait_for(ready.wait(), timeout=1)
            assert "tts_first_pcm" in actor._tl().marks
            assert "playout" not in actor._tl().marks, "a planned playback is not transmitted PCM"
            release.set()
            await asyncio.wait_for(sent.wait(), timeout=1)
            assert actor._tl().marks["playout"] >= actor._tl().marks["tts_first_pcm"]
            assert len([e for e in events if e.payload.get("stage") == "tts.first_pcm"]) == 1
            assert next(e for e in events if e.event_type == "playback.started").payload[
                "generation_id"
            ] == "gen"
        finally:
            release.set()
            await actor._interrupt_playback(flush=True)
            pump.cancel()
            speak.cancel()
            await asyncio.gather(pump, speak, return_exceptions=True)

    asyncio.run(scenario())


def test_latency_report_reads_the_actual_stage_timeline_schema(tmp_path, monkeypatch, capsys):
    import json

    from tools.voice_lab.latency_histogram import main

    path = tmp_path / "call.jsonl"
    path.write_text(json.dumps({"type": "stage.timing", "payload": {
        "stage": "timeline", "seg_answer_to_playout_ms": 600,
    }}) + "\n")
    monkeypatch.setattr("sys.argv", ["latency_histogram", str(path)])
    assert main() == 0
    assert "p50=600ms" in capsys.readouterr().out


def test_final_only_stt_never_presents_an_empty_stub_as_realtime_recognition():
    from packages.contracts.providers import ProviderUnavailable
    from services.stt.http_provider import HttpSTTProvider

    async def scenario():
        with pytest.raises(ProviderUnavailable, match="final-only"):
            await HttpSTTProvider("http://unused.invalid").transcribe_partial(
                tone(), 16000, call_id="realtime-contract", partial_id="p1",
            )

    asyncio.run(scenario())
