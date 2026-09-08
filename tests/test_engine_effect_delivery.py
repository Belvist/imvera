"""Stale-safe effect delivery + engine-owned wait/timer regressions."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from packages.contracts.enums import AnswerJudgement, DialogueAct, FsmState, SlotStatus
from packages.contracts.interpretation import TurnInterpretation
from packages.contracts.status import SafetySnapshot
from packages.contracts.turn import TurnProposal, ValidatedTurn
from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.interpretation import UserInterpretation
from packages.dialogue.planner import Planner
from packages.dialogue.session import CallSession, SessionTurnResult
from packages.dialogue_engine.effects import SpeakEffect, TimerEffect
from packages.dialogue_engine.engine import DialogueEngine
from packages.dialogue_engine.events import (
    CallStarted,
    PlayoutCancelled,
    PlayoutCompleted,
    SpeakEffectStale,
    TimerExpired,
)
from packages.dialogue_engine.reducer import reduce
from packages.dialogue_engine.scenario_runner import ScenarioRunner
from packages.dialogue_engine.state import EngineState
from packages.voice_runtime.call_actor import CallActor, MediaCallbacks

pytestmark = pytest.mark.dialogue_engine


async def _noop(*_a, **_k):
    return None


def _session() -> CallSession:
    return CallSession(
        call_id="delivery-test",
        family_id="audit-family",
        store=InMemoryCallRecordStore(),
    )


def _speak(
    eng: DialogueEngine,
    *,
    effect_id: str = "fx-1",
    intent: str = "summary",
    text: str = "Спасибо за разговор.",
    revision: int | None = None,
    generation: int | None = None,
) -> SpeakEffect:
    revision = revision if revision is not None else eng.revision
    generation = generation if generation is not None else eng.state.active_playout_generation
    return SpeakEffect(
        effect_id=effect_id,
        revision=revision,
        generation_id="g-summary",
        generation=generation,
        text=text,
        intent=intent,
    )


def test_stale_summary_reemitted_after_revision_bump() -> None:
    state = EngineState(call_id="t", elder_display_name="Даниил")
    state.fsm_state = FsmState.SUMMARY
    state.summary_spoken = True
    state.bump_revision()
    stale = SpeakEffect(
        effect_id="fx-old",
        revision=state.revision - 1,
        generation_id="g-old",
        generation=1,
        text="Спасибо за разговор.",
        intent="summary",
    )
    state.deferred_speak = stale
    state, effects = reduce(
        state,
        SpeakEffectStale(
            effect_id=stale.effect_id,
            intent=stale.intent,
            generation=stale.generation,
            revision=stale.revision,
        ),
    )
    assert effects
    assert effects[0].intent == "summary"
    assert effects[0].revision == state.revision


def test_stale_summary_cannot_play_when_invalid() -> None:
    eng = DialogueEngine(call_id="t", elder_display_name="Даниил")
    eff = _speak(eng, revision=eng.revision - 1, generation=0)
    assert not eng.is_speak_effect_valid(eff)


def test_valid_deferred_summary_plays_once() -> None:
    async def scenario() -> None:
        session = _session()
        assert session._engine is not None
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

        speak = _speak(session._engine, intent="summary")
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
        session._engine.state.fsm_state = FsmState.SUMMARY
        session._engine.state.summary_spoken = True
        session._engine.state.active_playout_generation = speak.generation
        actor._inflight_utterances.add(1)
        await actor._enqueue_turn_delivery(summary)
        assert delivered == []
        actor._inflight_utterances.discard(1)
        await actor._flush_deferred_engine_turn()
        assert delivered == ["summary"]

    asyncio.run(scenario())


def test_goodbye_not_lost_on_stale_reemit() -> None:
    state = EngineState(call_id="t", elder_display_name="Даниил")
    state.call_closed = True
    state.goodbye_confirmed = True
    state.bump_revision()
    stale = SpeakEffect(
        effect_id="fx-gb",
        revision=state.revision - 1,
        generation_id="g-gb",
        generation=2,
        text="До свидания. Хорошего дня.",
        intent="goodbye_final",
    )
    state, effects = reduce(
        state,
        SpeakEffectStale(
            effect_id=stale.effect_id,
            intent=stale.intent,
            generation=stale.generation,
            revision=stale.revision,
        ),
    )
    assert effects
    assert effects[0].intent == "goodbye_final"


def test_playout_completed_exactly_once() -> None:
    eng = DialogueEngine(call_id="t", elder_display_name="Даниил")
    eng.start()
    speak = eng.pop_speak_effect()
    assert speak is not None
    eng.on_playout_completed(speak.generation, speak.question_id)
    before = eng.revision
    eng.on_playout_completed(speak.generation, speak.question_id)
    assert eng.revision == before


def test_cancelled_playout_not_delivered() -> None:
    state = EngineState(call_id="t", elder_display_name="Даниил")
    state, effects = reduce(state, CallStarted())
    speak = effects[0]
    goal = state.ensure_goal("wellness")
    state, _ = reduce(
        state,
        PlayoutCancelled(generation=speak.generation, question_id=speak.question_id),
    )
    assert goal.delivered_attempts == 0
    assert goal.reserved_question_id is None


def test_stale_timer_ignored() -> None:
    state = EngineState(call_id="t", elder_display_name="Даниил")
    state.waiting_on_slot = "wellness"
    state.bump_revision()
    state, effects = reduce(
        state,
        TimerExpired(timer_id="wait-wellness", revision=state.revision - 1),
    )
    assert effects == []


def test_wait_expired_uses_engine_not_planner(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMVERA_DIALOGUE_ENGINE", "1")
    monkeypatch.setenv("IMVERA_VOICE_DIRECT_WELLNESS_OPENING", "1")
    session = _session()
    assert session._engine is not None
    session._engine.start()
    speak = session._engine.pop_speak_effect()
    assert speak is not None
    session._playout_meta[speak.generation_id] = (speak.generation, speak.question_id)
    session.mark_spoken_action(speak.generation_id)
    session._engine.state.waiting_on_slot = "wellness"
    planner_called: list[bool] = []

    def _blocked(*_a, **_k):
        planner_called.append(True)
        raise AssertionError("planner must not run")

    with patch.object(Planner, "plan_wait_expired", side_effect=_blocked):
        result = session.handle_wait_expired("wait-wellness")
    assert not planner_called
    assert result.from_engine


def test_new_user_turn_invalidates_engine_timer(monkeypatch: pytest.MonkeyPatch) -> None:
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
        timer = TimerEffect(
            effect_id="fx-t",
            revision=1,
            timer_id="wait-wellness",
            wait_ms=5000,
            reason="backchannel",
        )
        await actor._schedule_engine_timer(timer)
        assert actor._engine_timer_task is not None
        await actor._cancel_engine_timer()
        assert actor._engine_timer_task is None

    asyncio.run(scenario())


def test_playout_completed_emits_answer_wait_timer() -> None:
    state = EngineState(call_id="t", elder_display_name="Даниил")
    state, effects = reduce(state, CallStarted())
    speak = effects[0]
    state, followups = reduce(
        state,
        PlayoutCompleted(
            generation=speak.generation,
            question_id=speak.question_id,
            revision=state.revision,
        ),
    )
    assert followups
    assert isinstance(followups[0], TimerEffect)
    assert followups[0].timer_id == "wait-wellness"


def test_pop_speak_effect_preserves_timer_in_queue() -> None:
    eng = DialogueEngine(call_id="t", elder_display_name="Даниил")
    eng.start()
    speak = eng.pop_speak_effect()
    assert speak is not None
    eng.on_playout_completed(speak.generation, speak.question_id)
    assert eng.pop_speak_effect() is None
    timer = eng.pop_timer_effect()
    assert timer is not None
    assert timer.timer_id == "wait-wellness"


def test_mark_spoken_followup_survives_pop_speak_effect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression fs-1fbe9a6a: pop_speak_effect must not drop TimerEffect from queue."""
    monkeypatch.setenv("IMVERA_DIALOGUE_ENGINE", "1")
    session = _session()
    result = session.start()
    speak = result.speak_effect
    assert speak is not None
    session.mark_spoken_action(speak.generation_id)
    followup = session.pop_engine_playout_followup()
    assert followup is not None
    assert followup.proposal.intent == "wait_for_continuation"
    assert followup.timer_effect is not None
    assert followup.timer_effect.timer_id == "wait-wellness"


