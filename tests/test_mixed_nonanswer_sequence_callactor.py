"""§21.1 mixed non-answer sequence through CallActor (STT→LLM→adapter→session)."""

import asyncio
from collections import deque
from types import SimpleNamespace

from packages.contracts.enums import AsrQuality, FsmState, GoalStatus
from packages.contracts.semantic import SemanticPayload
from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.planner import Planner
from packages.dialogue.question_ledger import MAX_AUTOMATIC_ATTEMPTS
from packages.dialogue.session import CallSession
from packages.voice_runtime.call_actor import CallActor, MediaCallbacks
from packages.voice_runtime.wait_state import DialogueTimingProfile, WaitReason
from services.llm.http_provider import RenderChunk


def _payload(dialogue_act: str, **kw) -> SemanticPayload:
    base = {
        "dialogue_act": dialogue_act,
        "control": "none",
        "consent_answer": "not_applicable",
        "answers_pending_question": False,
        "needs_clarification": False,
    }
    base.update(kw)
    return SemanticPayload(**base)


MEANINGS: dict[str, SemanticPayload] = {
    "ага": _payload("backchannel"),
    "не знаю": _payload("unclear", needs_clarification=True),
    "кто вы": _payload("question", user_question="кто вы"),
    "алло": _payload("backchannel"),
}


def _session_at_wellness() -> CallSession:
    session = CallSession(
        call_id="actor-mixed",
        family_id="audit-family",
        store=InMemoryCallRecordStore(),
    )
    session.start()
    session.state.mandatory_checks.update(identity=True, consent=True, can_talk=True)
    session.state.greeted = True
    session.state.fsm_state = FsmState.DAILY_CHECK
    open_prop = Planner.plan_vera_turn(session.state, 1, "g1")
    session.transitions.commit_transition(session.state, open_prop)
    session.mark_spoken_action("g1")
    return session


class _FakeLLM:
    async def interpret_turn(self, ctx, **_kw):
        return SimpleNamespace(payload=MEANINGS[ctx.raw_text.lower()])

    async def render_stream(self, action, _facts, _deadline, request_id=None):
        text = action.get("planner_text") or ""
        if text:
            yield RenderChunk(text, done=True)


def test_mixed_nonanswer_sequence_through_call_actor() -> None:
    async def scenario() -> None:
        session = _session_at_wellness()
        spoken: list[str] = []
        texts = deque(["ага", "не знаю", "кто вы", "алло", "ага"])

        async def stt(_pcm, *_a, **_k):
            return SimpleNamespace(text=texts.popleft(), asr_quality=AsrQuality.GOOD)

        async def speak(text: str, _gen: str) -> None:
            spoken.append(text)

        async def noop(*_a, **_k):
            return None

        actor = CallActor(
            call_id=session.state.call_id,
            family_id="audit-family",
            session=session,
            stt=SimpleNamespace(transcribe_final=stt),
            tts=SimpleNamespace(cancel=noop),
            llm=_FakeLLM(),
            media=MediaCallbacks(noop, noop, noop, noop),
        )
        actor._timing_profile = DialogueTimingProfile(
            answer_wait_ms=40, backchannel_extra_ms=15, pause_wait_ms=500
        )
        actor._speak_phrase = speak  # type: ignore[method-assign]

        for seq in range(1, 5):
            await actor._handle_utterance(f"u{seq}".encode(), seq)
            await asyncio.sleep(0.02)

        assert len(session.state.facts) == 0
        goal = session.state.get_goal("wellness")
        assert goal is not None
        assert goal.automatic_attempts_used <= MAX_AUTOMATIC_ATTEMPTS

        await asyncio.sleep(0.06)
        assert actor._wait_state is None

        await actor._handle_utterance(b"u5", 5)
        await asyncio.sleep(0.02)
        await asyncio.sleep(0.06)

        goal = session.state.get_goal("wellness")
        assert goal is not None
        assert goal.automatic_attempts_used <= MAX_AUTOMATIC_ATTEMPTS
        assert goal.status in (GoalStatus.UNRESOLVED, GoalStatus.OPEN)
        assert len(session.state.facts) == 0
        wellness_questions = [s for s in spoken if "чувствуете" in s.lower()]
        assert len(wellness_questions) <= 2

    asyncio.run(asyncio.wait_for(scenario(), timeout=5))


def test_call_actor_pause_ack_starts_pause_wait() -> None:
    async def scenario() -> None:
        from packages.contracts.enums import AnswerJudgement, DialogueAct
        from packages.dialogue.interpretation import UserInterpretation

        session = _session_at_wellness()
        pause_interp = UserInterpretation(
            judgement=AnswerJudgement.VALID,
            dialogue_act=DialogueAct.PAUSE,
            pause_requested=True,
        )
        pause_result = session.handle_user_text("подождите", interp=pause_interp)
        assert pause_result.proposal.intent == "pause_ack"

        async def noop(*_a, **_k):
            return None

        actor = CallActor(
            call_id=session.state.call_id,
            family_id="audit-family",
            session=session,
            stt=SimpleNamespace(),
            tts=SimpleNamespace(),
            llm=SimpleNamespace(),
            media=MediaCallbacks(noop, noop, noop, noop),
        )
        actor._timing_profile = DialogueTimingProfile(pause_wait_ms=100)
        actor._speak_phrase = noop  # type: ignore[method-assign]
        await actor._deliver_session_turn(pause_result)
        assert actor._wait_state is not None
        assert actor._wait_state.reason == WaitReason.PAUSE

    asyncio.run(scenario())
