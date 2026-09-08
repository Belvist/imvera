"""Engine-authoritative deferred speak — revision guard, not CallActor queue."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from packages.contracts.enums import AnswerJudgement, DialogueAct, FsmState
from packages.contracts.interpretation import TurnInterpretation
from packages.contracts.status import SafetySnapshot
from packages.contracts.turn import TurnProposal, ValidatedTurn
from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.interpretation import UserInterpretation
from packages.dialogue.session import CallSession, SessionTurnResult
from packages.dialogue_engine.effects import SpeakEffect
from packages.dialogue_engine.engine import DialogueEngine
from packages.dialogue_engine.reducer import reduce
from packages.dialogue_engine.scenario_runner import ScenarioRunner
from packages.dialogue_engine.state import EngineState
from packages.voice_runtime.call_actor import CallActor, MediaCallbacks

pytestmark = pytest.mark.dialogue_engine


async def _noop(*_a, **_k):
    return None


def test_is_speak_effect_valid_requires_current_revision() -> None:
    eng = DialogueEngine(call_id="t", elder_display_name="Даниил")
    eff = SpeakEffect(
        effect_id="fx-1",
        revision=eng.revision,
        generation_id="g-1",
        generation=1,
        text="Спасибо за разговор.",
        intent="summary",
    )
    eng.state.active_playout_generation = 1
    assert eng.is_speak_effect_valid(eff)
    eng.state.bump_revision()
    assert not eng.is_speak_effect_valid(eff)


def test_backchannel_after_last_slot_does_not_reemit_summary() -> None:
    r = ScenarioRunner(call_id="defer-stale", elder_display_name="Даниил")
    r.run(
        [
            "Хорошо.",
            "Нормально.",
            "Спал нормально.",
            "Дома посижу.",
        ]
    )
    before = len(r.effects)
    r.run(["ага"])
    new_effects = r.effects[before:]
    assert not any(
        getattr(e, "intent", "") == "summary" for e in new_effects
    )


def test_call_actor_defers_to_session_not_local_queue() -> None:
    async def scenario() -> None:
        session = CallSession(
            call_id="actor-defer",
            family_id="audit-family",
            store=InMemoryCallRecordStore(),
        )
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

        assert session._engine is not None
        session._engine.state.fsm_state = FsmState.SUMMARY
        session._engine.state.summary_spoken = True
        session._engine.state.active_playout_generation = 1
        speak = SpeakEffect(
            effect_id="fx-summary",
            revision=session._engine.revision,
            generation_id="g-summary",
            generation=session._engine.state.active_playout_generation,
            text="Спасибо за разговор.",
            intent="summary",
        )
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
                fsm_state=FsmState.DAILY_CHECK,
            ),
            validated=ValidatedTurn(
                turn_id=5,
                generation_id="g-summary",
                speech="Спасибо за разговор.",
                intent="summary",
                fsm_state=FsmState.DAILY_CHECK,
                allowed=True,
            ),
            safety=SafetySnapshot(),
            persist_ok=True,
            from_engine=True,
            speak_effect=speak,
        )

        actor._inflight_utterances.add(99)
        await actor._enqueue_turn_delivery(summary)
        assert delivered == []
        assert session._deferred_engine_turn is not None

        actor._inflight_utterances.discard(99)
        flushed = await asyncio.to_thread(session.flush_deferred_engine_turn)
        assert flushed is not None
        await actor._deliver_session_turn(flushed)
        assert delivered == ["summary"]

    asyncio.run(scenario())


def test_emit_speak_tags_revision_on_effect() -> None:
    state = EngineState(call_id="t", elder_display_name="Даниил")
    from packages.dialogue_engine.events import CallStarted

    state, effects = reduce(state, CallStarted())
    assert effects
    speak = effects[0]
    assert speak.revision == state.revision
    assert speak.effect_id
