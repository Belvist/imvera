"""CallActor WAIT path — backchannel without immediate TTS."""

import asyncio
from types import SimpleNamespace

from packages.contracts.enums import AnswerJudgement, DialogueAct, FsmState
from packages.contracts.interpretation import TurnInterpretation
from packages.contracts.status import SafetySnapshot
from packages.contracts.turn import TurnProposal, ValidatedTurn
from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.interpretation import UserInterpretation
from packages.dialogue.planner import Planner
from packages.dialogue.session import CallSession, SessionTurnResult
from packages.voice_runtime.call_actor import CallActor, MediaCallbacks
from packages.voice_runtime.wait_state import DialogueTimingProfile


async def _noop(*_a, **_k):
    return None


def _session_at_wellness() -> CallSession:
    session = CallSession(
        call_id="actor-aha",
        family_id="audit-family",
        store=InMemoryCallRecordStore(),
    )
    session.state.mandatory_checks.update(identity=True, consent=True, can_talk=True)
    session.state.greeted = True
    session.state.fsm_state = FsmState.DAILY_CHECK
    open_prop = Planner.plan_vera_turn(session.state, 1, "g1")
    session.transitions.commit_transition(session.state, open_prop)
    session.mark_spoken_action("g1")
    return session


def test_call_actor_wait_skips_tts_and_fires_expiry() -> None:
    async def scenario() -> None:
        session = _session_at_wellness()
        spoken: list[str] = []

        async def speak(text: str, _gen: str) -> None:
            spoken.append(text)

        actor = CallActor(
            call_id=session.state.call_id,
            family_id="audit-family",
            session=session,
            stt=SimpleNamespace(),
            tts=SimpleNamespace(),
            llm=SimpleNamespace(),
            media=MediaCallbacks(_noop, _noop, _noop, _noop),
        )
        actor._timing_profile = DialogueTimingProfile(answer_wait_ms=30, backchannel_extra_ms=10)
        actor._speak_phrase = speak  # type: ignore[method-assign]

        wait_result = SessionTurnResult(
            user_text="ага",
            interpretation=UserInterpretation(
                judgement=AnswerJudgement.BACKCHANNEL,
                dialogue_act=DialogueAct.BACKCHANNEL,
            ),
            turn_contract=TurnInterpretation(
                call_id=session.state.call_id,
                turn_id=2,
                raw_text="ага",
                state_version=session.state.state_version,
                dialogue_act=DialogueAct.BACKCHANNEL,
                judgement=AnswerJudgement.BACKCHANNEL,
            ),
            proposal=TurnProposal(
                turn_id=2,
                generation_id="g-wait",
                speech="",
                intent="wait_for_continuation",
                fsm_state=FsmState.DAILY_CHECK,
                wait_goal_id=session.state.ensure_goal("wellness").goal_id,
            ),
            validated=ValidatedTurn(
                turn_id=2,
                generation_id="g-wait",
                speech="",
                intent="wait_for_continuation",
                fsm_state=FsmState.DAILY_CHECK,
                allowed=True,
            ),
            safety=SafetySnapshot(),
        )

        actor._start_answer_wait(
            goal_id=session.state.ensure_goal("wellness").goal_id,
            question_id="g1",
        )
        await actor._deliver_session_turn(wait_result)
        assert spoken == []
        assert actor._wait_state is not None
        await asyncio.sleep(0.05)
        goal = session.state.get_goal("wellness")
        assert goal is not None
        assert goal.automatic_attempts_used >= 1
        assert goal.automatic_attempts_used <= 2

    asyncio.run(scenario())
