"""Grandmother wellness-call scenario matrix — policy path for tomorrow's Zoiper gate.

Covers Stage B audit items from ``docs/verification/dialogue-current.md`` (base e0e86b0):
mood variants, full slot completion to goodbye, mixed utterance + side question,
complaint mid-call. Semantic payloads model expected LLM output; they do NOT prove
live STT/LLM accuracy.
"""

from __future__ import annotations

import pytest

from packages.contracts.enums import FsmState, SlotStatus
from packages.contracts.semantic import Evidence, FactCandidate, SemanticPayload
from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.context_builder import active_question_kind
from packages.dialogue.semantic_adapter import adapt_semantic_turn
from packages.dialogue.session import CallSession


def _evidence(text: str, quote: str | None = None) -> Evidence:
    q = quote or text
    start = text.index(q)
    return Evidence(start=start, end=start + len(q), quote=q)


def _fact(
    text: str,
    field: str = "wellness",
    quote: str | None = None,
    **kw,
) -> FactCandidate:
    q = quote or text
    return FactCandidate(
        field=field,
        value=q,
        subject="speaker",
        temporal_scope="now",
        negated=False,
        evidence=_evidence(text, q),
        **kw,
    )


def _payload(**changes) -> SemanticPayload:
    base = {
        "dialogue_act": "answer",
        "control": "none",
        "consent_answer": "not_applicable",
        "answers_pending_question": False,
        "needs_clarification": False,
    }
    base.update(changes)
    return SemanticPayload(**base)


def _daily_session() -> CallSession:
    session = CallSession(
        call_id="wellness-matrix",
        family_id="audit-family",
        elder_display_name="Бабушка",
        store=InMemoryCallRecordStore(),
    )
    start = session.start()
    session.state.mandatory_checks.update(identity=True, consent=True, can_talk=True)
    session.state.greeted = True
    session.mark_spoken_action(start.proposal.generation_id)
    assert session.state.pending_slot == "wellness"
    return session


def _apply_semantic(session: CallSession, text: str, payload: SemanticPayload):
    interp, _ = adapt_semantic_turn(
        text,
        payload,
        state=session.state,
        active_question_kind=active_question_kind(session.state),
    )
    return session.handle_user_text(text, interp=interp)


def _mark_spoken(session: CallSession) -> None:
    gen = session.state.pending_action_id
    if gen:
        session.mark_spoken_action(gen)


def _advance_slot(session: CallSession, text: str) -> str:
    result = session.handle_user_text(text)
    _mark_spoken(session)
    return result.proposal.intent


WELLNESS_MOOD_VARIANTS = (
    "хорошо",
    "нормально",
    "не очень",
    "плохо",
)

FOLLOW_UP_BY_WELLNESS = {
    "хорошо": ("хорошее", "спал нормально", "дома посижу"),
    "нормально": ("хорошее", "спал нормально", "дома посижу"),
    "не очень": ("плохое", "спала плохо", "дома"),
    "плохо": ("плохое", "спала плохо", "дома"),
}


@pytest.mark.parametrize("wellness_answer", WELLNESS_MOOD_VARIANTS)
def test_wellness_mood_variant_fills_slot_and_advances(wellness_answer: str) -> None:
    """Stage B P0: elderly mood answers at wellness must fill slot and ask mood next."""
    session = _daily_session()
    result = _apply_semantic(
        session,
        wellness_answer,
        _payload(
            facts=(_fact(wellness_answer),),
            answers_pending_question=True,
        ),
    )
    assert session.state.slots["wellness"] == SlotStatus.FILLED
    if wellness_answer in ("плохо", "не очень"):
        assert result.proposal.intent == "reflect_report"
    else:
        assert result.proposal.intent == "check_mood"
    assert wellness_answer in session.state.facts["wellness"].value.lower()


