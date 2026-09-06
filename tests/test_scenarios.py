"""Scenario tests S01–S12 — Phase 2 gate (public_status + dialogue invariants)."""

from packages.contracts.enums import (
    AnswerJudgement,
    CareState,
    ConsentState,
    DeliveryState,
    FsmState,
    PublicCallStatus,
    RiskLevel,
    SlotStatus,
    TechnicalState,
)
from packages.contracts.status import CallStatusSnapshot, SafetySnapshot
from packages.dialogue.planner import Planner
from packages.dialogue.state import DialogueState
from packages.dialogue.validator import Validator
from packages.safety import SafetyEngine
from packages.status import StatusEngine


def _snap(**kwargs) -> CallStatusSnapshot:
    return CallStatusSnapshot(call_id="test", **kwargs)


def _answered_ok(**kwargs) -> CallStatusSnapshot:
    defaults = {
        "delivery_state": DeliveryState.ANSWERED,
        "technical_state": TechnicalState.OK,
        "consent_state": ConsentState.ACTIVE,
    }
    defaults.update(kwargs)
    return _snap(**defaults)


# --- S01: morning check-in all OK → GREEN ---


def test_s01_morning_check_in_green() -> None:
    s = _answered_ok(
        care_state=CareState.GREEN,
        mandatory_checks={
            "identity": True,
            "consent": True,
            "can_talk": True,
            "wellness": True,
        },
    )
    assert StatusEngine.resolve(s) == PublicCallStatus.GREEN


# --- S02: dizziness → YELLOW ---


def test_s02_dizziness_yellow() -> None:
    safety = SafetySnapshot()
    SafetyEngine.ingest_transcript(safety, "голова кружится")
    s = _answered_ok(care_state=CareState.YELLOW, safety=safety)
    assert safety.active_risk == RiskLevel.YELLOW
    assert StatusEngine.resolve(s) == PublicCallStatus.YELLOW


# --- S03: fall + confirm → RED ---


def test_s03_fall_confirmed_red() -> None:
    safety = SafetySnapshot()
    SafetyEngine.ingest_transcript(safety, "я упала и не могу встать")
    SafetyEngine.confirm_red(safety)
    s = _answered_ok(care_state=CareState.RED, safety=safety)
    assert safety.active_risk == RiskLevel.RED
    assert StatusEngine.resolve(s) == PublicCallStatus.RED


# --- S04: do not call again → DECLINED ---


def test_s04_declined() -> None:
    s = _snap(consent_state=ConsentState.DECLINED, delivery_state=DeliveryState.ANSWERED)
    assert StatusEngine.resolve(s) == PublicCallStatus.DECLINED


# --- S05: ring, no answer → NO_CONTACT ---


def test_s05_no_contact() -> None:
    s = _snap(delivery_state=DeliveryState.NOT_ANSWERED, technical_state=TechnicalState.OK)
    assert StatusEngine.resolve(s) == PublicCallStatus.NO_CONTACT


# --- S06: trunk failed before ring → TECHNICAL ---


def test_s06_trunk_failed_technical() -> None:
    s = _snap(delivery_state=DeliveryState.NOT_ATTEMPTED, technical_state=TechnicalState.FAILED)
    assert StatusEngine.resolve(s) == PublicCallStatus.TECHNICAL


# --- S07: answered, STT died → TECHNICAL ---


def test_s07_answered_then_technical() -> None:
    s = _snap(
        delivery_state=DeliveryState.ANSWERED,
        technical_state=TechnicalState.FAILED,
        care_state=CareState.UNKNOWN,
    )
    assert StatusEngine.resolve(s) == PublicCallStatus.TECHNICAL


# --- S08: answered + STT died + active RED → RED wins ---


def test_s08_red_wins_over_technical() -> None:
    safety = SafetySnapshot(active_risk=RiskLevel.RED)
    s = _snap(
        delivery_state=DeliveryState.ANSWERED,
        technical_state=TechnicalState.FAILED,
        care_state=CareState.RED,
        safety=safety,
    )
    assert StatusEngine.resolve(s) == PublicCallStatus.RED


