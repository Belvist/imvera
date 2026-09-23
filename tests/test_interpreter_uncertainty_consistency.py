from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from packages.contracts.enums import AsrQuality, FsmState, SlotStatus
from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.session import CallSession
from packages.dialogue_engine.context import InterpretContext
from packages.dialogue_engine.contextual_interpreter import contextual_interpret
from packages.dialogue_engine.fast_interpreter import fast_interpret_semantic
from packages.dialogue_engine.semantic import SemanticAct
from packages.voice_runtime import call_actor
from packages.voice_runtime.call_actor import CallActor, MediaCallbacks

pytestmark = pytest.mark.dialogue_engine


def _context(answer_slot: str) -> InterpretContext:
    return InterpretContext(
        delivered_question=None,
        playing_question=None,
        answer_slot=answer_slot,
        open_slots=(answer_slot,),
        filled_slots=frozenset(),
        fsm_state=FsmState.DAILY_CHECK,
    )


@pytest.mark.parametrize("text", ["не знаю", "затрудняюсь", "сложно сказать", "Ну, не знаю."])
def test_explicit_wellness_uncertainty_agrees(text: str) -> None:
    contextual, contextual_confident = contextual_interpret(text, _context("wellness"))
    fast, fast_confident = fast_interpret_semantic(text, answer_slot="wellness")
    assert contextual.act == SemanticAct.UNCLEAR
    assert not contextual_confident
    assert fast.act == contextual.act
    assert fast.target_slot == contextual.target_slot == "wellness"
    assert fast.polarity is contextual.polarity is None
    assert fast.source_quote == contextual.source_quote == text
    assert not fast.slots and not contextual.slots
    assert fast_confident == contextual_confident


@pytest.mark.parametrize("answer_slot", ["mood", "sleep", "plans"])
def test_other_slot_uncertainty_retains_existing_semantics(answer_slot: str) -> None:
    for interpret in (
        lambda: contextual_interpret("не знаю", _context(answer_slot)),
        lambda: fast_interpret_semantic("не знаю", answer_slot=answer_slot),
    ):
        semantic, confident = interpret()
        assert semantic.act == SemanticAct.ANSWER
        assert semantic.target_slot == answer_slot
        assert semantic.polarity == "uncertain"
        assert confident


@pytest.mark.parametrize(
    ("text", "polarity"),
    [("так себе", "uncertain"), ("Голова болит.", "negative"),
     ("Не знаю, но голова болит.", "negative")],
)
def test_substantive_wellness_answers_are_not_explicit_uncertainty(
    text: str, polarity: str,
) -> None:
    for interpret in (
        lambda: contextual_interpret(text, _context("wellness")),
        lambda: fast_interpret_semantic(text, answer_slot="wellness"),
    ):
        semantic, confident = interpret()
        assert semantic.act == SemanticAct.ANSWER
        assert semantic.target_slot == "wellness"
        assert semantic.polarity == polarity
        assert semantic.value == text
        assert confident


@pytest.mark.parametrize("text", ["абракадабра", "Меня знобит."])
def test_no_match_remains_available_for_other_interpreters(text: str) -> None:
    for interpret in (
        lambda: contextual_interpret(text, _context("wellness")),
        lambda: fast_interpret_semantic(text, answer_slot="wellness"),
    ):
        semantic, confident = interpret()
        assert semantic.act == SemanticAct.UNCLEAR
        assert not confident


@pytest.fixture
def runtime_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in {
        "IMVERA_DIALOGUE_ENGINE": "1",
        "IMVERA_COVERAGE_LADDER": "1",
        "IMVERA_LLM_INTERPRET": "0",
        "IMVERA_MISSION_LLM_INTERPRET": "0",
        "IMVERA_TINYLLM_MODEL": "",
        "IMVERA_ACTION_POLICY_MODE": "off",
        "IMVERA_STT_DUMP": "0",
        "IMVERA_FORENSIC": "0",
    }.items():
        monkeypatch.setenv(name, value)


async def _runtime_turns(monkeypatch: pytest.MonkeyPatch, texts: list[str]):
    session = CallSession(
        call_id="uncertainty-consistency",
        family_id="audit-family",
        store=InMemoryCallRecordStore(),
    )
    opening = session.start()
    assert session.mark_spoken_action(opening.proposal.generation_id)
    assert session._engine is not None
    assert session._engine.answer_context_slot() == "wellness"
    delivered = []
    fallback_results = []
    outcomes = []

    async def deliver(result):
        delivered.append(result)
        assert session.mark_spoken_action(result.proposal.generation_id)

    def fast_spy(text, *, answer_slot):
        result = fast_interpret_semantic(text, answer_slot=answer_slot)
        fallback_results.append((text, result))
        return result

    monkeypatch.setattr(call_actor, "fast_interpret_semantic", fast_spy)
    stt = AsyncMock(side_effect=[
        SimpleNamespace(text=text, asr_quality=AsrQuality.GOOD, model_revision="test")
        for text in texts
    ])
    llm = AsyncMock(side_effect=AssertionError("LLM must not run"))
    actor = CallActor(
        call_id=session.state.call_id,
        family_id="audit-family",
        session=session,
        stt=SimpleNamespace(transcribe_final=stt),
        tts=SimpleNamespace(cancel=AsyncMock()),
        llm=SimpleNamespace(interpret_turn=llm),
        media=MediaCallbacks(AsyncMock(), AsyncMock(), AsyncMock(), AsyncMock()),
    )
    monkeypatch.setattr(actor, "_deliver_session_turn", deliver)
    submit = actor._submit_utterance_outcome

    async def submit_spy(outcome):
        outcomes.append(outcome)
        await submit(outcome)

    monkeypatch.setattr(actor, "_submit_utterance_outcome", submit_spy)
    for seq in range(1, len(texts) + 1):
        await actor._handle_utterance(b"\x01\x00" * 16000, seq)
    assert stt.await_count == len(texts)
    llm.assert_not_awaited()
    assert len(outcomes) == len(texts)
    assert all(outcome.ok and outcome.rich_turn is not None for outcome in outcomes)
    assert len(delivered) == len(texts)
    return session._engine.state, delivered, fallback_results, outcomes


