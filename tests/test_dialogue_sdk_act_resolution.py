"""The model's act must reach canonical RichUserTurn with truthful usage trace."""

from __future__ import annotations

import struct
from types import SimpleNamespace

import pytest

from packages.contracts.enums import AsrQuality
from packages.dialogue.session import CallSession
from packages.dialogue_engine.semantic import SemanticAct, SemanticTurn
from packages.dialogue_engine.semantic_nlp.model import ActCandidate, SemanticNLP
from packages.dialogue_engine.turn_understanding import RichUserTurn, TurnUnderstandingV2
from packages.voice_runtime.call_actor import CallActor, MediaCallbacks

pytestmark = pytest.mark.dialogue_engine


def test_model_act_applies_to_canonical_turn_without_manufacturing_fact() -> None:
    turn = RichUserTurn(
        utterance_id="u", raw_text="Можно ещё раз?", dialogue_act="answer",
        control="none", answers_pending_question=True, needs_clarification=False,
    )
    candidate = SemanticTurn(
        act=SemanticAct.REPAIR_REQUEST, source_quote=turn.raw_text, confidence=0.99,
    )
    rich, applied, reason = TurnUnderstandingV2().apply_act_candidate(
        turn, candidate, confident=True,
    )
    assert applied and reason == "applied_to_canonical_turn"
    assert rich.dialogue_act == "repair" and not rich.answers_pending_question
    assert not rich.goal_answers and not rich.goal_facts


@pytest.mark.parametrize("confidence,quote,expected", [
    (0.1, "Ага.", "below_confidence_threshold"),
    (0.99, "другая реплика", "candidate_evidence_not_grounded"),
])
def test_candidate_boundary_rejects_untrusted_vote(confidence, quote, expected) -> None:
    turn = RichUserTurn(
        utterance_id="u", raw_text="Ага.", dialogue_act="answer", control="none",
        answers_pending_question=True, needs_clarification=False,
    )
    candidate = SemanticTurn(act=SemanticAct.BACKCHANNEL, source_quote=quote, confidence=confidence)
    rich, applied, reason = TurnUnderstandingV2().apply_act_candidate(
        turn, candidate, confident=True,
    )
    assert not applied and rich == turn and reason == expected


def test_yes_no_answer_cannot_become_backchannel() -> None:
    from packages.dialogue_engine.state import EngineState, Question, QuestionPhase

    state = EngineState(call_id="yes-no")
    state.delivered_question = Question(
        question_id="q", slot="medication", text="Сегодня лекарство приняли?",
        phase=QuestionPhase.DELIVERED,
    )
    turn = RichUserTurn(
        utterance_id="u", raw_text="Ага.", dialogue_act="answer", control="none",
        answers_pending_question=True, needs_clarification=False,
    )
    candidate = SemanticTurn(act=SemanticAct.BACKCHANNEL, source_quote="Ага.", confidence=0.99)
    rich, applied, reason = TurnUnderstandingV2().apply_act_candidate(
        turn, candidate, confident=True, engine_state=state,
    )
    assert not applied and rich == turn and reason == "delivered_yes_no_answer_wins"


def test_sdk_explicit_candidate_uses_same_resolver_as_live() -> None:
    from packages.dialogue_engine.engine import DialogueEngine

    engine = DialogueEngine(call_id="sdk")
    engine.start()
    before = engine.state.model_dump()
    candidate = SemanticTurn(act=SemanticAct.REPAIR_REQUEST, source_quote="Эээ.", confidence=0.99)
    rich = engine.build_rich_turn(
        "Эээ.", utterance_id="u", act_candidate=candidate, candidate_confident=True,
    )
    assert rich.dialogue_act == "repair"
    assert not rich.answers_pending_question
    assert engine.state.model_dump() == before  # Understand remains read-only.


