"""Public status resolution — 4 internal axes → 6 product statuses."""

from packages.contracts.enums import (
    CareState,
    ConsentState,
    DeliveryState,
    PublicCallStatus,
    RiskLevel,
    TechnicalState,
)
from packages.contracts.mandatory import PILOT_MANDATORY_CHECKS
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

        if delivery in (DeliveryState.NOT_ATTEMPTED, DeliveryState.FAILED):
            return PublicCallStatus.TECHNICAL

        if delivery == DeliveryState.NOT_ANSWERED and technical == TechnicalState.OK:
            return PublicCallStatus.NO_CONTACT

        if active_risk == RiskLevel.RED or care == CareState.RED:
            return PublicCallStatus.RED

        if care == CareState.YELLOW or active_risk == RiskLevel.YELLOW:
            return PublicCallStatus.YELLOW

        if active_risk == RiskLevel.POSSIBLE:
            return PublicCallStatus.YELLOW

        if consent == ConsentState.DECLINED:
            return PublicCallStatus.DECLINED

        if technical in (TechnicalState.FAILED, TechnicalState.DEGRADED):
            return PublicCallStatus.TECHNICAL

        if delivery == DeliveryState.RINGING:
            return PublicCallStatus.TECHNICAL

        if delivery == DeliveryState.ANSWERED and technical == TechnicalState.OK:
            if care == CareState.GREEN and StatusEngine._mandatory_complete(snapshot):
                return PublicCallStatus.GREEN
            return PublicCallStatus.YELLOW

        return PublicCallStatus.TECHNICAL

    @staticmethod
    def _mandatory_complete(snapshot: CallStatusSnapshot) -> bool:
        checks = snapshot.mandatory_checks
        if not checks:
            return False
        return all(checks.get(key, False) for key in PILOT_MANDATORY_CHECKS)

    @staticmethod
    def finalize(snapshot: CallStatusSnapshot) -> CallStatusSnapshot:
        public = StatusEngine.resolve(snapshot)
        snapshot.public_status = public
        return snapshot
