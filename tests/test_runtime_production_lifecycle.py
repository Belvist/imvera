"""Runtime lifecycle regressions with a real SDK and controllable I/O boundaries."""

from __future__ import annotations

import asyncio
import threading
import time
from types import SimpleNamespace

import pytest

from packages.contracts.enums import AnswerJudgement, AsrQuality, DialogueAct
from packages.contracts.interpretation import TurnInterpretation
from packages.contracts.outbox import ActionOutboxStatus
from packages.contracts.providers import AudioChunk
from packages.contracts.runtime import RuntimeEventType
from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.interpretation import UserInterpretation
from packages.dialogue.session import CallSession
from packages.voice_runtime.audio import AudioEnvelope
from packages.voice_runtime.call_actor import (
    CallActor,
    MediaCallbacks,
    _UtteranceOutcome,
    build_call_actor,
)
from packages.voice_runtime.playback import PlaybackQueue
from packages.voice_runtime.wait_state import DialogueTimingProfile, WaitState

pytestmark = pytest.mark.dialogue_engine


async def noop(*args, **kwargs):
    return None


def make_actor(*, stt=None, tts=None, media=None):
    session = CallSession(call_id="production-lifecycle", family_id="family",
                          store=InMemoryCallRecordStore())
    session.start()
    return CallActor(
        call_id=session.state.call_id, family_id="family", session=session,
        stt=stt or SimpleNamespace(transcribe_final=noop),
        tts=tts or SimpleNamespace(cancel=noop), llm=SimpleNamespace(cancel_request=noop),
        media=media or MediaCallbacks(noop, noop, noop, noop),
    )


def test_unexpected_stt_result_failure_does_not_block_all_later_turns():
    async def scenario():
        events = []

        async def emit(event):
            events.append(event)

        async def invalid(*args, **kwargs):
            return SimpleNamespace(text="Хорошо.")  # malformed adapter response

        actor = make_actor(stt=SimpleNamespace(transcribe_final=invalid),
                           media=MediaCallbacks(noop, noop, noop, emit))
        actor._inflight_utterances.add(1)
        await actor._handle_utterance(b"\x00\x00" * 320, 1)
        assert actor._last_applied_utterance_seq == 1
        assert not actor._inflight_utterances
        assert any(event.event_type == RuntimeEventType.INTERPRETATION_FAILED for event in events)

        async def empty(*args, **kwargs):
            return SimpleNamespace(text="", asr_quality=AsrQuality.UNUSABLE,
                                   model_revision="fixture")

        actor.stt = SimpleNamespace(transcribe_final=empty)
        actor._inflight_utterances.add(2)
        await actor._handle_utterance(b"\x00\x00" * 320, 2)
        assert actor._last_applied_utterance_seq == 2
        assert not actor._inflight_utterances and not actor._utterance_outcomes

    asyncio.run(scenario())


def test_stop_cancels_timers_and_playback_and_finalizes_a_not_started_actor():
    async def scenario():
        actor = make_actor()
        actor._playback = PlaybackQueue(actor.call_id)
        timers = [asyncio.create_task(asyncio.sleep(60)) for _ in range(4)]
        (actor._wait_task, actor._engine_timer_task,
         actor._tts_slow_watch, actor._playback_task) = timers
        try:
            await actor.stop()
            assert all(task.done() for task in timers)
            assert actor.session.is_finalized()
            await actor.stop()  # repeated transport teardown must be harmless
        finally:
            for task in timers:
                task.cancel()
            await asyncio.gather(*timers, return_exceptions=True)

    asyncio.run(scenario())


def test_media_ready_after_stop_cannot_reopen_playback():
    async def scenario():
        prime = []

        async def prime_downlink():
            prime.append(True)

        actor = make_actor(media=MediaCallbacks(noop, noop, noop, noop,
                                               prime_downlink=prime_downlink))
        actor._stopped = True
        await actor.on_media_ready(16000, 640)
        assert actor._playback_task is None
        assert not prime and not actor._media_ready

    asyncio.run(scenario())