def test_model_not_recalled_paraphrase_reaches_episode_reducer() -> None:
    from packages.dialogue_engine.engine import DialogueEngine

    engine = DialogueEngine(call_id="model-recall")
    engine.start()

    def deliver():
        while (effect := engine.pop_speak_effect()) is not None:
            engine.on_playout_completed(effect.generation, effect.question_id)

    deliver()
    engine.on_user_turn(
        "u1", "Голова болит.",
        rich_turn=engine.build_rich_turn("Голова болит.", utterance_id="u1"),
    )
    deliver()
    text = "Совсем забыл."
    candidate = SemanticTurn(
        act=SemanticAct.ANSWER, source_quote=text, confidence=0.99, not_recalled=True,
    )
    rich = engine.build_rich_turn(
        text, utterance_id="u2", act_candidate=candidate, candidate_confident=True,
    )
    assert rich.not_recalled
    episode = engine.state.issue_episodes[engine.state.active_episode_id]
    attribute = engine.state.pending_episode_attribute
    engine.on_user_turn("u2", text, rich_turn=rich)
    deliver()
    assert episode.unanswered_attributes[attribute] == text
    assert engine.state.pending_episode_attribute not in {"onset", "duration"}


def test_consent_answer_is_protected_from_model_vote() -> None:
    turn = RichUserTurn(
        utterance_id="u", raw_text="Да.", dialogue_act="answer", control="none",
        consent_answer="yes", answers_pending_question=True, needs_clarification=False,
    )
    candidate = SemanticTurn(act=SemanticAct.BACKCHANNEL, source_quote="Да.", confidence=0.99)
    rich, applied, reason = TurnUnderstandingV2().apply_act_candidate(
        turn, candidate, confident=True,
    )
    assert not applied and rich.consent_answer == "yes"
    assert reason == "protected_control_risk_or_question"


@pytest.mark.asyncio
@pytest.mark.parametrize("text,act,expected_used", [
    ("Чувствую себя хорошо.", "backchannel", False),
    ("Голова болит.", "backchannel", False),
    ("Помогите, вызовите скорую.", "backchannel", False),
    ("Не беспокойте меня больше.", "answer", False),
    ("Эээ.", "repeat_request", True),
])
async def test_call_actor_passes_resolved_rich_turn_and_reports_usage(
    monkeypatch: pytest.MonkeyPatch, text: str, act: str, expected_used: bool,
) -> None:
    async def noop(*args, **kwargs):
        return None

    session = CallSession(call_id="sdk-act", family_id="test")
    opening = session.start()
    effect = opening.speak_effect
    assert effect is not None and session._engine is not None
    session._engine.on_playout_completed(effect.generation, effect.question_id)

    async def stt(*args, **kwargs):
        return SimpleNamespace(text=text, asr_quality=AsrQuality.GOOD)

    class FakeActModel:
        def predict(self, *args):
            return ActCandidate(act=act, confidence=0.99, latency_ms=1)

    monkeypatch.setattr(SemanticNLP, "get", classmethod(lambda cls: FakeActModel()))
    events = []

    async def emit(event):
        events.append(event)

    actor = CallActor(
        call_id=session.state.call_id, family_id="test", session=session,
        stt=SimpleNamespace(transcribe_final=stt), tts=SimpleNamespace(cancel=noop),
        llm=SimpleNamespace(), media=MediaCallbacks(noop, noop, noop, emit),
    )
    monkeypatch.setattr(actor, "_deliver_session_turn", noop)
    monkeypatch.setattr(actor, "_relation_shadow_task", noop)
    seen = []
    original = session.handle_user_text

    def capture(*args, **kwargs):
        seen.append(kwargs.get("rich_turn"))
        return original(*args, **kwargs)

    monkeypatch.setattr(session, "handle_user_text", capture)
    await actor._handle_utterance(struct.pack("<h", 1000) * 16000, 1)
    nlp = [
        event.payload for event in events
        if hasattr(event, "payload") and "nlp_act" in event.payload
    ]
    assert nlp and nlp[-1]["proposed"] is True
    assert nlp[-1]["used"] is expected_used, nlp
    assert seen and seen[-1] is not None
    if expected_used:
        assert seen[-1].dialogue_act == "repair"
        assert not seen[-1].answers_pending_question
    elif text == "Чувствую себя хорошо.":
        assert session._engine.state.slot_values["wellness"]