@pytest.mark.usefixtures("runtime_flags")
async def test_runtime_positive_with_clause_never_probes_concern(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Live fs-27a3ced4: «Ну хорошо, только что покушала.» after a delivered
    greeting → mission path recorded polarity 'uncertain' (judge 'answer') →
    safety net asked «Что вас беспокоит» of a healthy person. Clear valence
    beats the boundary: positive → routine ladder, never the concern probe."""
    state, delivered, _, _ = await _runtime_turns(
        monkeypatch, ["Ну хорошо, только что покушала."]
    )
    assert state.slots["wellness"] == SlotStatus.FILLED
    assert state.slot_records["wellness"].polarity == "positive"
    intents = [result.proposal.intent for result in delivered]
    assert "probe_concern" not in intents
    assert "probe_concern_options" not in intents
    assert not state.call_closed


@pytest.mark.usefixtures("runtime_flags")
async def test_runtime_explicit_uncertainty_keeps_wellness_open(monkeypatch) -> None:
    state, delivered, fallback, outcomes = await _runtime_turns(monkeypatch, ["не знаю"])
    assert state.slots["wellness"] == SlotStatus.OPEN
    assert "wellness" not in state.slot_records
    assert state.answer_context_slot() == "wellness"
    assert not state.call_closed
    assert [result.proposal.intent for result in delivered] == ["clarify_wellness"]
    assert len(fallback) == 1
    semantic, confident = fallback[0][1]
    assert semantic.act == SemanticAct.UNCLEAR
    assert not confident
    assert not outcomes[0].interp.fills_pending_slot


@pytest.mark.usefixtures("runtime_flags")
@pytest.mark.parametrize("text", ["так себе", "Голова болит.", "Не знаю, но голова болит."])
async def test_runtime_substantive_wellness_remains_recorded(monkeypatch, text) -> None:
    state, delivered, _, _ = await _runtime_turns(monkeypatch, [text])
    assert state.slots["wellness"] == SlotStatus.FILLED
    assert state.slot_records["wellness"].polarity in ("uncertain", "negative")
    assert not state.call_closed
    assert all(result.proposal.intent != "background_nutrition" for result in delivered)
    if text == "так себе":
        assert delivered[-1].proposal.intent == "probe_concern"
    else:
        assert any(ep.body_site == "голова" for ep in state.issue_episodes.values())


@pytest.mark.usefixtures("runtime_flags")
@pytest.mark.parametrize("texts", [["Меня знобит."], ["Хорошо.", "Меня знобит."]])
async def test_runtime_no_match_does_not_suppress_new_concern(monkeypatch, texts) -> None:
    state, delivered, fallback, outcomes = await _runtime_turns(monkeypatch, texts)
    assert len(fallback) == 1
    semantic, confident = fallback[0][1]
    assert semantic.act == SemanticAct.UNCLEAR
    assert not confident
    assert outcomes[-1].rich_turn.issue_mentions
    assert state.issue_episodes
    assert not state.call_closed
    assert "background_" not in delivered[-1].proposal.intent
    episode = next(iter(state.issue_episodes.values()))
    assert episode.primary_label == "знобит"
    assert episode.subject == "speaker"
    assert state.pending_episode_attribute == "onset"
    assert delivered[-1].proposal.intent == f"episode_{episode.episode_id}_onset"


def test_no_answer_slot_retains_existing_fast_behavior() -> None:
    semantic, confident = fast_interpret_semantic("не знаю", answer_slot=None)
    assert semantic.act == SemanticAct.ANSWER
    assert semantic.target_slot is None
    assert semantic.polarity == "uncertain"
    assert confident


@pytest.mark.usefixtures("runtime_flags")
async def test_runtime_uncertainty_can_recover_with_valid_answer(monkeypatch) -> None:
    state, delivered, fallback, _ = await _runtime_turns(monkeypatch, ["не знаю", "так себе"])
    semantic, confident = fallback[0][1]
    assert semantic.act == SemanticAct.UNCLEAR
    assert not confident
    assert [result.proposal.intent for result in delivered] == [
        "clarify_wellness", "probe_concern",
    ]
    assert state.slots["wellness"] == SlotStatus.FILLED
    assert state.slot_records["wellness"].value == "так себе"
    assert state.slot_records["wellness"].polarity == "uncertain"
    assert not state.call_closed
