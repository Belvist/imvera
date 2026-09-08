"""LiveKit privacy redaction tests."""

from packages.telephony.livekit_privacy import (
    new_imvera_call_id,
    redact_room_name,
    redact_sip_identity,
)


def test_opaque_call_id_not_from_room() -> None:
    a = new_imvera_call_id()
    b = new_imvera_call_id()
    assert a.startswith("lk-")
    assert a != b
    assert len(a) > 16


def test_redact_room_name_hides_phone() -> None:
    room = "imvera-call-+15551234567-abc"
    red = redact_room_name(room)
    assert "+1555" not in red
    assert red.startswith("room-")


def test_redact_sip_identity() -> None:
    ident = "+15551234567"
    red = redact_sip_identity(ident)
    assert "+1555" not in red
    assert red.startswith("sip-")
