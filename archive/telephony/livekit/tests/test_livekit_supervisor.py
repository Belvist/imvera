"""LiveKit supervisor webhook/session tests."""

from __future__ import annotations

import pytest

from packages.telephony.livekit_privacy import new_imvera_call_id
from packages.telephony.livekit_session import (
    IMVERA_IDENTITY_PREFIX,
    is_imvera_participant_identity,
    is_sip_participant_kind,
)
from packages.telephony.livekit_webhook import LiveKitWebhookEvent
from services.voice_gateway.livekit_supervisor import LiveKitSupervisor


def test_imvera_identity_skipped() -> None:
    assert is_imvera_participant_identity(f"{IMVERA_IDENTITY_PREFIX}-abc")
    assert not is_imvera_participant_identity("sip_caller")


def test_sip_kind() -> None:
    assert is_sip_participant_kind(3)
    assert not is_sip_participant_kind(0)


def test_opaque_call_id() -> None:
    a = new_imvera_call_id()
    b = new_imvera_call_id()
    assert a.startswith("lk-")
    assert a != b


@pytest.mark.asyncio
async def test_duplicate_webhook_no_double_session(monkeypatch) -> None:
    sup = LiveKitSupervisor()
    started = 0

    async def fake_start(**kwargs):
        nonlocal started
        started += 1
        room = kwargs.get("room_name", "imvera-call-x")
        sup._room_index[room] = "lk-test"
        return {"status": "started", "call_id": "lk-test"}

    monkeypatch.setattr(sup, "_start_session", fake_start)
    ev = LiveKitWebhookEvent(
        event="participant_joined",
        room_name="imvera-call-x",
        room_sid="RM_x",
        participant_identity="sip_123",
        participant_sid="PA_sip",
        participant_kind=3,
        track_sid="",
        raw={},
    )
    r1 = await sup.handle_webhook(ev)
    r2 = await sup.handle_webhook(ev)
    assert r1["status"] == "started"
    assert r2["status"] == "already_active"
    assert started == 1


@pytest.mark.asyncio
async def test_imvera_participant_webhook_ignored() -> None:
    sup = LiveKitSupervisor()
    ev = LiveKitWebhookEvent(
        event="participant_joined",
        room_name="imvera-call-y",
        room_sid="RM_y",
        participant_identity=f"{IMVERA_IDENTITY_PREFIX}-lk1",
        participant_sid="PA_imvera",
        participant_kind=0,
        track_sid="",
        raw={},
    )
    result = await sup.handle_webhook(ev)
    assert result["status"] == "ignored"