def test_late_transport_failure_does_not_fail_the_replacement_generation():
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()

        async def send(_pcm):
            entered.set()
            await release.wait()
            raise ConnectionError("old send completed with failure")

        actor = make_actor(media=MediaCallbacks(send, noop, noop, noop))
        actor._playback = PlaybackQueue(actor.call_id)
        actor._playback.begin_phrase("old", "p-old", "Старая фраза.")
        actor._active_generation = "old"
        await actor._playback.enqueue_wait(AudioEnvelope(
            actor.call_id, "old", "p-old", 0, 16000, b"\x01\x00" * 320))
        pump = asyncio.create_task(actor._playback_pump())
        try:
            await entered.wait()
            actor._playback.cancel_generation("old")
            actor._playback.begin_phrase("new", "p-new", "Новая фраза.")
            actor._active_generation = "new"
            release.set()
            await asyncio.sleep(0.03)
            ledger = actor._playback._ledger
            assert ledger.generation_id == "new"
            assert ledger.generation_outcome is None and not ledger.generation_done
        finally:
            pump.cancel()
            await asyncio.gather(pump, return_exceptions=True)

    asyncio.run(scenario())


def test_late_tts_error_cannot_fail_another_effect(monkeypatch):
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()

        async def synthesize(*args, **kwargs):
            entered.set()
            await release.wait()
            raise ConnectionError("old TTS response failed")
            yield AudioChunk(pcm_s16le=b"", sample_rate=16000, sequence=0)

        actor = make_actor(tts=SimpleNamespace(synthesize=synthesize, cancel=noop))
        actor._playback = PlaybackQueue(actor.call_id)
        actor._render_generation = "old"
        actor._pending_speak_effect_id = "fx-old"
        failed = []
        monkeypatch.setattr(actor.session, "handle_effect_failed",
                            lambda effect_id, **kwargs: failed.append(effect_id))
        phrase = asyncio.create_task(actor._speak_phrase("Старая фраза.", "old"))
        try:
            await entered.wait()
            actor._playback.cancel_generation("old")
            actor._playback.begin_phrase("new", "p-new", "Новая фраза.")
            actor._active_generation = actor._render_generation = "new"
            actor._pending_speak_effect_id = "fx-new"
            release.set()
            await asyncio.sleep(0.03)
            assert not failed, "A stale provider error must not fail the latest SDK effect"
        finally:
            phrase.cancel()
            if actor._tts_slow_watch:
                actor._tts_slow_watch.cancel()
            await asyncio.gather(phrase, return_exceptions=True)

    asyncio.run(scenario())


@pytest.mark.parametrize("suppress_cancel", [False, True])
def test_stt_uses_its_own_budget_and_enforces_an_ignored_adapter_deadline(suppress_cancel):
    async def scenario():
        observed = []
        cancelled = []
        release = asyncio.Event()
        events = []

        async def emit(event):
            events.append(event)

        async def ignores_deadline(*args, **kwargs):
            observed.append(kwargs["deadline"] - time.monotonic())
            try:
                await asyncio.sleep(0.08)
            except asyncio.CancelledError:
                cancelled.append(True)
                if not suppress_cancel:
                    raise
                await release.wait()
            return SimpleNamespace(text="Сильная боль.", asr_quality=AsrQuality.GOOD,
                                   model_revision="fixture")

        actor = make_actor(stt=SimpleNamespace(transcribe_final=ignores_deadline),
                           media=MediaCallbacks(noop, noop, noop, emit))
        actor.config.stt_deadline_s = 0.02
        actor._inflight_utterances.add(1)
        try:
            await asyncio.wait_for(actor._handle_utterance(b"\x00\x00" * 320, 1), 0.06)
            assert 0 < observed[0] <= 0.02
            assert cancelled and actor._last_applied_utterance_seq == 1
            assert not actor._inflight_utterances
        finally:
            release.set()
            await asyncio.gather(*actor._owned_tasks, return_exceptions=True)
        assert not actor.session._engine.state.issue_episodes
        assert not any(event.event_type == RuntimeEventType.STT_FINAL for event in events)

    asyncio.run(scenario())


def test_build_actor_uses_declared_profile_deadlines(monkeypatch):
    from packages.voice_runtime import profile

    base = dict(profile.load_profile())
    base["limits"] = dict(base.get("limits", {}), stt_deadline_s=3.0,
                          llm_deadline_s=4.0, tts_deadline_s=5.0)
    monkeypatch.setattr(profile, "load_profile", lambda: base)
    actor = build_call_actor(
        call_id="profile-deadlines", family_id="family", elder_name="Анна",
        store=InMemoryCallRecordStore(), media=MediaCallbacks(noop, noop, noop, noop),
        stt_url="http://stt", tts_url="http://tts", llm_url="http://llm",
    )
    assert (actor.config.stt_deadline_s, actor.config.llm_deadline_s,
            actor.config.tts_deadline_s) == (3.0, 4.0, 5.0)