# --- S09: declined + fall → RED wins ---


def test_s09_declined_but_red_is_red() -> None:
    safety = SafetySnapshot(active_risk=RiskLevel.RED)
    s = _snap(
        consent_state=ConsentState.DECLINED,
        delivery_state=DeliveryState.ANSWERED,
        care_state=CareState.RED,
        safety=safety,
    )
    assert StatusEngine.resolve(s) == PublicCallStatus.RED


# --- S10: false alarm protocol → YELLOW, not GREEN ---


def test_s10_false_alarm_clears_active_risk() -> None:
    safety = SafetySnapshot()
    SafetyEngine.ingest_transcript(safety, "я упала")
    assert safety.highest_signal_seen == RiskLevel.RED
    SafetyEngine.resolve_false_alarm(safety)
    assert safety.active_risk == RiskLevel.NONE
    assert safety.highest_signal_seen == RiskLevel.RED


def test_s10_false_alarm_public_status_yellow_not_green() -> None:
    safety = SafetySnapshot()
    SafetyEngine.ingest_transcript(safety, "я упала")
    SafetyEngine.resolve_false_alarm(safety)
    s = _answered_ok(care_state=CareState.UNKNOWN, safety=safety)
    assert StatusEngine.resolve(s) == PublicCallStatus.YELLOW


# --- S11: silence / backchannel → no false GREEN (domain; echo gate is runtime) ---


def test_s11_backchannel_does_not_close_slot_or_green() -> None:
    state = DialogueState(call_id="s11", fsm_state=FsmState.DAILY_CHECK)
    Planner.plan_after_user(
        state,
        user_text="ага",
        judgement=AnswerJudgement.BACKCHANNEL,
        generation_id="g1",
        turn_id=1,
    )
    assert state.slots["wellness"] == SlotStatus.OPEN
    assert "wellness" in state.mandatory_remaining()

    snap = _answered_ok(care_state=CareState.UNKNOWN, mandatory_checks=state.mandatory_checks)
    assert StatusEngine.resolve(snap) == PublicCallStatus.YELLOW
    assert StatusEngine.resolve(snap) != PublicCallStatus.GREEN


def test_s11_no_answer_does_not_close_slot() -> None:
    state = DialogueState(call_id="s11b", fsm_state=FsmState.DAILY_CHECK)
    state.pending_slot = "wellness"
    Planner.plan_after_user(
        state,
        user_text="",
        judgement=AnswerJudgement.NO_ANSWER,
        generation_id="g1",
        turn_id=1,
    )
    assert state.slots["wellness"] == SlotStatus.OPEN


# --- S12: second goodbye → terminal (domain; barge-in playback is runtime) ---


def test_s12_second_goodbye_reaches_terminal() -> None:
    state = DialogueState(call_id="s12", fsm_state=FsmState.SUMMARY)
    for key in state.mandatory_checks:
        state.mandatory_checks[key] = True

    first = Planner.plan_closing(state, "до свидания", turn_id=1, generation_id="g1")
    assert state.goodbye_count == 1
    assert "закончить разговор" in first.speech.lower()
    assert state.fsm_state == FsmState.GOODBYE
    assert Validator.validate(first).allowed is True

    second = Planner.plan_closing(state, "да, до свидания", turn_id=2, generation_id="g2")
    assert state.goodbye_count == 2
    assert state.goodbye_confirmed is True
    assert state.fsm_state == FsmState.FINAL_CLASSIFICATION
    assert Validator.validate(second).allowed is True


# --- ADR-005 regression: mandatory incomplete must not become TECHNICAL ---


def test_mandatory_incomplete_answered_is_yellow_not_technical() -> None:
    s = _answered_ok(
        care_state=CareState.GREEN,
        mandatory_checks={
            "identity": True,
            "consent": True,
            "can_talk": True,
            "wellness": False,
        },
    )
    assert StatusEngine.resolve(s) == PublicCallStatus.YELLOW
    assert StatusEngine.resolve(s) != PublicCallStatus.TECHNICAL
