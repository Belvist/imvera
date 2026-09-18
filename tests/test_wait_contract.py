"""§6.1 answer-wait contract — fake clock, single backchannel extension."""

import asyncio
from types import SimpleNamespace

from packages.contracts.enums import AnswerJudgement, DialogueAct, FsmState
from packages.contracts.interpretation import TurnInterpretation
from packages.contracts.status import SafetySnapshot
from packages.contracts.turn import TurnProposal, ValidatedTurn
from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.interpretation import UserInterpretation
from packages.dialogue.session import CallSession, SessionTurnResult
from packages.voice_runtime.call_actor import CallActor, MediaCallbacks
from packages.voice_runtime.wait_state import DialogueTimingProfile, WaitState


async def _noop(*_a, **_k):
    return None


class FakeClock:
    def __init__(self, start: float = 1000.0) -> None:
        self._t = start

    def now(self) -> float:
        return self._t

    def advance(self, seconds: float) -> None:
        self._t += seconds


def _session_at_wellness() -> CallSession:
    session = CallSession(
        call_id="wait-contract",
        family_id="audit-family",
        store=InMemoryCallRecordStore(),
    )
    start = session.start()
    session.state.mandatory_checks.update(identity=True, consent=True, can_talk=True)
    session.state.greeted = True
    session.mark_spoken_action(start.proposal.generation_id)
    return session


def _wait_result(session: CallSession) -> SessionTurnResult:
    return SessionTurnResult(
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


def test_wait_state_answer_window_and_single_backchannel_extra() -> None:
    clock = FakeClock()
    profile = DialogueTimingProfile(answer_wait_ms=7000, backchannel_extra_ms=2000)
    state = WaitState.start_answer_wait(
        goal_id="goal-1",
        question_id="q-1",
        control_epoch=0,
        profile=profile,
        now_mono=clock.now(),
    )
    assert state.remaining_ms(clock.now()) == 7000

    clock.advance(3.0)
    assert not state.should_fire(clock.now())
    assert state.apply_backchannel_extra(profile, clock.now())
    assert state.remaining_ms(clock.now()) == 6000

    clock.advance(1.0)
    assert not state.apply_backchannel_extra(profile, clock.now())

    clock.advance(5.0)
    assert state.should_fire(clock.now())


def test_call_actor_backchannel_extends_once_before_expiry() -> None:
    async def scenario() -> None:
        clock = FakeClock()
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
        actor._timing_profile = DialogueTimingProfile(
            answer_wait_ms=7000, backchannel_extra_ms=2000
        )
        actor._monotonic = clock.now
        actor._speak_phrase = speak  # type: ignore[method-assign]

        actor._start_answer_wait(
            goal_id=session.state.ensure_goal("wellness").goal_id,
            question_id=session.state.get_goal("wellness").last_question_id,
        )
        assert spoken == []

        await actor._handle_backchannel_continuation(_wait_result(session))
        session.state.waiting_on_goal = "wellness"
        clock.advance(5.0)
        assert not actor._wait_state.should_fire(clock.now())
        assert spoken == []

        await actor._handle_backchannel_continuation(_wait_result(session))
        assert actor._wait_state.backchannel_extra_applied
        clock.advance(6.0)
        wait_id = actor._wait_state.wait_id
        epoch = actor._wait_state.control_epoch
        assert actor._wait_state.should_fire(clock.now())
        await actor._on_wait_deadline(wait_id, epoch)
        goal = session.state.get_goal("wellness")
        assert goal is not None
        assert goal.automatic_attempts_used == 1
        assert len(spoken) == 1
        assert "двух словах" in spoken[0]

    asyncio.run(scenario())


def test_stale_wait_id_ignored_after_control_epoch_bump() -> None:
    async def scenario() -> None:
        clock = FakeClock()
        session = _session_at_wellness()
        actor = CallActor(
            call_id=session.state.call_id,
            family_id="audit-family",
            session=session,
            stt=SimpleNamespace(),
            tts=SimpleNamespace(),
            llm=SimpleNamespace(),
            media=MediaCallbacks(_noop, _noop, _noop, _noop),
        )
        actor._timing_profile = DialogueTimingProfile(answer_wait_ms=100)
        actor._monotonic = clock.now
        actor._start_answer_wait(goal_id="g1", question_id="q1")
        wait_id = actor._wait_state.wait_id
        epoch = actor._control_epoch
        actor._bump_control_epoch()
        actor._start_answer_wait(goal_id="g1", question_id="q2")
        clock.advance(0.2)
        await actor._on_wait_deadline(wait_id, epoch)
        assert session.state.get_goal("wellness").automatic_attempts_used == 1

    asyncio.run(scenario())
