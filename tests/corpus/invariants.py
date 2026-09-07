"""Hard dialogue invariants — fail the corpus run when broken."""

from __future__ import annotations

import re

from packages.contracts.enums import (
    CareState,
    ConsentState,
    DeliveryState,
    PublicCallStatus,
    SlotStatus,
    TechnicalState,
)
from packages.contracts.status import CallStatusSnapshot, SafetySnapshot
from packages.dialogue.session import CallSession
from packages.status.engine import StatusEngine

_BACKCHANNEL_ONLY = re.compile(
    r"^\s*(ага|угу|мгм|м-м|мм|алло)\s*[.!?…]*\s*$",
    re.I,
)
_EMPTY_OR_NOISE = re.compile(
    r"^(\s*|\.+|…+|[,;!?]+|шум+(\s+шум)*|xxx+|###+|asdf+|ааа+|эээ+)\s*$",
    re.I,
)


def is_backchannel_only(text: str) -> bool:
    return bool(_BACKCHANNEL_ONLY.match(text.strip()))


def is_empty_or_noise(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    return bool(_EMPTY_OR_NOISE.match(stripped))


def check_turn_invariants(
    session: CallSession,
    user_text: str,
    slots_before: dict[str, SlotStatus],
    *,
    recent_speeches: list[str],
) -> list[str]:
    """Return human-readable hard failures for one turn."""
    errors: list[str] = []
    pending = session.state.pending_slot

    if is_backchannel_only(user_text) and pending:
        if session.state.slots.get(pending) == SlotStatus.FILLED and slots_before.get(
            pending
        ) != SlotStatus.FILLED:
            errors.append(
                f"HARD: backchannel {user_text!r} filled pending slot {pending}"
            )

    if is_empty_or_noise(user_text):
        for slot, status in session.state.slots.items():
            if status == SlotStatus.FILLED and slots_before.get(slot) != SlotStatus.FILLED:
                errors.append(
                    f"HARD: empty/noise {user_text!r} filled slot {slot}"
                )

    # Forbidden loop: identical Vera speech 3+ times while pending slot still OPEN.
    # Product gate: no 3+ identical wellness (or other) questions in one call.
    if len(recent_speeches) >= 3:
        last3 = [s.strip() for s in recent_speeches[-3:]]
        if last3[0] and len(set(last3)) == 1 and "?" in last3[0]:
            if pending and session.state.slots.get(pending) == SlotStatus.OPEN:
                errors.append(
                    f"HARD: identical question x3 while {pending} OPEN: {last3[0][:80]!r}"
                )

    return errors


def check_status_invariants() -> list[str]:
    """TECHNICAL / NO_CONTACT must never resolve as GREEN."""
    errors: list[str] = []
    cases = [
        (
            "FAILED delivery",
            CallStatusSnapshot(
                call_id="inv-failed",
                delivery_state=DeliveryState.FAILED,
                technical_state=TechnicalState.OK,
                care_state=CareState.GREEN,
                consent_state=ConsentState.ACTIVE,
                safety=SafetySnapshot(),
                mandatory_checks={
                    "identity": True,
                    "consent": True,
                    "can_talk": True,
                },
            ),
            PublicCallStatus.TECHNICAL,
        ),
        (
            "NOT_ANSWERED",
            CallStatusSnapshot(
                call_id="inv-nocontact",
                delivery_state=DeliveryState.NOT_ANSWERED,
                technical_state=TechnicalState.OK,
                care_state=CareState.GREEN,
                consent_state=ConsentState.ACTIVE,
                safety=SafetySnapshot(),
                mandatory_checks={
                    "identity": True,
                    "consent": True,
                    "can_talk": True,
                },
            ),
            PublicCallStatus.NO_CONTACT,
        ),
        (
            "TECHNICAL failed",
            CallStatusSnapshot(
                call_id="inv-tech",
                delivery_state=DeliveryState.ANSWERED,
                technical_state=TechnicalState.FAILED,
                care_state=CareState.GREEN,
                consent_state=ConsentState.ACTIVE,
                safety=SafetySnapshot(),
                mandatory_checks={
                    "identity": True,
                    "consent": True,
                    "can_talk": True,
                },
            ),
            PublicCallStatus.TECHNICAL,
        ),
    ]
    for label, snap, expected in cases:
        public = StatusEngine.resolve(snap)
        if public == PublicCallStatus.GREEN:
            errors.append(f"HARD: StatusEngine {label} → GREEN (forbidden)")
        if public != expected:
            errors.append(
                f"HARD: StatusEngine {label} → {public.value}, expected {expected.value}"
            )
    return errors
