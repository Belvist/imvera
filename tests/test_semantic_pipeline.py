"""Semantic pipeline — validator, policy, adapter."""

from packages.contracts.enums import FsmState, SlotStatus
from packages.contracts.semantic import Evidence, FactCandidate, SemanticPayload
from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.context_builder import active_question_kind
from packages.dialogue.semantic_adapter import adapt_semantic_turn
from packages.dialogue.semantic_validator import SemanticValidator
from packages.dialogue.session import CallSession


def _evidence(text: str, quote: str | None = None) -> Evidence:
    q = quote or text
    start = text.index(q)
    return Evidence(start=start, end=start + len(q), quote=q)


def _fact(text: str, field: str = "wellness", quote: str | None = None, **kw) -> FactCandidate:
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
        call_id="semantic-pipe",
        family_id="audit-family",
        elder_display_name="Даниил",
        store=InMemoryCallRecordStore(),
    )
    session.start()
    start_gen = session.state.pending_action_id
    if start_gen:
        session.mark_spoken_action(start_gen)
    return session


def test_validator_rejects_span_mismatch() -> None:
    text = "голова болит"
    payload = _payload(
        facts=(
            FactCandidate(
                field="wellness",
                value="устала",
                subject="speaker",
                temporal_scope="now",
                negated=False,
                evidence=Evidence(start=0, end=5, quote="фантазия"),
            ),
        ),
    )
    result = SemanticValidator.validate(
        text, payload, active_question_kind="slot", pending_slot="wellness"
    )
    assert len(result.payload.facts) == 0
    assert any(r.reason == "evidence_span_mismatch" for r in result.rejected_facts)


def test_adapter_complaint_reflection_not_praise() -> None:
    session = _daily_session()
    text = "Голова болит с утра"
    payload = _payload(
        facts=(_fact(text),),
        answers_pending_question=True,
    )
    interp, _ = adapt_semantic_turn(
        text,
        payload,
        state=session.state,
        active_question_kind=active_question_kind(session.state),
    )
    result = session.handle_user_text(text, interp=interp)
    assert session.state.slots["wellness"] == SlotStatus.FILLED
    assert result.proposal.intent == "reflect_report"
    assert "болит" in result.proposal.speech.lower()
    assert "отлично" not in result.proposal.speech.lower()
    assert "?" not in result.proposal.speech
    assert result.validated.allowed


def test_adapter_mixed_sleep_and_who_are_you() -> None:
    session = _daily_session()
    text = "Плохо спала. А вы кто?"
    payload = _payload(
        dialogue_act="question",
        user_question="А вы кто?",
        facts=(_fact(text, field="sleep", quote="Плохо спала"),),
    )
    interp, _ = adapt_semantic_turn(
        text,
        payload,
        state=session.state,
        active_question_kind=active_question_kind(session.state),
    )
    result = session.handle_user_text(text, interp=interp)
    assert session.state.slots["sleep"] == SlotStatus.FILLED
    assert result.proposal.intent == "explain_vera"
    assert "Вера" in result.proposal.speech


def test_identity_yes_binds_with_evidence() -> None:
    session = CallSession(call_id="identity-yes", family_id="audit-family")
    session.state.fsm_state = FsmState.IDENTIFY_PERSON
    session.state.mandatory_checks["identity"] = False
    session.state.pending_question = "Я разговариваю с Даниил?"
    session.state.pending_question_delivered = True
    text = "Да."
    payload = _payload(dialogue_act="answer", consent_answer="not_applicable")
    interp, _ = adapt_semantic_turn(
        text,
        payload,
        state=session.state,
        active_question_kind="identity",
    )
    result = session.handle_user_text(text, interp=interp)
    assert session.state.mandatory_checks.get("identity") is True
    assert result.proposal.fsm_state != FsmState.IDENTIFY_PERSON
    session = CallSession(call_id="consent-bc", family_id="audit-family")
    session.state.fsm_state = FsmState.CHECK_CONSENT
    session.state.mandatory_checks["consent"] = False
    text = "ага"
    payload = _payload(
        dialogue_act="backchannel",
        consent_answer="yes",
        consent_evidence=_evidence(text),
        answers_pending_question=True,
    )
    interp, validated = adapt_semantic_turn(
        text,
        payload,
        state=session.state,
        active_question_kind="consent",
    )
    result = session.handle_user_text(text, interp=interp)
    assert session.state.mandatory_checks.get("consent") is not True