def test_stop_cancels_owned_stt_and_rejects_its_late_result():
    async def scenario():
        entered = asyncio.Event()
        events = []

        async def emit(event):
            events.append(event)

        async def slow(*args, **kwargs):
            entered.set()
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                # A remote inference can complete after its caller cancels.
                return SimpleNamespace(text="Сильная боль.", asr_quality=AsrQuality.GOOD,
                                       model_revision="fixture")

        actor = make_actor(stt=SimpleNamespace(transcribe_final=slow),
                           media=MediaCallbacks(noop, noop, noop, emit))
        before_revision = actor.session._engine.revision
        actor._inflight_utterances.add(1)
        recognition = actor._spawn_owned_task(actor._handle_utterance(b"\x00\x00" * 320, 1))
        await entered.wait()
        await actor.stop()
        assert recognition.done() and not actor._owned_tasks
        assert not actor._inflight_utterances and not actor._utterance_outcomes
        assert actor.session.is_finalized()
        assert actor.session._engine.revision == before_revision
        assert not any(event.event_type == RuntimeEventType.STT_FINAL for event in events)

    asyncio.run(scenario())


def test_unresponsive_llm_cancel_is_bounded_and_old_outbox_cannot_clear_new_identity():
    async def scenario():
        entered = asyncio.Event()

        async def cancel(_rid):
            entered.set()
            await asyncio.sleep(60)

        actor = make_actor()
        old_id = next(iter(actor.session._playout_meta))
        actor._outbox_action_id = old_id
        actor._active_llm_request_id = "old-request"
        actor.llm = SimpleNamespace(cancel_request=cancel)
        interrupt = asyncio.create_task(actor._interrupt_playback(flush=True))
        await entered.wait()
        actor._outbox_action_id = "replacement-action"
        await asyncio.wait_for(interrupt, timeout=0.6)
        assert actor._active_llm_request_id is None
        assert actor._outbox_action_id == "replacement-action"
        record = actor.session.transitions.get_outbox_record(actor.call_id, old_id)
        assert record.status == ActionOutboxStatus.CANCELLED

    asyncio.run(scenario())


def test_interrupt_starts_provider_cleanup_on_the_first_event_loop_turn():
    async def scenario():
        started = []

        async def cancel(generation):
            started.append(("tts.cancel", generation))
            await asyncio.sleep(60)

        async def flush():
            started.append(("transport.flush", None))
            await asyncio.sleep(60)

        actor = make_actor(tts=SimpleNamespace(cancel=cancel),
                           media=MediaCallbacks(noop, flush, noop, noop))
        actor._playback = PlaybackQueue(actor.call_id)
        actor._playback.begin_phrase("interrupted", "p", "Фраза.")
        actor._active_generation = "interrupted"
        await actor._interrupt_playback(flush=True)
        assert actor._active_generation is None
        await asyncio.sleep(0)
        assert started == [("tts.cancel", "interrupted"), ("transport.flush", None)]
        await asyncio.wait_for(asyncio.gather(*actor._owned_tasks, return_exceptions=True), 0.5)
        assert not actor._owned_tasks

    asyncio.run(scenario())


def test_disconnect_waits_for_a_sdk_mutation_already_running_in_a_thread(monkeypatch):
    async def scenario():
        entered, release = threading.Event(), threading.Event()
        actor = make_actor()
        session = actor.session
        order = []
        original_turn, original_finalize = session.handle_user_text, session.finalize_disconnect

        def slow_turn(*args, **kwargs):
            entered.set()
            assert release.wait(2)
            rich = session._engine.build_rich_turn("Голова болит.", utterance_id="u-1")
            result = original_turn("Голова болит.", utterance_id="u-1", rich_turn=rich)
            order.append("turn")
            return result

        def finalize():
            order.append("finalize")
            original_finalize()

        monkeypatch.setattr(session, "handle_user_text", slow_turn)
        monkeypatch.setattr(session, "finalize_disconnect", finalize)
        actor._inflight_utterances.add(1)
        contract = TurnInterpretation(
            call_id=actor.call_id, turn_id=1, raw_text="Голова болит.",
            dialogue_act=DialogueAct.ANSWER, judgement=AnswerJudgement.VALID,
            state_version=session.state.state_version,
        )
        applying = asyncio.create_task(actor._submit_utterance_outcome(_UtteranceOutcome(
            utterance_seq=1, utterance_id="u-1", ok=True, text="Голова болит.",
            interp=UserInterpretation(judgement=AnswerJudgement.VALID,
                                      dialogue_act=DialogueAct.ANSWER),
            legacy_contract=contract,
        )))
        try:
            assert await asyncio.to_thread(entered.wait, 1)
            actor._stopped = actor._transport_closed = True
            applying.cancel()
            disconnecting = asyncio.create_task(actor._finalize_disconnect())
            await asyncio.sleep(0.02)
            assert not disconnecting.done() and not order
            applying.cancel()  # a second transport cleanup must preserve the fence
            await asyncio.sleep(0.02)
            assert not disconnecting.done() and not order
            release.set()
            await asyncio.gather(applying, return_exceptions=True)
            await disconnecting
            assert order == ["turn", "finalize"]
            assert session.is_finalized()
        finally:
            release.set()
            await asyncio.gather(applying, return_exceptions=True)

    asyncio.run(scenario())


