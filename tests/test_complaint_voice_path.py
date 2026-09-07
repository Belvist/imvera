"""Voice path for complaints — CallActor STT→LLM→adapter→Planner→TTS."""

import asyncio
from types import SimpleNamespace

from packages.contracts.enums import AsrQuality, FsmState, SlotStatus
from packages.contracts.semantic import Evidence, FactCandidate, SemanticPayload
from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.planner import Planner
from packages.dialogue.session import CallSession
from packages.voice_runtime.call_actor import CallActor, MediaCallbacks
from services.llm.http_provider import RenderChunk


def _evidence(text: str, quote: str) -> Evidence:
    start = text.index(quote)
    return Evidence(start=start, end=start + len(quote), quote=quote)


def _complaint_payload(text: str) -> SemanticPayload:
    quote = "Голова болит с утра"
    return SemanticPayload(
        dialogue_act="answer",
        control="none",
        consent_answer="not_applicable",
        answers_pending_question=True,
        needs_clarification=False,
        facts=(
            FactCandidate(
                field="wellness",
                value=quote,
                subject="speaker",
                temporal_scope="now",
                negated=False,
                evidence=_evidence(text, quote),
            ),
        ),
    )


def _session_at_wellness() -> CallSession:
    session = CallSession(
        call_id="actor-complaint",
        family_id="audit-family",
        store=InMemoryCallRecordStore(),
    )
    start = session.start()
    session.state.mandatory_checks.update(identity=True, consent=True, can_talk=True)
    session.state.greeted = True
    session.mark_spoken_action(start.proposal.generation_id)
    return session


class _ComplaintLLM:
    async def interpret_turn(self, ctx, **_kw):
        return SimpleNamespace(payload=_complaint_payload(ctx.raw_text))

    async def render_stream(self, action, _facts, _deadline, request_id=None):
        text = action.get("planner_text") or ""
        if text:
            yield RenderChunk(text, done=True)


def test_complaint_reflect_report_through_call_actor() -> None:
    async def scenario() -> None:
        session = _session_at_wellness()
        spoken: list[str] = []
        text = "Голова болит с утра"

        async def stt(_pcm, *_a, **_k):
            return SimpleNamespace(text=text, asr_quality=AsrQuality.GOOD)

        async def speak(phrase: str, _gen: str) -> None:
            spoken.append(phrase)

        async def noop(*_a, **_k):
            return None

        actor = CallActor(
            call_id=session.state.call_id,
            family_id="audit-family",
            session=session,
            stt=SimpleNamespace(transcribe_final=stt),
            tts=SimpleNamespace(cancel=noop, synthesize=noop),
            llm=_ComplaintLLM(),
            media=MediaCallbacks(noop, noop, noop, noop),
        )
        actor._speak_phrase = speak  # type: ignore[method-assign]

        await actor._handle_utterance(b"u1", 1)
        await asyncio.sleep(0.05)

        assert session.state.slots["wellness"] == SlotStatus.FILLED
        assert len(session.state.facts) == 1
        assert spoken
        joined = " ".join(spoken).lower()
        assert "болит" in joined
        assert "отлично" not in joined
        assert "?" not in joined

    asyncio.run(asyncio.wait_for(scenario(), timeout=5))
