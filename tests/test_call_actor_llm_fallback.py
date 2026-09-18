"""CallActor uses rule-based interpretation when LLM is unavailable."""

import asyncio
from types import SimpleNamespace

from packages.contracts.enums import AsrQuality, FsmState
from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.session import CallSession
from packages.voice_runtime.call_actor import CallActor, MediaCallbacks


def test_call_actor_llm_failure_falls_back_to_rule_identity_yes() -> None:
    async def scenario() -> None:
        session = CallSession(
            call_id="llm-fallback",
            family_id="audit-family",
            store=InMemoryCallRecordStore(),
        )
        session.start()
        session.state.fsm_state = FsmState.IDENTIFY_PERSON
        session.state.pending_question = "Я разговариваю с Даниил?"
        session.state.pending_question_delivered = True

        async def stt(_pcm, *_a, **_k):
            return SimpleNamespace(text="Да.", asr_quality=AsrQuality.GOOD)

        async def llm_fail(*_a, **_k):
            raise RuntimeError("LLM HTTP 422: invalid SemanticPayload")

        async def noop(*_a, **_k):
            return None

        actor = CallActor(
            call_id=session.state.call_id,
            family_id="audit-family",
            session=session,
            stt=SimpleNamespace(transcribe_final=stt),
            tts=SimpleNamespace(cancel=noop),
            llm=SimpleNamespace(interpret_turn=llm_fail),
            media=MediaCallbacks(noop, noop, noop, noop),
        )
        actor._speak_phrase = noop  # type: ignore[method-assign]

        await actor._handle_utterance(b"u1", 1)
        await asyncio.sleep(0.05)

        assert session.state.mandatory_checks.get("identity") is True
        assert session.state.fsm_state != FsmState.IDENTIFY_PERSON

    asyncio.run(scenario())
