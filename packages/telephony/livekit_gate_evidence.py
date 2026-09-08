"""LiveKit gate evidence + failure boundary classification (transport gate)."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path


class MediaGateFailure(StrEnum):
    PASSED = "transport_p0_passed"
    SIP_NO_RTP = "sip_endpoint_network_sdp"
    SIP_NO_TRACK = "livekit_sip_media"
    NO_AUDIOSTREAM = "livekit_rtc_subscription"
    ADAPTER_DROP = "livekit_telephony_adapter"
    NO_NONZERO_PCM = "remote_silence"
    VERA_IN_INBOUND = "directional_violation"
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
    first_livekit_frame_at: float | None = None
    first_imvera_pcm_at: float | None = None
    sip_rtp_rx_packets: int = 0
    sip_rtp_rx_bytes: int = 0
    livekit_track_frames: int = 0
    livekit_track_bytes: int = 0
    actor_pcm_frames: int = 0
    actor_pcm_bytes: int = 0
    nonzero_pcm_frames: int = 0
    inbound_rms_peak: float = 0.0
    inbound_peak_sample: int = 0
    vera_bytes_in_inbound: int = 0
    raw_inbound_wav: str = ""
    negotiated_codecs: list[str] = field(default_factory=list)
    failure: str = ""
    classified_at: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> MediaGateEvidence:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


def classify_media_gate(evidence: MediaGateEvidence) -> MediaGateFailure:
    if evidence.vera_bytes_in_inbound > 0:
        return MediaGateFailure.VERA_IN_INBOUND
    if evidence.sip_rtp_rx_packets == 0 and evidence.livekit_track_frames == 0:
        if evidence.sip_participant_sid or evidence.remote_track_sid:
            return MediaGateFailure.NO_AUDIOSTREAM
        return MediaGateFailure.SIP_NO_RTP
    if evidence.sip_rtp_rx_packets > 0 and evidence.livekit_track_frames == 0:
        if evidence.remote_track_sid or evidence.sip_participant_sid:
            return MediaGateFailure.SIP_NO_TRACK
        return MediaGateFailure.SIP_NO_RTP
    if evidence.remote_track_sid and evidence.livekit_track_frames == 0:
        return MediaGateFailure.NO_AUDIOSTREAM
    if evidence.livekit_track_frames > 0 and evidence.actor_pcm_frames == 0:
        return MediaGateFailure.ADAPTER_DROP
    if evidence.actor_pcm_frames > 0 and evidence.nonzero_pcm_frames == 0:
        return MediaGateFailure.NO_NONZERO_PCM
    if evidence.nonzero_pcm_frames > 0 and evidence.inbound_rms_peak > 50.0:
        return MediaGateFailure.PASSED
    if evidence.actor_pcm_frames > 0:
        return MediaGateFailure.NO_NONZERO_PCM
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