def test_check_plans_playout_followup_schedules_wait_timer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After sleep fill → check_plans question, playout complete must arm wait-plans."""
    monkeypatch.setenv("IMVERA_DIALOGUE_ENGINE", "1")
    session = _session()
    opening = session.start()
    assert opening.speak_effect is not None
    session.mark_spoken_action(opening.speak_effect.generation_id)
    session.pop_engine_playout_followup()
    last_timer: TimerEffect | None = None
    for text in ("Хорошо.", "Плохое.", "Спал плохо."):
        turn = session.handle_user_text(text)
        assert turn.speak_effect is not None
        session.mark_spoken_action(turn.speak_effect.generation_id)
        followup = session.pop_engine_playout_followup()
        assert followup is not None
        assert followup.timer_effect is not None
        last_timer = followup.timer_effect
    assert last_timer is not None
    assert last_timer.timer_id == "wait-plans"


def test_fs_14c79443_full_sequence_reaches_goodbye_final() -> None:
    r = ScenarioRunner(call_id="fs-14c79443", elder_display_name="Даниил")
    result = r.run(
        [
            CallStarted(),
            "Хорошо себя чувствую.",
            "Хорошее.",
            "Спал нормально.",
            "Дома посижу.",
            "до свидания",
            "да",
        ]
    )
    intents = [e.intent for e in result.speak_effects]
    assert intents.count("opening_wellness") == 1
    assert "summary" in intents
    assert "goodbye_confirm" in intents
    assert "goodbye_final" in intents
    for slot in ("wellness", "mood", "sleep", "plans"):
        assert result.state.slots[slot] == SlotStatus.FILLED


def test_session_summary_allowed_after_probe_path_plans_fill() -> None:
    """Regression fs-8054b8c5: Validator must not block engine summary on legacy identity/consent."""
    from packages.core.memory_store import InMemoryCallRecordStore
    from packages.dialogue.session import CallSession
    from packages.dialogue_engine.context import InterpretContext
    from packages.dialogue_engine.contextual_interpreter import contextual_interpret
    from packages.dialogue_engine.semantic import semantic_to_interpretation
    from packages.dialogue.interpretation import to_turn_interpretation

    session = CallSession(
        call_id="fs-8054b8c5",
        family_id="audit-family",
        store=InMemoryCallRecordStore(),
    )
    session.start()
    turns = [
        "Плохо.",
        "Беспокоит головная боль, тошнота.",
        "в течение часа",
        "Нормально.",
        "Пойдёт, нормально.",
        "Планов никаких нету.",
    ]
    for i, text in enumerate(turns, 1):
        eng = session._engine
        assert eng is not None
        ctx = InterpretContext.from_engine_state(eng.state, turn_id=f"u-{i}")
        sem, _ = contextual_interpret(text, ctx)
        interp = semantic_to_interpretation(sem)
        contract = to_turn_interpretation(
            session.state,
            session.turn_id + 1,
            text,
            interp,
            state_version=session.state.state_version,
        )
        result = session.handle_user_text(
            text,
            interp=interp,
            contract=contract,
            utterance_id=f"u-{i}",
        )
        if i < len(turns):
            assert result.proposal.intent != "summary"
        else:
            assert result.proposal.intent == "summary"
            assert result.validated.allowed is True
            assert result.speak_effect is not None
            assert result.speak_effect.intent == "summary"


def test_session_handle_stale_replaces_deferred_summary() -> None:
    session = _session()
    assert session._engine is not None
    session._engine.state.fsm_state = FsmState.SUMMARY
    session._engine.state.summary_spoken = True
    stale = _speak(session._engine, effect_id="fx-stale", revision=1, generation=1)
    session._engine.state.bump_revision()
    session._engine.state.active_playout_generation = 2
    replacement = session.handle_stale_speak_effect(stale)
    assert replacement is not None
    assert replacement.speak_effect is not None
    assert replacement.speak_effect.intent == "summary"
    assert session._engine.is_speak_effect_valid(replacement.speak_effect)
