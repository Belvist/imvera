"""CallActor load: multi-phrase playback, barge-in, TTS-fail reservation release.

Uses mock TTS/LLM — NOT live HTTP TTS ×1000, NOT live SIP.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from packages.contracts.enums import AnswerJudgement, DialogueAct
from packages.contracts.interpretation import TurnInterpretation
from packages.contracts.turn import TurnProposal
from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.interpretation import UserInterpretation
from packages.dialogue.planner import Planner
from packages.dialogue.session import CallSession, SessionTurnResult
from packages.dialogue.validator import Validator
from packages.voice_runtime.call_actor import CallActor, CallActorConfig, MediaCallbacks
from packages.voice_runtime.playback import PlaybackQueue
from services.llm.http_provider import RenderChunk


async def _noop(*args, **kwargs):
    pass


def _wellness_session(call_id: str) -> CallSession:
    session = CallSession(
        call_id=call_id,
        family_id="corpus-load",
        store=InMemoryCallRecordStore(),
    )
    session.state.mandatory_checks.update(identity=True, consent=True, can_talk=True)
    session.state.greeted = True
    proposal = Planner.plan_vera_turn(session.state, 1, "question-1")
    session.mark_spoken_action(proposal.generation_id)
    return session


async def _multi_phrase_once(call_id: str, *, barge_in: bool = False) -> list[str]:
    session = _wellness_session(call_id)
    session.turn_id += 1
    proposal = TurnProposal(
        turn_id=session.turn_id,
        generation_id="g-render",
        speech="Спасибо.",
        intent="explain_vera",
        fsm_state=session.state.fsm_state,
        mandatory_remaining=session.state.mandatory_remaining(),
    )
    validated = Validator.validate(proposal)
    result = SessionTurnResult(
        user_text="болит спина",
        interpretation=UserInterpretation(
            judgement=AnswerJudgement.VALID,
            dialogue_act=DialogueAct.ANSWER,
        ),
        turn_contract=TurnInterpretation(
            call_id=session.state.call_id,
            turn_id=session.turn_id,
            raw_text="болит спина",
            dialogue_act=DialogueAct.ANSWER,
            judgement=AnswerJudgement.VALID,
            state_version=session.state.state_version,
        ),
        proposal=proposal,
        validated=validated,
        safety=session.safety.model_copy(deep=True),
    )
    tts_started: list[str] = []

    async def synthesize(text, **kwargs):
        tts_started.append(text)
        yield SimpleNamespace(pcm_s16le=b"\x01\x00" * 160, sample_rate=16000)

    async def stream(*args, **kwargs):
        yield RenderChunk("Поняла.", delta=True)
        if barge_in:
            await asyncio.sleep(0.03)
        yield RenderChunk(" Как вы спали?", delta=True)
        yield RenderChunk("Поняла. Как вы спали?", done=True)

    actor = CallActor(
        call_id=session.state.call_id,
        family_id=session.state.family_id,
        session=session,
        stt=SimpleNamespace(),
        tts=SimpleNamespace(synthesize=synthesize, cancel=_noop),
        llm=SimpleNamespace(render_stream=stream, cancel_request=_noop),
        media=MediaCallbacks(_noop, _noop, _noop, _noop),
        config=CallActorConfig(telephony_stream=False, post_speech_pause_ms=0),
    )
    actor._playback = PlaybackQueue(call_id=actor.call_id, sample_rate=16000)
    actor._playback_task = asyncio.create_task(actor._playback_pump())

    deliver = asyncio.create_task(actor._deliver_session_turn(result))
    if barge_in:
        await asyncio.sleep(0.015)
        await actor._interrupt_playback(flush=True)
    try:
        await asyncio.wait_for(deliver, timeout=3.0)
    except (TimeoutError, asyncio.CancelledError):
        if not deliver.done():
            deliver.cancel()
            await asyncio.gather(deliver, return_exceptions=True)

    actor._playback_task.cancel()
    await asyncio.gather(actor._playback_task, return_exceptions=True)
    await actor._cancel_wait_timer()
    return tts_started


async def _tts_fail_release(call_id: str) -> None:
    session = CallSession(
        call_id=call_id,
        family_id="corpus-load",
        store=InMemoryCallRecordStore(),
    )
    open_result = session.start()
    goal = session.state.get_goal("wellness")
    assert goal is not None
    assert goal.reserved_attempt_id == open_result.proposal.generation_id

    async def failing_synthesize(*args, **kwargs):
        raise RuntimeError("tts down")
        yield  # pragma: no cover

    actor = CallActor(
        call_id=session.state.call_id,
        family_id="corpus-load",
        session=session,
        stt=SimpleNamespace(),
        tts=SimpleNamespace(synthesize=failing_synthesize, cancel=_noop),
        llm=SimpleNamespace(cancel_request=_noop),
        media=MediaCallbacks(_noop, _noop, _noop, _noop),
        config=CallActorConfig(telephony_stream=False, post_speech_pause_ms=0),
    )
    actor._playback = PlaybackQueue(call_id=actor.call_id, sample_rate=16000)
    actor._playback_task = asyncio.create_task(actor._playback_pump())
    await actor._deliver_session_turn(open_result)
    goal = session.state.get_goal("wellness")
    assert goal is not None
    assert goal.reserved_attempt_id is None
    assert actor._wait_state is None
    actor._playback_task.cancel()
    await asyncio.gather(actor._playback_task, return_exceptions=True)


@pytest.mark.asyncio
async def test_call_actor_multi_phrase_load_sequential() -> None:
    """Many synthetic multi-phrase turns: sequential TTS, no concurrent synthesize."""
    n = 50
    for i in range(n):
        started = await _multi_phrase_once(f"load-seq-{i}", barge_in=False)
        assert started == ["Поняла.", "Как вы спали?"], started


@pytest.mark.asyncio
async def test_call_actor_barge_in_load() -> None:
    """Barge-in under repeated synthetic turns cancels second phrase TTS."""
    n = 20
    for i in range(n):
        started = await _multi_phrase_once(f"load-barge-{i}", barge_in=True)
        assert started, f"expected at least first phrase on iter {i}"
        assert started[0] == "Поняла."
        # Second phrase must not start after barge-in.
        assert started == ["Поняла."], started


@pytest.mark.asyncio
async def test_call_actor_tts_fail_release_concurrent() -> None:
    """Concurrent simulated calls: TTS fail releases reservation (not stuck delivered)."""
    n = 40
    await asyncio.gather(*[_tts_fail_release(f"load-tts-fail-{i}") for i in range(n)])
