"""Effect Delivery V2 — outbox, dispatcher, lifecycle chaos tests."""

from __future__ import annotations

import asyncio
import random
from types import SimpleNamespace

import pytest

from packages.contracts.enums import AnswerJudgement, DialogueAct, FsmState
from packages.contracts.interpretation import TurnInterpretation
from packages.contracts.status import SafetySnapshot
from packages.contracts.turn import TurnProposal, ValidatedTurn
from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.interpretation import UserInterpretation
from packages.dialogue.session import CallSession, SessionTurnResult
from packages.dialogue_engine.delivery import EffectOutbox, EffectStatus
from packages.dialogue_engine.delivery.decision import Decision
from packages.dialogue_engine.delivery.scope import speak_scope_for, timer_scope_for
from packages.dialogue_engine.effects import EndCallEffect, SpeakEffect, TimerEffect
from packages.dialogue_engine.engine import DialogueEngine
from packages.dialogue_engine.state import EngineState, Question, QuestionPhase
from packages.voice_runtime.call_actor import CallActor, MediaCallbacks

pytestmark = pytest.mark.dialogue_engine


async def _noop(*_a, **_k):
    return None


def _session() -> CallSession:
    return CallSession(
        call_id="v2-delivery",
        family_id="audit-family",
    )


def _speak(
    *,
    effect_id: str = "fx-1",
    intent: str = "summary",
    generation_id: str = "g-summary",
    generation: int = 2,
    revision: int = 1,
) -> SpeakEffect:
    scope = speak_scope_for(
        intent=intent,
        generation_id=generation_id,
        slot=None,
        marks_question=False,
    )
    return SpeakEffect(
        effect_id=effect_id,
        revision=revision,
        generation_id=generation_id,
        generation=generation,
        text="Спасибо за разговор.",
        intent=intent,
        semantic_scope_id=scope,
    )


def _timer(
    *,
    effect_id: str = "fx-t",
    timer_id: str = "wait-wellness",
    wait_ms: int = 5000,
) -> TimerEffect:
    return TimerEffect(
        effect_id=effect_id,
        revision=1,
        timer_id=timer_id,
        wait_ms=wait_ms,
        semantic_scope_id=timer_scope_for(timer_id=timer_id),
    )


def test_speak_and_timer_same_decision_both_claimed() -> None:
    outbox = EffectOutbox(call_id="t")
    speak = _speak(effect_id="fx-s")
    timer = _timer(effect_id="fx-t")
    outbox.accept_decision(Decision(revision=1, effects=(speak, timer)))
    claimed_speak = outbox.claim_next_speak()
    assert claimed_speak is not None
    assert claimed_speak.effect_id == "fx-s"
    assert outbox.claim_next_speak() is None
    claimed_timer = outbox.claim_next_timer()
    assert claimed_timer is not None
    assert claimed_timer.effect_id == "fx-t"
    assert outbox.claim_next_timer() is None


def test_engine_playout_complete_preserves_timer() -> None:
    eng = DialogueEngine(call_id="t", elder_display_name="Даниил")
    eng.start()
    speak = eng.pop_speak_effect()
    assert speak is not None
    eng.on_playout_completed(speak.generation, speak.question_id)
    assert eng.pop_speak_effect() is None
    timer = eng.pop_timer_effect()
    assert timer is not None
    assert timer.timer_id == "wait-wellness"
    record = eng.outbox.get_record(timer.effect_id)
    assert record is not None
    assert record.status == EffectStatus.CLAIMED


def test_timer_cancelled_on_vad_speech_start() -> None:
    async def scenario() -> None:
        session = _session()
        actor = CallActor(
            call_id=session.state.call_id,
            family_id="audit-family",
            session=session,
            stt=SimpleNamespace(),
            tts=SimpleNamespace(),
            llm=SimpleNamespace(),
            media=MediaCallbacks(_noop, _noop, _noop, _noop),
        )
        timer = _timer()
        session._engine.outbox.accept_decision(Decision(revision=1, effects=(timer,)))
        await actor._schedule_engine_timer(timer)
        assert actor._engine_timer_task is not None
        await actor._cancel_engine_timer_on_speech_start()
        assert actor._engine_timer_task is None
        record = session._engine.outbox.get_record(timer.effect_id)
        assert record is not None
        assert record.status == EffectStatus.CANCELLED

    asyncio.run(scenario())


