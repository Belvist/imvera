"""FreeSWITCH forensic boundary classification."""

from packages.telephony.freeswitch_forensics import (
    ForensicBoundary,
    FreeSwitchForensicEvidence,
    classify_media_boundary,
)


def test_rtp_rx_zero() -> None:
    ev = FreeSwitchForensicEvidence(fs_uuid="u1", rtp_audio_in_packets=0)
    out = classify_media_boundary(ev)
    assert out.boundary == ForensicBoundary.HOST_RTP_RX_ZERO


def test_fs_read_silent_with_rtp() -> None:
    ev = FreeSwitchForensicEvidence(
        fs_uuid="u2",
        rtp_audio_in_packets=120,
        fs_read_rms_peak=1.0,
        fs_read_nonzero_frames=0,
    )
    out = classify_media_boundary(ev)
    assert out.boundary == ForensicBoundary.FREESWITCH_RTP_RX_OK_PCM_SILENT


def test_mod_audio_stream_drop() -> None:
    ev = FreeSwitchForensicEvidence(
        fs_uuid="u3",
        rtp_audio_in_packets=200,
        fs_read_rms_peak=800.0,
        fs_read_nonzero_frames=10,
        ws_rms_peak=1.0,
        ws_nonzero_frames=0,
    )
    out = classify_media_boundary(ev)
    assert out.boundary == ForensicBoundary.MOD_AUDIO_STREAM_DROP


def test_ok_chain() -> None:
    ev = FreeSwitchForensicEvidence(
        fs_uuid="u4",
        rtp_audio_in_packets=300,
        fs_read_rms_peak=900.0,
        fs_read_nonzero_frames=20,
        ws_rms_peak=700.0,
        ws_nonzero_frames=15,
        listen_rms_peak=600.0,
        actor_nonzero_frames=12,
    )
    out = classify_media_boundary(ev)
    assert out.boundary == ForensicBoundary.OK_CHAIN


def test_docker_forwarding_failure() -> None:
    ev = FreeSwitchForensicEvidence(
        fs_uuid="u5",
        host_rtp_observed=True,
        rtp_audio_in_packets=0,
        local_media_port=16444,
    )
    out = classify_media_boundary(ev)
    assert out.boundary == ForensicBoundary.DOCKER_RTP_FORWARDING_FAILURE