@pytest.mark.parametrize("wellness_answer", WELLNESS_MOOD_VARIANTS)
def test_full_daily_check_to_goodbye(wellness_answer: str) -> None:
    """Full pilot flow: four slots → summary → goodbye confirm → goodbye final."""
    session = _daily_session()
    mood_answer, sleep_answer, plans_answer = FOLLOW_UP_BY_WELLNESS[wellness_answer]

    _apply_semantic(
        session,
        wellness_answer,
        _payload(facts=(_fact(wellness_answer),), answers_pending_question=True),
    )
    _mark_spoken(session)

    mood_intent = _advance_slot(session, mood_answer)
    assert mood_intent == "check_sleep"

    sleep_intent = _advance_slot(session, sleep_answer)
    if wellness_answer in ("плохо", "не очень"):
        assert sleep_intent == "reflect_report"
        _advance_slot(session, "угу")
    else:
        assert sleep_intent == "check_plans"

    plans_intent = _advance_slot(session, plans_answer)
    assert plans_intent == "summary"
    assert session.state.fsm_state == FsmState.SUMMARY
    assert all(session.state.slots[s] == SlotStatus.FILLED for s in ("wellness", "mood", "sleep", "plans"))
    assert session.state.mandatory_remaining() == []

    goodbye = session.handle_user_text("до свидания")
    assert goodbye.proposal.intent == "goodbye_confirm"
    assert session.state.awaiting_goodbye_confirm

    final = session.handle_user_text("да")
    assert final.proposal.intent == "goodbye_final"
    assert session.state.goodbye_confirmed is True
    assert session.state.fsm_state == FsmState.FINAL_CLASSIFICATION


def test_mixed_answer_and_side_question_preserves_fact() -> None:
    """Stage B P0: fact + side question in one utterance — wellness filled, Vera explains."""
    session = _daily_session()
    text = "Чувствую себя хорошо. А зачем вы спрашиваете?"
    result = _apply_semantic(
        session,
        text,
        _payload(
            dialogue_act="question",
            user_question="А зачем вы спрашиваете?",
            facts=(_fact(text, quote="Чувствую себя хорошо"),),
            answers_pending_question=True,
        ),
    )
    assert session.state.slots["wellness"] == SlotStatus.FILLED
    assert result.proposal.intent == "explain_vera"
    assert "Вера" in result.proposal.speech


def test_complaint_at_wellness_reflects_without_praise() -> None:
    """Stage B P0: complaint «голова болит» mirrors pain, no praise, no new question."""
    session = _daily_session()
    text = "Голова болит с утра"
    result = _apply_semantic(
        session,
        text,
        _payload(facts=(_fact(text),), answers_pending_question=True),
    )
    assert session.state.slots["wellness"] == SlotStatus.FILLED
    assert result.proposal.intent == "reflect_report"
    speech = result.proposal.speech.lower()
    assert "болит" in speech
    assert "отлично" not in speech
    assert "?" not in result.proposal.speech


def test_negative_wellness_semantic_reflects_without_praise() -> None:
    """плохо / не очень via semantic path — empathy reflection before next slot."""
    for phrase in ("плохо", "не очень"):
        session = _daily_session()
        result = _apply_semantic(
            session,
            phrase,
            _payload(facts=(_fact(phrase),), answers_pending_question=True),
        )
        assert session.state.slots["wellness"] == SlotStatus.FILLED
        assert result.proposal.intent == "reflect_report"
        assert phrase.split()[0] in result.proposal.speech.lower()
        assert "?" not in result.proposal.speech


def test_complaint_mid_call_after_wellness_reflects_without_praise() -> None:
    """Complaint during mood slot — reflect_report, no praise, slot flow continues."""
    session = _daily_session()
    _apply_semantic(
        session,
        "нормально",
        _payload(facts=(_fact("нормально"),), answers_pending_question=True),
    )
    _mark_spoken(session)
    assert session.state.pending_slot == "mood"

    text = "Голова болит"
    result = _apply_semantic(
        session,
        text,
        _payload(facts=(_fact(text),), answers_pending_question=True),
    )
    assert result.proposal.intent == "reflect_report"
    assert "болит" in result.proposal.speech.lower()
    assert "отлично" not in result.proposal.speech.lower()
    assert session.state.slots["mood"] == SlotStatus.OPEN


def test_rule_baseline_wellness_short_answers_still_work() -> None:
    """Baseline interpreter path (no semantic payload) for common grandmother phrases."""
    for phrase, expected_intent in (
        ("хорошо", "check_mood"),
        ("нормально", "check_mood"),
        ("плохо", "reflect_report"),
        ("не очень", "reflect_report"),
    ):
        session = _daily_session()
        result = session.handle_user_text(phrase)
        assert session.state.slots["wellness"] == SlotStatus.FILLED
        assert result.proposal.intent == expected_intent