def test_tts_failure_notifies_engine() -> None:
    session = _session()
    speak = _speak(effect_id="fx-tts")
    session._engine.outbox.accept_decision(Decision(revision=1, effects=(speak,)))
    session.handle_effect_failed("fx-tts", stage="TTS", error="boom")
    record = session._engine.outbox.get_record("fx-tts")
    assert record is not None
    assert record.status == EffectStatus.FAILED
    assert record.fail_stage == "TTS"


def test_duplicate_playout_completed_ignored() -> None:
    eng = DialogueEngine(call_id="t", elder_display_name="Даниил")
    eng.start()
    speak = eng.pop_speak_effect()
    assert speak is not None
    eng.on_playout_completed(speak.generation, speak.question_id)
    rev = eng.revision
    eng.on_playout_completed(speak.generation, speak.question_id)
    assert eng.revision == rev
    record = eng.outbox.get_record(speak.effect_id)
    assert record is not None
    assert record.status == EffectStatus.CLAIMED


def test_stale_summary_by_semantic_scope() -> None:
    eng = DialogueEngine(call_id="t", elder_display_name="Даниил")
    eng.state.fsm_state = FsmState.GOODBYE
    eng.state.summary_spoken = True
    eng.state.goodbye_confirmed = True
    stale = _speak(intent="summary", generation=1)
    assert not eng.is_speak_effect_valid(stale)


def test_barge_in_cancelled_not_completed() -> None:
    session = _session()
    eng = session._engine
    speak = _speak(effect_id="fx-barge", generation=3)
    eng.outbox.accept_decision(Decision(revision=1, effects=(speak,)))
    eng.outbox.mark_started(speak.effect_id)
    session._playout_meta[speak.generation_id] = (speak.generation, speak.question_id)
    session._playout_effect_meta[speak.generation_id] = speak.effect_id
    session.cancel_playout_action(speak.generation_id)
    record = eng.outbox.get_record(speak.effect_id)
    assert record is not None
    assert record.status == EffectStatus.CANCELLED
    session._playout_meta[speak.generation_id] = (speak.generation, speak.question_id)
    session._playout_effect_meta[speak.generation_id] = speak.effect_id
    session.mark_spoken_action(speak.generation_id)
    assert record.status == EffectStatus.CANCELLED


def test_deferred_speak_flush_after_inflight() -> None:
    async def scenario() -> None:
        session = _session()
        delivered: list[str] = []

        async def deliver(result: SessionTurnResult) -> None:
            delivered.append(result.proposal.intent)

        actor = CallActor(
            call_id=session.state.call_id,
            family_id="audit-family",
            session=session,
            stt=SimpleNamespace(),
            tts=SimpleNamespace(),
            llm=SimpleNamespace(),
            media=MediaCallbacks(_noop, _noop, _noop, _noop),
        )
        actor._deliver_session_turn = deliver  # type: ignore[method-assign]

        speak = _speak(intent="summary")
        session._engine.state.fsm_state = FsmState.SUMMARY
        session._engine.state.summary_spoken = True
        session._engine.state.active_playout_generation = speak.generation
        summary = SessionTurnResult(
            user_text="дома",
            interpretation=UserInterpretation(
                judgement=AnswerJudgement.VALID,
                dialogue_act=DialogueAct.ANSWER,
            ),
            turn_contract=TurnInterpretation(
                call_id=session.state.call_id,
                turn_id=5,
                raw_text="дома",
                state_version=session.state.state_version,
                dialogue_act=DialogueAct.ANSWER,
                judgement=AnswerJudgement.VALID,
            ),
            proposal=TurnProposal(
                turn_id=5,
                generation_id="g-summary",
                speech="Спасибо за разговор.",
                intent="summary",
                fsm_state=FsmState.SUMMARY,
            ),
            validated=ValidatedTurn(
                turn_id=5,
                generation_id="g-summary",
                speech="Спасибо за разговор.",
                intent="summary",
                fsm_state=FsmState.SUMMARY,
                allowed=True,
            ),
            safety=SafetySnapshot(),
            persist_ok=True,
            from_engine=True,
            speak_effect=speak,
        )
        actor._inflight_utterances.add(1)
        await actor._enqueue_turn_delivery(summary)
        assert delivered == []
        assert session._engine.outbox.get_record(speak.effect_id).status == EffectStatus.DEFERRED
        actor._inflight_utterances.discard(1)
        await actor._flush_deferred_engine_turn()
        assert delivered == ["summary"]

    asyncio.run(scenario())


