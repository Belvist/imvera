"""§6.2 — stale generation after STOP/barge-in must not resume speech."""

import asyncio
from types import SimpleNamespace

from packages.contracts.enums import FsmState
from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.planner import Planner
from packages.dialogue.session import CallSession
from packages.voice_runtime.call_actor import CallActor, MediaCallbacks
from packages.voice_runtime.wait_state import DialogueTimingProfile


async def _noop(*_a, **_k):
    return None


async def _cancel_tts(*_a, **_k):
    return None


def test_barge_in_bumps_control_epoch_and_invalidates_wait() -> None:
    async def scenario() -> None:
        session = CallSession(
            call_id="stop-epoch",
            family_id="audit-family",
            store=InMemoryCallRecordStore(),
        )
        session.state.mandatory_checks.update(identity=True, consent=True, can_talk=True)
        session.state.greeted = True
        session.state.fsm_state = FsmState.DAILY_CHECK
        open_prop = Planner.plan_vera_turn(session.state, 1, "g1")
        session.transitions.commit_transition(session.state, open_prop)
        session.mark_spoken_action("g1")

        actor = CallActor(
            call_id=session.state.call_id,
            family_id="audit-family",
            session=session,
            stt=SimpleNamespace(),
            tts=SimpleNamespace(cancel=_cancel_tts),
            llm=SimpleNamespace(),
            media=MediaCallbacks(_noop, _noop, _noop, _noop),
        )
        actor._timing_profile = DialogueTimingProfile(answer_wait_ms=5000)
        actor._start_answer_wait(goal_id="g1", question_id="q1")
        old_wait = actor._wait_state
        assert old_wait is not None
        old_epoch = actor._control_epoch

        await actor._interrupt_playback(flush=True)
        assert actor._control_epoch == old_epoch + 1
        await actor._on_wait_deadline(old_wait.wait_id, old_epoch)
        assert session.state.get_goal("wellness").automatic_attempts_used == 1

    asyncio.run(scenario())
