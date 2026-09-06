"""Product integrity — dialogue + persistence acceptance from e599c52 audit."""

from packages.contracts.core import DeliveryStage, TerminationReason
from packages.contracts.enums import FsmState, SlotStatus
from packages.contracts.enums import FsmState as FS
from packages.contracts.turn import TurnProposal
from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.session import CallSession
from packages.dialogue.validator import Validator


def _full_session(call_id: str = "integrity") -> CallSession:
    store = InMemoryCallRecordStore()
    session = CallSession(call_id=call_id, family_id="fam-integrity", store=store)
    session.start()
    session.handle_user_text("да")
    session.handle_user_text("да")
    session.handle_user_text("да")
    session.handle_user_text("да")
    return session


def test_mood_good_does_not_overwrite_wellness() -> None:
    session = _full_session()
    session.handle_user_text("нормально")
    assert session.state.slots["wellness"] == SlotStatus.FILLED
    assert session.state.pending_slot == "mood"
    session.handle_user_text("хорошо")
    assert session.state.slots["mood"] == SlotStatus.FILLED
    assert session.state.slots["wellness"] == SlotStatus.FILLED
    assert session.state.facts["mood"].field == "mood"


def test_risk_revoke_after_confirm_not_red_clarified() -> None:
    session = _full_session()
    session.handle_user_text("я упала и не могу встать")
    assert session.state.fsm_state == FsmState.RED_SIGNAL
    session.handle_user_text("да")
    assert session.state.fsm_state == FsmState.CONFIRM_SITUATION
    result = session.handle_user_text("Не звоните мне больше")
    assert result.proposal.intent == "revoke_consent_final"
    assert "передана" not in result.validated.speech.lower()
    assert session.state.termination_reason == TerminationReason.CONSENT_REVOKED


def test_risk_goodbye_after_confirm() -> None:
    session = _full_session()
    session.handle_user_text("я упала и не могу встать")
    session.handle_user_text("да")
    result = session.handle_user_text("до свидания")
    assert result.proposal.intent in ("goodbye_confirm", "goodbye_final")
    assert result.proposal.intent != "red_clarified"


def test_risk_neighbor_correction() -> None:
    session = _full_session()
    session.handle_user_text("я упала и не могу встать")
    session.handle_user_text("да")
    result = session.handle_user_text("нет, это было про соседку")
    assert result.proposal.intent == "red_false_alarm"
    assert session.safety.active_risk.value == "NONE"


def test_single_call_ended_event() -> None:
    store = InMemoryCallRecordStore()
    session = CallSession(call_id="ended-once", family_id="fam-integrity", store=store)
    session.start()
    session.handle_user_text("да")
    session.handle_user_text("нет, не согласен")
    session.handle_user_text("алло")
    session.handle_user_text("ещё раз")
    events = store.get_events("ended-once", "fam-integrity")
    ended = [e for e in events if e.event_type == "CALL_ENDED"]
    assert len(ended) == 1


def test_finalize_preserves_family_and_state() -> None:
    store = InMemoryCallRecordStore()
    session = CallSession(call_id="finalize", family_id="fam-42", store=store)
    session.start()
    session.handle_user_text("да")
    session.handle_user_text("нет, не согласен")
    result = session.get_persisted_result()
    assert result is not None
    assert result.family_id == "fam-42"
    assert result.call_ended is True
    assert result.fsm_state == FsmState.FINAL_CLASSIFICATION
    assert result.termination_reason == TerminationReason.CONSENT_DECLINED
    assert result.delivery_stage == DeliveryStage.PERSISTED


def test_wrong_family_cannot_read() -> None:
    store = InMemoryCallRecordStore()
    session = CallSession(call_id="fam-gate", family_id="fam-a", store=store)
    session.start()
    session.handle_user_text("да")
    session.handle_user_text("нет, не согласен")
    assert store.get_call_result("fam-gate", "fam-b") is None


def test_validator_blocks_unconfirmed_delivery_any_intent() -> None:
    proposal = TurnProposal(
        turn_id=1,
        generation_id="g1",
        speech="Уведомление доставлено семье.",
        intent="red_clarified",
        fsm_state=FS.CONFIRM_SITUATION,
        mandatory_remaining=[],
    )
    validated = Validator.validate(proposal)
    assert validated.allowed is False


def test_say_returns_empty_when_validator_blocks() -> None:
    session = CallSession(call_id="say", family_id="fam-test")
    session.start()
    session.state.fsm_state = FsmState.FINAL_CLASSIFICATION
    session.state.goodbye_confirmed = True
    session.state.call_finalized = True
    assert session.say("алло") == ""


def test_risk_observation_persisted() -> None:
    store = InMemoryCallRecordStore()
    session = CallSession(call_id="risk-obs", family_id="fam-integrity", store=store)
    session.start()
    session.handle_user_text("да")
    session.handle_user_text("да")
    session.handle_user_text("да")
    session.handle_user_text("я упала и не могу встать")
    result = session.get_persisted_result()
    assert result is not None
    assert len(result.observations) >= 1
