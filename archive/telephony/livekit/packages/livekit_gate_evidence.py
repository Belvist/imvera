"""LiveKit gate evidence + failure boundary classification (transport gate)."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path


class MediaGateFailure(StrEnum):
    PASSED = "transport_p0_passed"
    SIP_DISPATCH_FAILURE = "sip_dispatch_failure"
    ROOM_CONNECT_FAILURE = "room_connect_failure"
    TRACK_TIMEOUT = "track_timeout"
    OUTBOUND_STARVATION = "outbound_starvation"
    SIP_DOWNLINK_MEDIA_FAILURE = "sip_downlink_media_failure"
    SIP_UPLINK_MEDIA_FAILURE = "sip_uplink_media_failure"
    SIP_NO_RTP = "sip_endpoint_network_sdp"
    SIP_NO_TRACK = "livekit_sip_media"
    NO_AUDIOSTREAM = "livekit_rtc_subscription"
    ADAPTER_DROP = "livekit_telephony_adapter"
    NO_NONZERO_PCM = "remote_silence"
    CALLER_TONE_MISSING = "caller_tone_missing"
    VERA_IN_INBOUND = "directional_violation"
    OUTBOUND_NOT_RECEIVED = "outbound_not_received"
    UNKNOWN = "unknown"


@dataclass
class MediaGateEvidence:
    call_id: str
    room_ref: str = ""
    room_sid: str = ""
    sip_participant_sid: str = ""
    remote_track_sid: str = ""
    invite_sent_at: float | None = None
    sip_answered_at: float | None = None
    room_connected_at: float | None = None
    local_track_published_at: float | None = None
    transport_ready_at: float | None = None
    first_outbound_pcm_at: float | None = None
    first_livekit_frame_at: float | None = None
    first_imvera_pcm_at: float | None = None
    first_inbound_pcm_at: float | None = None
    synthetic_rtp_tx_packets: int = 0
    synthetic_rtp_tx_bytes: int = 0
    sip_rtp_rx_packets: int = 0
    sip_rtp_rx_bytes: int = 0
    livekit_track_frames: int = 0
    livekit_track_bytes: int = 0
    livekit_outbound_frames: int = 0
    livekit_outbound_bytes: int = 0
    actor_pcm_frames: int = 0
    actor_pcm_bytes: int = 0
    nonzero_pcm_frames: int = 0
    inbound_rms_peak: float = 0.0
    inbound_peak_sample: int = 0
    inbound_has_440_hz: bool = False
    inbound_has_880_hz: bool = False
    caller_downlink_has_880_hz: bool = False
    inbound_440_snr: float = 0.0
    inbound_880_snr: float = 0.0
    caller_880_snr: float = 0.0
    raw_inbound_wav: str = ""
    synthetic_downlink_wav: str = ""
    negotiated_codecs: list[str] = field(default_factory=list)
    failure: str = ""
    classified_at: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> MediaGateEvidence:
        # Backward compat: old evidence used sip_rtp_rx for synthetic TX.
        if "synthetic_rtp_tx_packets" not in data and data.get("sip_rtp_rx_packets"):
            data = dict(data)
            data["synthetic_rtp_tx_packets"] = data.pop("sip_rtp_rx_packets", 0)
            data["synthetic_rtp_tx_bytes"] = data.pop("sip_rtp_rx_bytes", 0)
            data["sip_rtp_rx_packets"] = 0
            data["sip_rtp_rx_bytes"] = 0
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


def _has_transport_flow(evidence: MediaGateEvidence) -> bool:
    return (
        evidence.synthetic_rtp_tx_packets > 0
        or evidence.livekit_track_frames > 0
        or evidence.livekit_outbound_frames > 0
    )


def classify_media_gate(evidence: MediaGateEvidence) -> MediaGateFailure:
    if evidence.inbound_has_880_hz:
        return MediaGateFailure.VERA_IN_INBOUND

    if evidence.invite_sent_at and not evidence.sip_answered_at:
        return MediaGateFailure.SIP_DISPATCH_FAILURE

    if evidence.sip_answered_at and not evidence.sip_participant_sid:
        return MediaGateFailure.SIP_DISPATCH_FAILURE

    if evidence.sip_participant_sid and evidence.room_connected_at is None:
        return MediaGateFailure.ROOM_CONNECT_FAILURE

    if (
        evidence.local_track_published_at is not None
        and evidence.first_outbound_pcm_at is None
        and evidence.livekit_outbound_frames == 0
    ):
        return MediaGateFailure.OUTBOUND_STARVATION

    if (
        evidence.room_connected_at is not None
        and not evidence.remote_track_sid
        and evidence.livekit_track_frames == 0
        and evidence.actor_pcm_frames == 0
        and evidence.synthetic_rtp_tx_packets == 0
    ):
        return MediaGateFailure.TRACK_TIMEOUT

    if (
        evidence.first_outbound_pcm_at is not None
        and evidence.livekit_outbound_frames > 0
        and evidence.synthetic_downlink_wav
        and not evidence.caller_downlink_has_880_hz
    ):
        return MediaGateFailure.SIP_DOWNLINK_MEDIA_FAILURE

    if not _has_transport_flow(evidence):
        return MediaGateFailure.SIP_NO_RTP
    if evidence.livekit_track_frames == 0:
        if evidence.remote_track_sid or evidence.sip_participant_sid:
            if evidence.first_outbound_pcm_at is not None:
                return MediaGateFailure.SIP_UPLINK_MEDIA_FAILURE
            return MediaGateFailure.SIP_NO_TRACK
        return MediaGateFailure.SIP_NO_RTP
    if evidence.remote_track_sid and evidence.livekit_track_frames == 0:
        return MediaGateFailure.NO_AUDIOSTREAM
    if evidence.livekit_track_frames > 0 and evidence.actor_pcm_frames == 0:
        return MediaGateFailure.ADAPTER_DROP
    if evidence.actor_pcm_frames > 0 and evidence.nonzero_pcm_frames == 0:
        return MediaGateFailure.NO_NONZERO_PCM
    if evidence.actor_pcm_frames > 0 and not evidence.inbound_has_440_hz:
        return MediaGateFailure.CALLER_TONE_MISSING
    if evidence.actor_pcm_frames > 0 and not evidence.caller_downlink_has_880_hz:
        return MediaGateFailure.OUTBOUND_NOT_RECEIVED
    if (
        evidence.nonzero_pcm_frames > 0
        and evidence.inbound_rms_peak > 50.0
        and evidence.inbound_has_440_hz
        and not evidence.inbound_has_880_hz
        and evidence.caller_downlink_has_880_hz
    ):
        return MediaGateFailure.PASSED
    if evidence.actor_pcm_frames > 0:
        return MediaGateFailure.UNKNOWN
    return MediaGateFailure.UNKNOWN


def write_evidence(path: Path, evidence: MediaGateEvidence) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    evidence.classified_at = time.time()
    if not evidence.failure:
        evidence.failure = str(classify_media_gate(evidence))
    path.write_text(json.dumps(evidence.to_dict(), indent=2), encoding="utf-8")


def read_evidence(path: Path) -> MediaGateEvidence | None:
    if not path.exists():
        return None
    return MediaGateEvidence.from_dict(json.loads(path.read_text(encoding="utf-8")))


def find_latest_evidence(root: Path) -> Path | None:
    if not root.exists():
        return None
    candidates = list(root.glob("*/media_gate_evidence.json"))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


MEDIA_GATE_STAMP = Path(".run/livekit-gate/media_gate.passed")
