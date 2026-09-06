"""Contract schema smoke tests — Phase 1 gate."""

from datetime import UTC, datetime

from packages.contracts import (
    CallEvent,
    CallStatusSnapshot,
    DeliveryState,
    EventTypes,
    FsmState,
    PublicCallStatus,
    RiskLevel,
    STTResult,
    TechnicalState,
    TurnProposal,
)


def test_turn_proposal_roundtrip() -> None:
    t = TurnProposal(
        turn_id=1,
        generation_id="g-1",
        speech="Здравствуйте.",
        intent="greeting",
        fsm_state=FsmState.GREETING,
    )
    data = t.model_dump()
    assert TurnProposal.model_validate(data).speech == "Здравствуйте."


def test_call_event_frozen() -> None:
    evt = CallEvent(
        event_id="evt-1",
        call_id="call-1",
        sequence_no=1,
        occurred_at=datetime.now(UTC),
        event_type=EventTypes.CALL_STARTED,
        idempotency_key="call-1:1",
    )
    assert evt.event_type == "CALL_STARTED"


def test_status_snapshot_axes() -> None:
    snap = CallStatusSnapshot(
        call_id="call-1",
        delivery_state=DeliveryState.ANSWERED,
        technical_state=TechnicalState.FAILED,
    )
    snap.safety.active_risk = RiskLevel.RED
    assert snap.delivery_state == DeliveryState.ANSWERED
    assert snap.safety.active_risk == RiskLevel.RED


def test_public_status_enum() -> None:
    assert PublicCallStatus.TECHNICAL != PublicCallStatus.GREEN
    assert len(PublicCallStatus) == 6


def test_stt_result_defaults() -> None:
    r = STTResult(text="привет", asr_quality="GOOD")
    assert r.is_final is True
