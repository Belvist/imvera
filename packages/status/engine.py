"""Public status resolution — 4 internal axes → 6 product statuses."""

from packages.contracts.enums import (
    CareState,
    ConsentState,
    DeliveryState,
    PublicCallStatus,
    RiskLevel,
    TechnicalState,
)
from packages.contracts.status import CallStatusSnapshot


class StatusEngine:
    """Pure domain logic. No I/O."""

    @staticmethod
    def resolve(snapshot: CallStatusSnapshot) -> PublicCallStatus:
        """Map internal axes to one of six public statuses (ADR-005)."""
        delivery = snapshot.delivery_state
        technical = snapshot.technical_state
        care = snapshot.care_state
        consent = snapshot.consent_state
        active_risk = snapshot.safety.active_risk

        # Consent decline (after contact or explicit decline flow)
        if consent == ConsentState.DECLINED:
            if active_risk == RiskLevel.RED or care == CareState.RED:
                return PublicCallStatus.RED
            return PublicCallStatus.DECLINED

        # Delivery / technical failures before meaningful contact
        if delivery in (DeliveryState.NOT_ATTEMPTED, DeliveryState.FAILED):
            return PublicCallStatus.TECHNICAL

        if delivery == DeliveryState.NOT_ANSWERED and technical == TechnicalState.OK:
            return PublicCallStatus.NO_CONTACT

        # Active risk / care precedence over technical degradation
        if active_risk == RiskLevel.RED or care == CareState.RED:
            return PublicCallStatus.RED

        if care == CareState.YELLOW or active_risk == RiskLevel.YELLOW:
            return PublicCallStatus.YELLOW

        if technical in (TechnicalState.FAILED, TechnicalState.DEGRADED):
            if delivery == DeliveryState.ANSWERED:
                return PublicCallStatus.TECHNICAL
            return PublicCallStatus.TECHNICAL

        if delivery == DeliveryState.ANSWERED and care == CareState.GREEN:
            if StatusEngine._mandatory_complete(snapshot):
                return PublicCallStatus.GREEN
            if care == CareState.UNKNOWN:
                return PublicCallStatus.YELLOW

        if delivery == DeliveryState.RINGING:
            return PublicCallStatus.TECHNICAL

        return PublicCallStatus.TECHNICAL

    @staticmethod
    def _mandatory_complete(snapshot: CallStatusSnapshot) -> bool:
        checks = snapshot.mandatory_checks
        if not checks:
            return False
        return all(checks.values())

    @staticmethod
    def finalize(snapshot: CallStatusSnapshot) -> CallStatusSnapshot:
        public = StatusEngine.resolve(snapshot)
        snapshot.public_status = public
        return snapshot