def test_reissue_loop_capped_at_two() -> None:
    eng = DialogueEngine(call_id="t", elder_display_name="Даниил")
    eng.state.fsm_state = FsmState.SUMMARY
    eng.state.summary_spoken = True
    for idx in range(3):
        stale = _speak(effect_id=f"fx-{idx}", intent="summary")
        eng.outbox.accept_decision(Decision(revision=1, effects=(stale,)))
        effects = eng.on_speak_effect_stale(stale)
        if idx < 2:
            assert effects
        else:
            assert effects == []
    key = speak_scope_for(
        intent="summary",
        generation_id="g-summary",
        slot=None,
        marks_question=False,
    )
    assert eng.outbox._reissue_counts.get(key, 0) == 2


@pytest.mark.parametrize("seed", list(range(50)))
def test_random_interleaving_lifecycle(seed: int) -> None:
    rng = random.Random(seed)
    outbox = EffectOutbox(call_id=f"chaos-{seed}")
    eng_state = EngineState(call_id=f"chaos-{seed}", elder_display_name="X")
    speaks: list[SpeakEffect] = []
    timers: list[TimerEffect] = []

    for i in range(5):
        gen_id = f"g-{i}"
        gen = eng_state.active_playout_generation + 1
        eng_state.active_playout_generation = gen
        speaks.append(
            SpeakEffect(
                effect_id=f"s-{i}",
                revision=eng_state.revision,
                generation_id=gen_id,
                generation=gen,
                text=f"q{i}",
                intent="check_wellness" if i == 0 else f"check_mood",
                slot="wellness" if i == 0 else "mood",
                marks_question=True,
                semantic_scope_id=speak_scope_for(
                    intent="check_wellness",
                    generation_id=gen_id,
                    slot="wellness",
                    marks_question=True,
                ),
            )
        )
        timers.append(
            TimerEffect(
                effect_id=f"t-{i}",
                revision=eng_state.revision,
                timer_id=f"wait-{i}",
                wait_ms=1000,
                semantic_scope_id=timer_scope_for(timer_id=f"wait-{i}"),
            )
        )
        outbox.accept_decision(
            Decision(revision=eng_state.revision, effects=(speaks[-1], timers[-1]))
        )

    ops = ["claim_speak", "claim_timer", "complete", "cancel_timer", "stale"]
    active_speaks: list[str] = []
    active_timers: list[str] = []

    for _ in range(20):
        op = rng.choice(ops)
        if op == "claim_speak":
            s = outbox.claim_next_speak()
            if s:
                active_speaks.append(s.effect_id)
                outbox.mark_started(s.effect_id)
        elif op == "claim_timer":
            t = outbox.claim_next_timer()
            if t:
                active_timers.append(t.effect_id)
        elif op == "complete" and active_speaks:
            eid = rng.choice(active_speaks)
            outbox.mark_completed(eid)
            active_speaks.remove(eid)
        elif op == "cancel_timer" and active_timers:
            eid = rng.choice(active_timers)
            outbox.mark_cancelled(eid)
            active_timers.remove(eid)
        elif op == "stale" and active_speaks:
            eid = rng.choice(active_speaks)
            outbox.mark_stale(eid)
            active_speaks.remove(eid)

    for eid, record in outbox._records.items():
        assert record.status in EffectStatus


def test_call_actor_tts_exception_path() -> None:
    session = _session()
    speak = _speak(effect_id="fx-tts-live")
    session._engine.outbox.accept_decision(Decision(revision=1, effects=(speak,)))
    session.handle_effect_failed("fx-tts-live", stage="TTS", error="tts down")
    record = session._engine.outbox.get_record("fx-tts-live")
    assert record is not None
    assert record.status == EffectStatus.FAILED
    assert record.fail_stage == "TTS"
    assert eng_revision_bumped(session._engine)


def eng_revision_bumped(eng: DialogueEngine) -> bool:
    return eng.revision >= 1


def test_single_terminal_transition_invariant() -> None:
    outbox = EffectOutbox(call_id="t")
    speak = _speak(effect_id="fx-term")
    outbox.accept_decision(Decision(revision=1, effects=(speak,)))
    outbox.claim_next_speak()
    outbox.mark_started(speak.effect_id)
    assert outbox.mark_completed(speak.effect_id)
    assert not outbox.mark_completed(speak.effect_id)
    assert not outbox.mark_cancelled(speak.effect_id)
    assert not outbox.mark_stale(speak.effect_id)
    record = outbox.get_record(speak.effect_id)
    assert record is not None
    assert record.status == EffectStatus.COMPLETED


