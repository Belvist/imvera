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


def _planner_session() -> CallSession:
    """Session without DialogueEngine — legacy planner/semantic adapter tests."""
    session = CallSession(
        call_id="wellness-matrix-planner",
        family_id="audit-family",
        elder_display_name="Бабушка",
        store=InMemoryCallRecordStore(),
    )
    session._engine = None
    start = session.start()
    session.state.mandatory_checks.update(identity=True, consent=True, can_talk=True)
    session.state.greeted = True
    session.mark_spoken_action(start.proposal.generation_id)
    assert session.state.pending_slot == "wellness"
    return session


def _daily_session() -> CallSession:
    session = CallSession(
        call_id="wellness-matrix",
        family_id="audit-family",
        elder_display_name="Бабушка",
        store=InMemoryCallRecordStore(),
    )
    if session._engine is None:
        from packages.dialogue_engine.engine import DialogueEngine

        session._engine = DialogueEngine(
            call_id=session.state.call_id,
            elder_display_name=session.state.elder_display_name,
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


def _slots(session: CallSession):
    """Slot map from the owning state: engine on engine path (Cut 4a —
    the legacy mirror is no longer synced on speak turns), legacy else."""
    if session._engine is not None:
        return session._engine.state.slots
    return session.state.slots


def _slot_value(session: CallSession, slot: str) -> str:
    if session._engine is not None:
        return session._engine.state.slot_values.get(slot, "")
    fact = session.state.facts.get(slot)
    return fact.value if fact else ""


def _fsm(session: CallSession):
    if session._engine is not None:
        return session._engine.state.fsm_state
    return session.state.fsm_state


def _mandatory_open(session: CallSession) -> list:
    """Close-readiness: engine slot rule on engine path, legacy else."""
    if session._engine is not None:
        return session._engine.slot_mandatory_remaining()
    return session.state.mandatory_remaining()


def _goodbye_flag(session: CallSession, name: str):
    if session._engine is not None:
        return getattr(session._engine.state, name)
    return getattr(session.state, name)


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
    session = (
        _daily_session()
        if wellness_answer in ("хорошо", "нормально")
        else _planner_session()
    )
    result = _apply_semantic(
        session,
        wellness_answer,
        _payload(
            facts=(_fact(wellness_answer),),
            answers_pending_question=True,
        ),
    )
    assert _slots(session)["wellness"] == SlotStatus.FILLED
    if wellness_answer in ("плохо", "не очень"):
        assert result.proposal.intent == "reflect_report"
    else:
        assert result.proposal.intent == "important_to_share"
    assert wellness_answer in _slot_value(session, "wellness").lower()


@pytest.mark.parametrize("wellness_answer", WELLNESS_MOOD_VARIANTS)
def test_full_daily_check_to_goodbye(wellness_answer: str) -> None:
    """Full pilot flow: four slots → summary → goodbye confirm → goodbye final."""
    session = (
        _daily_session()
        if wellness_answer in ("хорошо", "нормально")
        else _planner_session()
    )
    _apply_semantic(
        session,
        wellness_answer,
        _payload(facts=(_fact(wellness_answer),), answers_pending_question=True),
    )
    _mark_spoken(session)

    if wellness_answer in ("хорошо", "нормально"):
        share_intent = _advance_slot(session, "Ничего.")
        assert share_intent == "summary"
        assert _fsm(session) == FsmState.SUMMARY
        assert _slots(session)["wellness"] == SlotStatus.FILLED
    else:
        mood_answer, sleep_answer, plans_answer = FOLLOW_UP_BY_WELLNESS[wellness_answer]
        mood_intent = _advance_slot(session, mood_answer)
        assert mood_intent == "check_sleep"
        sleep_intent = _advance_slot(session, sleep_answer)
        assert sleep_intent == "reflect_report"
        _advance_slot(session, "угу")
        plans_intent = _advance_slot(session, plans_answer)
        assert plans_intent == "summary"
        assert _fsm(session) == FsmState.SUMMARY
        assert all(
            _slots(session)[s] == SlotStatus.FILLED
            for s in ("wellness", "mood", "sleep", "plans")
        )
        assert _mandatory_open(session) == []

    goodbye = session.handle_user_text("до свидания")
    if goodbye.proposal.intent == "goodbye_final":
        assert _goodbye_flag(session, "goodbye_confirmed") is True
        assert not _goodbye_flag(session, "awaiting_goodbye_confirm")
    else:
        # Legacy planner path still confirms ambiguous closes.
        assert goodbye.proposal.intent == "goodbye_confirm"
        assert _goodbye_flag(session, "awaiting_goodbye_confirm")
        final = session.handle_user_text("да")
        assert final.proposal.intent == "goodbye_final"
        assert _goodbye_flag(session, "goodbye_confirmed") is True
    assert _fsm(session) == FsmState.FINAL_CLASSIFICATION


def test_mixed_answer_and_side_question_preserves_fact() -> None:
    """Stage B P0: fact + side question in one utterance — wellness filled, Vera explains."""
    session = _planner_session()
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
    session = _planner_session()
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
        session = _planner_session()
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
    session = _planner_session()
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
    engine_cases = (
        ("хорошо", "important_to_share"),
        ("нормально", "important_to_share"),
    )
    for phrase, expected_intent in engine_cases:
        session = _daily_session()
        result = session.handle_user_text(phrase)
        assert _slots(session)["wellness"] == SlotStatus.FILLED
        assert result.proposal.intent == expected_intent
    for phrase in ("плохо", "не очень"):
        session = _planner_session()
        result = session.handle_user_text(phrase)
        assert session.state.slots["wellness"] == SlotStatus.FILLED
        assert result.proposal.intent == "reflect_report"