@pytest.mark.parametrize("timer_kind", ["engine", "answer_wait"])
def test_timer_mutation_cannot_run_after_disconnect_even_under_repeated_cancel(monkeypatch,
                                                                             timer_kind):
    async def scenario():
        entered, release = threading.Event(), threading.Event()
        actor = make_actor()
        session = actor.session
        order = []
        original_wait, original_finalize = session.handle_wait_expired, session.finalize_disconnect

        def slow_wait(*args, **kwargs):
            entered.set()
            assert release.wait(2)
            result = original_wait(*args, **kwargs)
            order.append("timer")
            return result

        def finalize():
            order.append("finalize")
            original_finalize()

        monkeypatch.setattr(session, "handle_wait_expired", slow_wait)
        monkeypatch.setattr(session, "finalize_disconnect", finalize)
        if timer_kind == "engine":
            actor._engine_timer_revision = session._engine.revision
            operation = actor._on_engine_timer_expired("timer", actor._engine_timer_revision)
        else:
            wait = WaitState.start_answer_wait(
                goal_id="wellness", question_id="q", control_epoch=actor._control_epoch,
                profile=DialogueTimingProfile(answer_wait_ms=0), now_mono=actor._monotonic(),
            )
            actor._wait_state = wait
            operation = actor._on_wait_deadline(wait.wait_id, actor._control_epoch)
        timer = actor._spawn_owned_task(operation)
        try:
            assert await asyncio.to_thread(entered.wait, 1)
            actor._stopped = actor._transport_closed = True
            timer.cancel()
            disconnect = asyncio.create_task(actor._finalize_disconnect())
            await asyncio.sleep(0.02)
            timer.cancel()
            await asyncio.sleep(0.02)
            assert not disconnect.done() and not order
            release.set()
            await asyncio.gather(timer, return_exceptions=True)
            await disconnect
            assert order == ["timer", "finalize"]
            assert session.is_finalized() and not actor._owned_tasks
        finally:
            release.set()
            await asyncio.gather(timer, return_exceptions=True)

    asyncio.run(scenario())


@pytest.mark.parametrize("suppress_cancel", [False, True])
def test_tts_adapter_that_ignores_deadline_cannot_hold_delivery_forever(monkeypatch,
                                                                      suppress_cancel):
    async def scenario():
        cancelled = []
        release = asyncio.Event()

        async def synthesize(*args, **kwargs):
            try:
                await asyncio.sleep(0.08)
            except asyncio.CancelledError:
                cancelled.append(True)
                if not suppress_cancel:
                    raise
                await release.wait()
            yield AudioChunk(pcm_s16le=b"\x01\x00" * 320, sample_rate=16000, sequence=0)

        actor = make_actor(tts=SimpleNamespace(synthesize=synthesize, cancel=noop))
        actor.config.tts_deadline_s = 0.02
        actor._playback = PlaybackQueue(actor.call_id)
        actor._render_generation = "slow-generation"
        actor._pending_speak_effect_id = "fx-slow"
        failed = []
        monkeypatch.setattr(actor.session, "handle_effect_failed",
                            lambda effect_id, **kwargs: failed.append(effect_id))
        try:
            await asyncio.wait_for(actor._speak_phrase("Фраза.", "slow-generation"), 0.06)
            assert cancelled and failed == ["fx-slow"]
            assert actor._active_generation is None
            assert actor._playback.is_cancelled("slow-generation")
        finally:
            release.set()
            await asyncio.gather(*actor._owned_tasks, return_exceptions=True)
        assert not actor._playback.pending_frames
        assert actor._playback._ledger.generated_samples == 0

    asyncio.run(scenario())
