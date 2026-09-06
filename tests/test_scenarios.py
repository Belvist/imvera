"""Scenario tests S01–S12 — assert public_status (Phase 2 gate)."""

from packages.contracts.enums import (
    CareState,
    ConsentState,
    DeliveryState,
    PublicCallStatus,
    RiskLevel,
    TechnicalState,
)
from packages.contracts.status import CallStatusSnapshot, SafetySnapshot
from packages.safety import SafetyEngine
from packages.status import StatusEngine


def _snap(**kwargs) -> CallStatusSnapshot:
    return CallStatusSnapshot(call_id="test", **kwargs)


def test_s05_no_contact() -> None:
    s = _snap(delivery_state=DeliveryState.NOT_ANSWERED, technical_state=TechnicalState.OK)
    assert StatusEngine.resolve(s) == PublicCallStatus.NO_CONTACT


def test_s06_trunk_failed_technical() -> None:
    s = _snap(delivery_state=DeliveryState.NOT_ATTEMPTED, technical_state=TechnicalState.FAILED)
    assert StatusEngine.resolve(s) == PublicCallStatus.TECHNICAL


def test_s07_answered_then_technical() -> None:
    s = _snap(
        delivery_state=DeliveryState.ANSWERED,
        technical_state=TechnicalState.FAILED,
        care_state=CareState.UNKNOWN,
    )
    assert StatusEngine.resolve(s) == PublicCallStatus.TECHNICAL


def test_s08_red_wins_over_technical() -> None:
    safety = SafetySnapshot(active_risk=RiskLevel.RED)
    s = _snap(
        delivery_state=DeliveryState.ANSWERED,
        technical_state=TechnicalState.FAILED,
        care_state=CareState.RED,
        safety=safety,
    )
    assert StatusEngine.resolve(s) == PublicCallStatus.RED


def test_s04_declined() -> None:
    s = _snap(consent_state=ConsentState.DECLINED, delivery_state=DeliveryState.ANSWERED)
    assert StatusEngine.resolve(s) == PublicCallStatus.DECLINED


def test_s09_declined_but_red_is_red() -> None:
    safety = SafetySnapshot(active_risk=RiskLevel.RED)
    s = _snap(
        consent_state=ConsentState.DECLINED,
        delivery_state=DeliveryState.ANSWERED,
        care_state=CareState.RED,
        safety=safety,
    )
    assert StatusEngine.resolve(s) == PublicCallStatus.RED


def test_s01_green() -> None:
    s = _snap(
        delivery_state=DeliveryState.ANSWERED,
        technical_state=TechnicalState.OK,
        care_state=CareState.GREEN,
        consent_state=ConsentState.ACTIVE,
        mandatory_checks={
            "identity": True,
            "consent": True,
            "can_talk": True,
            "wellness": True,
        },
    )
    assert StatusEngine.resolve(s) == PublicCallStatus.GREEN


def test_s03_red_via_safety_engine() -> None:
    safety = SafetySnapshot()
    SafetyEngine.ingest_transcript(safety, "я упала и не могу встать")
    s = _snap(
        delivery_state=DeliveryState.ANSWERED,
        technical_state=TechnicalState.OK,
        care_state=CareState.RED,
        safety=safety,
    )
    assert safety.active_risk == RiskLevel.RED
    assert StatusEngine.resolve(s) == PublicCallStatus.RED


def test_s10_false_alarm_clears_active_risk() -> None:
    safety = SafetySnapshot()
    SafetyEngine.ingest_transcript(safety, "я упала")
    assert safety.highest_signal_seen == RiskLevel.RED
    SafetyEngine.resolve_false_alarm(safety)
    assert safety.active_risk == RiskLevel.NONE
    assert safety.highest_signal_seen == RiskLevel.RED
