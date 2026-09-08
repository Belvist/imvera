"""LiveKit privacy — opaque IMVERA call_id, redacted traces (ADR-012)."""

from __future__ import annotations

import uuid


def new_imvera_call_id() -> str:
    """Opaque application call id — never derived from phone number or room name."""
    return f"lk-{uuid.uuid4().hex}"


def redact_room_name(room_name: str) -> str:
    """LiveKit dispatchRuleIndividual may embed caller number in room_name — redact for logs."""
    if not room_name:
        return ""
    digest = uuid.uuid5(uuid.NAMESPACE_URL, room_name).hex[:10]
    return f"room-{digest}"


def redact_sip_identity(identity: str) -> str:
    """SIP participant identity may be a phone number — never log raw in trace."""
    if not identity:
        return ""
    digest = uuid.uuid5(uuid.NAMESPACE_URL, identity).hex[:10]
    return f"sip-{digest}"


def room_mapping_note() -> str:
    return (
        "LiveKit SIPDispatchRuleIndividual room names may contain caller digits; "
        "IMVERA call_id is opaque UUID. Map room_sid → call_id internally; redact room_name in traces."
    )
