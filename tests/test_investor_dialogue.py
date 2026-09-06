"""Investor dialogue corpus — audit regressions via CallSession public API."""

from packages.contracts.enums import FsmState, SlotStatus
from packages.dialogue.fsm import CallFsm
from packages.dialogue.planner import Planner
from packages.dialogue.session import CallSession
from packages.dialogue.state import DialogueState


def _wellness_pending_state() -> DialogueState:
    state = DialogueState(call_id="wellness", fsm_state=FsmState.DAILY_CHECK)
    state.mandatory_checks.update(
        {"identity": True, "consent": True, "can_talk": True, "greeted": True}
    )
    state.greeted = True
    Planner.plan_vera_turn(state, 1, "g1")
    assert state.pending_slot == "wellness"
    return state


def _session_through_wellness() -> CallSession:
    session = CallSession(call_id="audit", family_id="fam-test")
    session.start()
    session.state.mandatory_checks.update(
        {"identity": True, "consent": True, "can_talk": True}
    )
    session.state.greeted = True
    session.state.fsm_state = FsmState.DAILY_CHECK
    Planner.plan_vera_turn(session.state, 2, "g2")
    assert session.state.pending_slot == "wellness"
    return session


# --- Audit table from engineering spec ---


def test_film_sentence_does_not_fill_wellness() -> None:
    session = _session_through_wellness()
    result = session.handle_user_text("Вчера смотрела интересный фильм вечером")
    assert session.state.slots["wellness"] == SlotStatus.OPEN
    assert session.state.pending_slot == "wellness"
    assert result.proposal.intent in ("check_wellness", "explain_vera_resume", "repeat_wellness")


def test_poka_vse_horosho_fills_wellness_not_goodbye() -> None:
    session = _session_through_wellness()
    result = session.handle_user_text("Пока всё хорошо")
    assert session.state.slots["wellness"] == SlotStatus.FILLED
    assert "wellness" in session.state.facts
    assert result.proposal.intent == "check_mood"
    assert result.proposal.intent != "goodbye_confirm"


def test_who_are_you_gets_explanation() -> None:
    session = _session_through_wellness()
    result = session.handle_user_text("Кто вы такая?")
    assert session.state.slots["wellness"] == SlotStatus.OPEN
    assert result.proposal.intent == "explain_vera_resume"
    assert "Вера" in result.validated.speech
    assert "чувствуете" in result.validated.speech.lower()


def test_mne_nehorosho_fills_wellness() -> None:
    session = _session_through_wellness()
    session.handle_user_text("Мне нехорошо")
    assert session.state.slots["wellness"] == SlotStatus.FILLED
    assert "нехорошо" in session.state.facts["wellness"].value.lower()


def test_otlichno_fills_wellness() -> None:
    session = _session_through_wellness()
    session.handle_user_text("Отлично")
    assert session.state.slots["wellness"] == SlotStatus.FILLED


def test_negated_positive_wellness_accepted() -> None:
    session = _session_through_wellness()
    session.handle_user_text("Нет, чувствую себя хорошо")
    assert session.state.slots["wellness"] == SlotStatus.FILLED


def test_revoke_consent_from_daily_check() -> None:
    session = _session_through_wellness()
    result = session.handle_user_text("Не звоните мне больше")
    assert session.state.call_revoked is True
    assert session.state.fsm_state == FsmState.FINAL_CLASSIFICATION
    assert result.proposal.intent == "revoke_consent_final"


def test_ne_seychas_defers_not_repeat_can_talk() -> None:
    session = CallSession(call_id="defer", family_id="fam-test")
    session.start()
    session.state.fsm_state = FsmState.CHECK_CAN_TALK
    result = session.handle_user_text("не сейчас")
    assert session.state.call_deferred is True
    assert session.state.fsm_state == FsmState.FINAL_CLASSIFICATION
    assert result.proposal.intent == "defer_call_final"
    assert session.state.consent_declined is False
    assert session.state.call_revoked is False


def test_wrong_number_ends_identify() -> None:
    session = CallSession(call_id="wrong", family_id="fam-test")
    session.start()
    result = session.handle_user_text("нет, вы ошиблись номером")
    assert session.state.wrong_person is True
    assert session.state.fsm_state == FsmState.FINAL_CLASSIFICATION
    assert result.proposal.intent == "wrong_person_final"


def test_da_vy_chto_not_consent() -> None:
    session = CallSession(call_id="consent", family_id="fam-test")
    session.start()
    session.state.fsm_state = FsmState.CHECK_CONSENT
    session.handle_user_text("да вы что")
    assert session.state.mandatory_checks["consent"] is False
    assert session.state.fsm_state == FsmState.CHECK_CONSENT


def test_terminal_allo_no_repeat_goodbye() -> None:
    session = CallSession(call_id="term", family_id="fam-test")
    session.start()
    session.state.fsm_state = FsmState.FINAL_CLASSIFICATION
    session.state.goodbye_confirmed = True
    result = session.handle_user_text("алло")
    assert result.proposal.intent == "terminal_noop"
    assert result.validated.speech == ""


def test_red_interrupt_gets_product_compliant_prompt() -> None:
    state = DialogueState(call_id="red")
    state.fsm_state = FsmState.DAILY_CHECK
    CallFsm.interrupt_red(state, source_quote="я упала")
    proposal = Planner.plan_vera_turn(state, 1, "g1")
    assert proposal.intent == "red_confirm_safety"
    assert "передам" in proposal.speech.lower()
    assert "помощ" not in proposal.speech.lower()


def test_multi_fact_phrase_stores_wellness() -> None:
    session = _session_through_wellness()
    session.handle_user_text("Чувствую себя хорошо, только плохо спала, весь день буду дома")
    assert session.state.slots["wellness"] == SlotStatus.FILLED
    assert session.state.slots["sleep"] == SlotStatus.FILLED
