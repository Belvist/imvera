"""CallActor → Session → DialogueEngine rich path integration."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from packages.contracts.enums import AsrQuality
from packages.contracts.semantic import Evidence, IssueMention, SemanticPayload
from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.interpretation import to_turn_interpretation
from packages.dialogue.semantic_adapter import adapt_semantic_turn
from packages.dialogue.session import CallSession
from packages.dialogue_engine.events import CallStarted
from packages.dialogue_engine.reducer import reduce
from packages.dialogue_engine.turn_understanding import payload_to_rich_turn
from packages.voice_runtime.call_actor import CallActor, MediaCallbacks, _UtteranceOutcome

pytestmark = pytest.mark.dialogue_engine


async def _noop(*_a, **_k):
    return None


def _evidence(quote: str) -> Evidence:
    return Evidence(start=0, end=len(quote), quote=quote)


def _session_at_wellness() -> CallSession:
    session = CallSession(
        call_id="rich-path",
        family_id="audit-family",
        store=InMemoryCallRecordStore(),
    )
    session.start()
    assert session._engine is not None
    session._engine.state, _ = reduce(session._engine.state, CallStarted())
    return session


def test_session_receives_rich_turn_from_llm_payload_not_legacy_only() -> None:
    session = _session_at_wellness()
    engine = session._engine
    assert engine is not None
    captured: list[object] = []
    original = engine.on_user_turn

    def spy(turn_id: str, text: str, semantic=None, rich_turn=None, **kwargs):
        captured.append(rich_turn)
        return original(turn_id, text, semantic=semantic, rich_turn=rich_turn, **kwargs)

    engine.on_user_turn = spy  # type: ignore[method-assign]

    quote = "Голова болит и тошнит."
    payload = SemanticPayload(
        dialogue_act="answer",
        control="none",
        consent_answer="not_applicable",
        answers_pending_question=True,
        needs_clarification=False,
        issue_mentions=(
            IssueMention(
                mention_id="m1",
                kind="symptom",
                label="головная боль",
                role="primary",
                body_site="голова",
                temporal_scope="now",
                status="active",
                evidence=_evidence("Голова болит"),
            ),
            IssueMention(
                mention_id="m2",
                kind="symptom",
                label="тошнота",
                role="associated",
                temporal_scope="now",
                status="active",
                evidence=_evidence("тошнит"),
            ),
        ),
    )
    interp, validated = adapt_semantic_turn(
        quote,
        payload,
        state=session.state,
        active_question_kind="wellness",
        pending_slot="wellness",
    )
    rich_turn = payload_to_rich_turn(
        validated.payload,
        utterance_id="u-rich",
        raw_text=quote,
    )
    contract = to_turn_interpretation(
        session.state,
        1,
        quote,
        interp,
        state_version=session.state.state_version,
        asr_quality=AsrQuality.GOOD,
    )
    session.handle_user_text(
        quote,
        interp=interp,
        contract=contract,
        utterance_id="u-rich",
        rich_turn=rich_turn,
    )
    assert captured, "engine.on_user_turn must receive rich_turn"
    rt = captured[0]
    assert rt is not None
    assert len(rt.issue_mentions) >= 1
    assert not any(
        m.body_site == "живот" for m in rt.issue_mentions if m.body_site
    )


def test_call_actor_llm_path_passes_rich_turn_to_session() -> None:
    async def scenario() -> None:
        session = _session_at_wellness()
        engine = session._engine
        assert engine is not None
        captured: list[object] = []

        async def deliver(result) -> None:
            pass

        actor = CallActor(
            call_id=session.state.call_id,
            family_id="audit-family",
            session=session,
            stt=SimpleNamespace(transcribe_final=_noop),
            tts=SimpleNamespace(cancel=_noop),
            llm=SimpleNamespace(),
            media=MediaCallbacks(_noop, _noop, _noop, _noop),
        )
        actor._deliver_session_turn = deliver  # type: ignore[method-assign]

        quote = "А вы кто?"
        payload = SemanticPayload(
            dialogue_act="question",
            control="none",
            consent_answer="not_applicable",
            answers_pending_question=False,
            needs_clarification=False,
            user_question=quote,
        )
        interp, validated = adapt_semantic_turn(
            quote,
            payload,
            state=session.state,
            active_question_kind="wellness",
            pending_slot="wellness",
        )
        rich_turn = payload_to_rich_turn(
            validated.payload,
            utterance_id="u-q",
            raw_text=quote,
        )
        contract = to_turn_interpretation(
            session.state,
            2,
            quote,
            interp,
            state_version=session.state.state_version,
            asr_quality=AsrQuality.GOOD,
        )

        original_handle = session.handle_user_text

        def spy_handle(*args, **kwargs):
            captured.append(kwargs.get("rich_turn"))
            return original_handle(*args, **kwargs)

        session.handle_user_text = spy_handle  # type: ignore[method-assign]

        await actor._submit_utterance_outcome(
            _UtteranceOutcome(
                utterance_seq=1,
                utterance_id="u-q",
                ok=True,
                text=quote,
                interp=interp,
                legacy_contract=contract,
                rich_turn=rich_turn,
            )
        )
        assert captured[0] is not None
        assert captured[0].user_question

    asyncio.run(scenario())


def test_short_backchannel_can_stay_fast_path() -> None:
    from packages.dialogue_engine.issue_mention_extract import should_use_rich_turn
    from packages.dialogue_engine.topic_tracker import is_topic_slot

    assert not should_use_rich_turn("угу", "wellness", is_topic_slot_fn=is_topic_slot)


def test_correction_rich_turn_reaches_engine() -> None:
    session = _session_at_wellness()
    engine = session._engine
    assert engine is not None
    captured: list[object] = []
    original = engine.on_user_turn

    def spy(turn_id: str, text: str, semantic=None, rich_turn=None, **kwargs):
        captured.append(rich_turn)
        return original(turn_id, text, semantic=semantic, rich_turn=rich_turn, **kwargs)

    engine.on_user_turn = spy  # type: ignore[method-assign]

    quote = "Я же говорил, что болит"
    payload = SemanticPayload(
        dialogue_act="correction",
        control="none",
        consent_answer="not_applicable",
        answers_pending_question=True,
        needs_clarification=False,
    )
    rich_turn = payload_to_rich_turn(payload, utterance_id="u-c", raw_text=quote)
    interp, validated = adapt_semantic_turn(
        quote,
        payload,
        state=session.state,
        active_question_kind="wellness",
        pending_slot="wellness",
    )
    contract = to_turn_interpretation(
        session.state,
        3,
        quote,
        interp,
        state_version=session.state.state_version,
        asr_quality=AsrQuality.GOOD,
    )
    session.handle_user_text(
        quote,
        interp=interp,
        contract=contract,
        utterance_id="u-c",
        rich_turn=rich_turn,
    )
    assert captured[0] is not None
    assert captured[0].correction or captured[0].dialogue_act == "correction"