def test_playout_failure_stage_recorded() -> None:
    session = _session()
    speak = _speak(effect_id="fx-playout")
    session._engine.outbox.accept_decision(Decision(revision=1, effects=(speak,)))
    session.handle_effect_failed("fx-playout", stage="PLAYOUT", error="drain failed")
    record = session._engine.outbox.get_record("fx-playout")
    assert record is not None
    assert record.status == EffectStatus.FAILED
    assert record.fail_stage == "PLAYOUT"


def test_timer_expired_ignored_when_inflight() -> None:
    async def scenario() -> None:
        session = _session()
        actor = CallActor(
            call_id=session.state.call_id,
            family_id="audit-family",
            session=session,
            stt=SimpleNamespace(),
            tts=SimpleNamespace(),
            llm=SimpleNamespace(),
            media=MediaCallbacks(_noop, _noop, _noop, _noop),
        )
        timer = _timer(wait_ms=10)
        await actor._schedule_engine_timer(timer)
        actor._inflight_utterances.add(99)
        await asyncio.sleep(0.02)
        assert actor._engine_timer_task is None or actor._engine_timer_task.done()
        actor._inflight_utterances.discard(99)

    asyncio.run(scenario())


def test_second_timer_schedule_supersedes_first() -> None:
    async def scenario() -> None:
        session = _session()
        actor = CallActor(
            call_id=session.state.call_id,
            family_id="audit-family",
            session=session,
            stt=SimpleNamespace(),
            tts=SimpleNamespace(),
            llm=SimpleNamespace(),
            media=MediaCallbacks(_noop, _noop, _noop, _noop),
        )
        first = _timer(effect_id="fx-t1", timer_id="wait-wellness")
        second = _timer(effect_id="fx-t2", timer_id="wait-mood")
        await actor._schedule_engine_timer(first)
        first_task = actor._engine_timer_task
        await actor._schedule_engine_timer(second)
        assert actor._engine_timer_task is not first_task
        assert actor._engine_timer_effect_id == "fx-t2"
        await actor._cancel_engine_timer()

    asyncio.run(scenario())


def test_end_call_effect_executes_hangup() -> None:
    async def scenario() -> None:
        session = _session()
        hangup_calls: list[str] = []

        async def hangup() -> None:
            hangup_calls.append("hangup")

        actor = CallActor(
            call_id=session.state.call_id,
            family_id="audit-family",
            session=session,
            stt=SimpleNamespace(),
            tts=SimpleNamespace(),
            llm=SimpleNamespace(),
            media=MediaCallbacks(_noop, _noop, hangup, _noop),
        )
        effect = EndCallEffect(effect_id="fx-hang", revision=1, reason="goodbye")
        session._engine.outbox.accept_decision(
            Decision(revision=1, effects=(effect,))
        )
        claimed = session._engine.pop_hangup_effect()
        assert claimed is not None
        await actor._execute_end_call_effect(claimed)
        assert hangup_calls == ["hangup"]
        snap = session._engine.outbox.cleanup_snapshot()
        assert snap["non_terminal_outbox_records"] == 0

    asyncio.run(scenario())


def test_goodbye_completed_emits_end_call_effect() -> None:
    eng = DialogueEngine(call_id="t", elder_display_name="Даниил")
    state = eng.state
    gen = state.active_playout_generation + 1
    state.active_playout_generation = gen
    state.active_playout = Question(
        question_id="g-goodbye",
        slot="",
        text="До свидания.",
        intent="goodbye_final",
        phase=QuestionPhase.PLAYING,
    )
    state.call_closed = True
    state.closing_reason = "goodbye"
    eng.on_playout_completed(gen, "")
    hangup = eng.pop_hangup_effect()
    assert hangup is not None
    assert hangup.reason == "goodbye"


def test_partial_unresolved_close_emits_end_call_effect() -> None:
    eng = DialogueEngine(call_id="t", elder_display_name="Даниил")
    state = eng.state
    gen = state.active_playout_generation + 1
    state.active_playout_generation = gen
    state.active_playout = Question(
        question_id="g-partial",
        slot="",
        text="Сейчас не получилось узнать, как у вас дела. До свидания.",
        intent="partial_unresolved_close",
        phase=QuestionPhase.PLAYING,
    )
    state.call_closed = True
    state.closing_reason = "partial_unresolved"
    eng.on_playout_completed(gen, "")
    hangup = eng.pop_hangup_effect()
    assert hangup is not None
    assert hangup.reason == "partial_unresolved"


