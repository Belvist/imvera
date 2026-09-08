"""Unit tests for LiveKit media gate evidence + failure classification."""

from __future__ import annotations

from packages.telephony.livekit_gate_evidence import (
    MediaGateEvidence,
    MediaGateFailure,
    classify_media_gate,
)


def _transport_pass_evidence() -> MediaGateEvidence:
    return MediaGateEvidence(
        call_id="lk-test",
        sip_participant_sid="PA_1",
        room_connected_at=1.0,
        local_track_published_at=1.1,
        transport_ready_at=1.2,
        first_outbound_pcm_at=1.3,
        synthetic_rtp_tx_packets=120,
        remote_track_sid="TR_1",
        livekit_track_frames=80,
        livekit_outbound_frames=40,
        actor_pcm_frames=80,
        nonzero_pcm_frames=40,
        inbound_rms_peak=1200.0,
        inbound_has_440_hz=True,
        inbound_has_880_hz=False,
        caller_downlink_has_880_hz=True,
        synthetic_downlink_wav="/tmp/downlink.u8",
    )


def test_classify_transport_passed() -> None:
    assert classify_media_gate(_transport_pass_evidence()) == MediaGateFailure.PASSED


def test_classify_sip_no_rtp() -> None:
    ev = MediaGateEvidence(call_id="lk-test")
    assert classify_media_gate(ev) == MediaGateFailure.SIP_NO_RTP


def test_classify_sip_no_track() -> None:
    ev = MediaGateEvidence(
        call_id="lk-test",
        synthetic_rtp_tx_packets=80,
        sip_participant_sid="PA_1",
        room_connected_at=1.0,
    )
    assert classify_media_gate(ev) == MediaGateFailure.SIP_NO_TRACK


def test_classify_adapter_drop() -> None:
    ev = MediaGateEvidence(
        call_id="lk-test",
        synthetic_rtp_tx_packets=50,
        livekit_track_frames=10,
        actor_pcm_frames=0,
        remote_track_sid="TR_1",
    )
    assert classify_media_gate(ev) == MediaGateFailure.ADAPTER_DROP


def test_classify_directional_violation() -> None:
    ev = _transport_pass_evidence()
    ev.inbound_has_880_hz = True
    assert classify_media_gate(ev) == MediaGateFailure.VERA_IN_INBOUND


def test_classify_outbound_missing() -> None:
    ev = _transport_pass_evidence()
    ev.caller_downlink_has_880_hz = False
    assert classify_media_gate(ev) == MediaGateFailure.SIP_DOWNLINK_MEDIA_FAILURE


def test_classify_outbound_starvation() -> None:
    ev = MediaGateEvidence(
        call_id="lk-test",
        sip_participant_sid="PA_1",
        room_connected_at=1.0,
        local_track_published_at=2.0,
        livekit_outbound_frames=0,
    )
    assert classify_media_gate(ev) == MediaGateFailure.OUTBOUND_STARVATION


def test_classify_sip_dispatch_failure() -> None:
    ev = MediaGateEvidence(call_id="lk-test", invite_sent_at=1.0, sip_answered_at=None)
    assert classify_media_gate(ev) == MediaGateFailure.SIP_DISPATCH_FAILURE


def test_classify_room_connect_failure() -> None:
    ev = MediaGateEvidence(call_id="lk-test", sip_participant_sid="PA_1", sip_answered_at=2.0)
    assert classify_media_gate(ev) == MediaGateFailure.ROOM_CONNECT_FAILURE
