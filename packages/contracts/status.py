"""Status snapshot — 4 axes + safety sub-state."""

from pydantic import BaseModel, Field

from packages.contracts.enums import (
    CareState,
    ConsentState,
    DeliveryState,
    PublicCallStatus,
    RiskLevel,
    SignalResolution,
    TechnicalState,
)


class SafetySnapshot(BaseModel):
    highest_signal_seen: RiskLevel = RiskLevel.NONE
    active_risk: RiskLevel = RiskLevel.NONE
    signal_resolution: SignalResolution = SignalResolution.UNRESOLVED
    active_episode_id: str | None = None
    dismissed_episode_ids: list[str] = Field(default_factory=list)
    episode_levels: dict[str, RiskLevel] = Field(default_factory=dict)
    episode_seq: int = 0


class CallStatusSnapshot(BaseModel):
    call_id: str
    delivery_state: DeliveryState = DeliveryState.NOT_ATTEMPTED
    technical_state: TechnicalState = TechnicalState.OK
    care_state: CareState = CareState.UNKNOWN
    consent_state: ConsentState = ConsentState.UNKNOWN
    safety: SafetySnapshot = Field(default_factory=SafetySnapshot)
    mandatory_checks: dict[str, bool] = Field(default_factory=dict)
    # Subset of PILOT_MANDATORY_CHECKS gating GREEN in THIS call's mode.
    # None/empty = all (backward compatible). Short mode excludes bg goals
    # the mission never required; full mode includes them.
    required_checks: list[str] | None = None
    public_status: PublicCallStatus | None = None