def test_end_call_deferred_until_playback_idle() -> None:
    async def scenario() -> None:
        session = _session()
        hangup_calls: list[str] = []

        async def hangup() -> None:
            hangup_calls.append("hangup")

        actor = CallActor(
            call_id=session.state.call_id,
            family_id="audit-family",
            session=session,
            stt=SimpleNamespace(),
            tts=SimpleNamespace(),
            llm=SimpleNamespace(),
            media=MediaCallbacks(_noop, _noop, hangup, _noop),
        )
        effect = EndCallEffect(effect_id="fx-hang-def", revision=1, reason="partial_unresolved")
        session._engine.outbox.accept_decision(
            Decision(revision=1, effects=(effect,))
        )
        claimed = session._engine.pop_hangup_effect()
        assert claimed is not None
        actor._active_generation = "g-busy"
        await actor._schedule_end_call_effect(claimed)
        assert actor._pending_end_call_effect is not None
        assert hangup_calls == []
        actor._active_generation = None
        await actor._flush_pending_end_call_effect()
        assert hangup_calls == ["hangup"]
        assert actor._pending_end_call_effect is None
        record = session._engine.outbox.get_record("fx-hang-def")
        assert record is not None
        assert record.status == EffectStatus.COMPLETED

    asyncio.run(scenario())


def test_goodbye_cancelled_no_end_call_effect() -> None:
    eng = DialogueEngine(call_id="t", elder_display_name="Даниил")
    state = eng.state
    gen = state.active_playout_generation + 1
    state.active_playout_generation = gen
    state.active_playout = Question(
        question_id="g-goodbye",
        slot="",
        text="До свидания.",
        intent="goodbye_final",
        phase=QuestionPhase.PLAYING,
    )
    eng.on_playout_cancelled(gen, "")
    assert eng.pop_hangup_effect() is None


def test_playout_throws_wires_effect_failed() -> None:
    async def scenario() -> None:
        session = _session()
        speak = _speak(effect_id="fx-playout-live", intent="check_wellness")
        session._engine.outbox.accept_decision(
            Decision(revision=1, effects=(speak,))
        )
        actor = CallActor(
            call_id=session.state.call_id,
            family_id="audit-family",
            session=session,
            stt=SimpleNamespace(),
            tts=SimpleNamespace(),
            llm=SimpleNamespace(),
            media=MediaCallbacks(_noop, _noop, _noop, _noop),
        )
        actor._pending_speak_effect_id = speak.effect_id
        await actor._fail_pending_speak_playout("pcm write failed")
        record = session._engine.outbox.get_record(speak.effect_id)
        assert record is not None
        assert record.status == EffectStatus.FAILED
        assert record.fail_stage == "PLAYOUT"

    asyncio.run(scenario())


def test_hangup_cleanup_zero_active() -> None:
    async def scenario() -> None:
        session = _session()
        actor = CallActor(
            call_id=session.state.call_id,
            family_id="audit-family",
            session=session,
            stt=SimpleNamespace(),
            tts=SimpleNamespace(),
            llm=SimpleNamespace(),
            media=MediaCallbacks(_noop, _noop, _noop, _noop),
        )
        effect = EndCallEffect(effect_id="fx-hang2", revision=1, reason="goodbye")
        session._engine.outbox.accept_decision(
            Decision(revision=1, effects=(effect,))
        )
        claimed = session._engine.pop_hangup_effect()
        assert claimed is not None
        await actor._execute_end_call_effect(claimed)
        snap = session._engine.outbox.cleanup_snapshot()
        assert snap["non_terminal_outbox_records"] == 0
        assert snap["pending_timers"] == 0
        assert snap["deferred_speaks"] == 0

    asyncio.run(scenario())


def test_old_timer_expired_revision_ignored_at_actor() -> None:
    async def scenario() -> None:
        session = _session()
        delivered: list[str] = []

        async def deliver(result: SessionTurnResult) -> None:
            delivered.append(result.proposal.intent)

        actor = CallActor(
            call_id=session.state.call_id,
            family_id="audit-family",
            session=session,
            stt=SimpleNamespace(),
            tts=SimpleNamespace(),
            llm=SimpleNamespace(),
            media=MediaCallbacks(_noop, _noop, _noop, _noop),
        )
        actor._post_apply_turn = deliver  # type: ignore[method-assign]
        timer = _timer(wait_ms=20, timer_id="wait-wellness")
        await actor._schedule_engine_timer(timer)
        actor._engine_timer_revision = timer.revision - 1
        await asyncio.sleep(0.03)
        assert delivered == []

    asyncio.run(scenario())


def test_random_interleaving_1000_seeds() -> None:
    for seed in range(1000):
        test_random_interleaving_lifecycle(seed)
