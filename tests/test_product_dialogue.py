"""Product dialogue regression tests — Phase A fixes on e599c52 audit."""

from packages.contracts.core import DeliveryStage
from packages.contracts.enums import FsmState, RiskLevel, SlotStatus
from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.session import CallSession


def _session_through_wellness() -> CallSession:
    session = CallSession(call_id="audit", family_id="fam-test")
    start = session.start()
    session.state.mandatory_checks.update(
        {"identity": True, "consent": True, "can_talk": True}
    )
    session.state.greeted = True
    session.mark_spoken_action(start.proposal.generation_id)
    assert session.state.pending_slot == "wellness"
    return session


def _session_at_mood() -> CallSession:
    session = _session_through_wellness()
    result = session.handle_user_text("нормально")
    session.mark_spoken_action(result.proposal.generation_id)
    assert session.state.pending_slot == "mood"
    return session


# --- Prior audit regressions ---


def test_film_sentence_does_not_fill_wellness() -> None:
    session = _session_through_wellness()
    session.handle_user_text("Вчера смотрела интересный фильм вечером")
    assert session.state.slots["wellness"] == SlotStatus.OPEN


def test_poka_vse_horosho_fills_wellness_not_goodbye() -> None:
    session = _session_through_wellness()
    result = session.handle_user_text("Пока всё хорошо")
    assert session.state.slots["wellness"] == SlotStatus.FILLED
    assert result.proposal.intent == "check_mood"


def test_multi_fact_phrase_fills_wellness_sleep_plans() -> None:
    session = _session_through_wellness()
    session.handle_user_text("Чувствую себя хорошо, только плохо спала, весь день буду дома")
    assert session.state.slots["wellness"] == SlotStatus.FILLED
    assert session.state.slots["sleep"] == SlotStatus.FILLED
    assert session.state.slots["plans"] == SlotStatus.FILLED
    assert "спал" in session.state.facts["sleep"].value.lower()
    assert session.state.facts["sleep"].field == "sleep"


def test_sleep_correction_not_mood_when_mood_pending() -> None:
    session = _session_at_mood()
    session.handle_user_text("спала плохо")
    assert session.state.slots["sleep"] == SlotStatus.FILLED
    assert session.state.slots["mood"] == SlotStatus.OPEN
    assert session.state.facts["sleep"].field == "sleep"


def test_turn_contract_state_version_before_mutation() -> None:
    session = _session_through_wellness()
    before = session.state.state_version
    result = session.handle_user_text("Отлично")
    assert result.turn_contract.state_version == before
    assert session.state.state_version > before


def test_safety_snapshot_immutable_per_turn() -> None:
    session = _session_through_wellness()
    r1 = session.handle_user_text("я упала и не могу встать")
    risk_after_fall = r1.safety.active_risk
    assert risk_after_fall == RiskLevel.RED
    r2 = session.handle_user_text("алло")
    assert r1.safety.active_risk == RiskLevel.RED
    assert r2.safety.active_risk == RiskLevel.RED


def test_red_turn_not_hijacked_by_slot_unclear() -> None:
    session = _session_through_wellness()
    result = session.handle_user_text("я упала и не могу встать")
    assert session.state.fsm_state == FsmState.RED_SIGNAL
    assert result.proposal.intent == "red_confirm_safety"
    assert "помощ" not in result.validated.speech.lower()
    follow = session.handle_user_text("да")
    assert follow.proposal.intent in ("red_clarify_confirm", "red_confirm_safety")


def test_facts_persisted_to_store() -> None:
    store = InMemoryCallRecordStore()
    session = CallSession(call_id="persist", family_id="fam-1", store=store)
    start = session.start()
    session.state.mandatory_checks.update({"identity": True, "consent": True, "can_talk": True})
    session.state.greeted = True
    session.mark_spoken_action(start.proposal.generation_id)
    session.handle_user_text("нормально")
    result = session.get_persisted_result()
    assert result is not None
    assert result.family_id == "fam-1"
    assert "wellness" in result.facts
    session.handle_user_text("не звоните больше")
    final = session.get_persisted_result()
    assert final is not None
    assert final.delivery_stage == DeliveryStage.PERSISTED
    assert final.call_ended is True


def test_terminal_allo_no_repeat_goodbye() -> None:
    session = CallSession(call_id="term", family_id="fam-test")
    session.start()
    session.state.fsm_state = FsmState.FINAL_CLASSIFICATION
    session.state.goodbye_confirmed = True
    session.state.final_action_done = True
    result = session.handle_user_text("алло")
    assert result.proposal.intent == "terminal_noop"


def test_interpreter_provider_in_path() -> None:
    session = CallSession(call_id="interp", family_id="fam-test")
    assert session.interpreter.provider_name == "rule_baseline_v1"
