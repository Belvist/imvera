"""Unit tests for LiveKit media gate evidence + failure classification."""

from __future__ import annotations

from packages.telephony.livekit_gate_evidence import (
    MediaGateEvidence,
    MediaGateFailure,
    classify_media_gate,
)


def test_classify_transport_passed() -> None:
    ev = MediaGateEvidence(
        call_id="lk-test",
        sip_rtp_rx_packets=120,
        livekit_track_frames=80,
        actor_pcm_frames=80,
        nonzero_pcm_frames=40,
        inbound_rms_peak=1200.0,
    )
    assert classify_media_gate(ev) == MediaGateFailure.PASSED


def test_classify_sip_no_rtp() -> None:
    ev = MediaGateEvidence(call_id="lk-test")
    assert classify_media_gate(ev) == MediaGateFailure.SIP_NO_RTP


def test_classify_rtc_no_audiostream() -> None:
    ev = MediaGateEvidence(
        call_id="lk-test",
        remote_track_sid="TR_1",
        sip_participant_sid="PA_1",
        sip_rtp_rx_packets=80,
    )
    assert classify_media_gate(ev) == MediaGateFailure.SIP_NO_TRACK


def test_classify_adapter_drop() -> None:
    ev = MediaGateEvidence(
        call_id="lk-test",
        sip_rtp_rx_packets=50,
        livekit_track_frames=10,
        actor_pcm_frames=0,
        remote_track_sid="TR_1",
    )
    assert classify_media_gate(ev) == MediaGateFailure.ADAPTER_DROP


def test_classify_directional_violation() -> None:
    ev = MediaGateEvidence(
        call_id="lk-test",
        vera_bytes_in_inbound=100,
        nonzero_pcm_frames=5,
        inbound_rms_peak=500.0,
    )
    assert classify_media_gate(ev) == MediaGateFailure.VERA_IN_INBOUND
