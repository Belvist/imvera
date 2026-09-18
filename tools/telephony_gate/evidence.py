"""Transport media gate evidence + failure classification (telephony-neutral)."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path


class MediaGateFailure(StrEnum):
    PASSED = "transport_p0_passed"
    FS_ANSWER_FAILURE = "fs_answer_failure"
    BRIDGE_WS_FAILURE = "bridge_ws_failure"
    OUTBOUND_STARVATION = "outbound_starvation"
    SIP_DOWNLINK_MEDIA_FAILURE = "sip_downlink_media_failure"
    SIP_UPLINK_MEDIA_FAILURE = "sip_uplink_media_failure"
    NO_NONZERO_PCM = "remote_silence"
    CALLER_TONE_MISSING = "caller_tone_missing"
    VERA_IN_INBOUND = "directional_violation"
    OUTBOUND_NOT_RECEIVED = "outbound_not_received"
    UNKNOWN = "unknown"


@dataclass
class MediaGateEvidence:
    call_id: str
    invite_sent_at: float | None = None
    fs_answered_at: float | None = None
    bridge_ws_connected_at: float | None = None
    first_outbound_pcm_at: float | None = None
    first_inbound_pcm_at: float | None = None
    synthetic_rtp_tx_packets: int = 0
    synthetic_rtp_tx_bytes: int = 0
    bridge_rx_frames: int = 0
    bridge_rx_bytes: int = 0
    bridge_tx_frames: int = 0
    bridge_tx_bytes: int = 0
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
    gate_phase: str = "p0a"
    failure: str = ""
    classified_at: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> MediaGateEvidence:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


def classify_media_gate(
    evidence: MediaGateEvidence, *, phase: str | None = None
) -> MediaGateFailure:
    gate_phase = phase or evidence.gate_phase or "p0a"
    if evidence.inbound_has_880_hz:
        return MediaGateFailure.VERA_IN_INBOUND

    if evidence.invite_sent_at and not evidence.fs_answered_at:
        return MediaGateFailure.FS_ANSWER_FAILURE

    if evidence.fs_answered_at and evidence.bridge_ws_connected_at is None:
        return MediaGateFailure.BRIDGE_WS_FAILURE

    if gate_phase == "p0b":
        if (
            evidence.bridge_ws_connected_at is not None
            and evidence.first_outbound_pcm_at is None
            and evidence.bridge_tx_frames == 0
        ):
            return MediaGateFailure.OUTBOUND_STARVATION
        if (
            evidence.first_outbound_pcm_at is not None
            and evidence.bridge_tx_frames > 0
            and evidence.synthetic_downlink_wav
            and not evidence.caller_downlink_has_880_hz
        ):
            return MediaGateFailure.SIP_DOWNLINK_MEDIA_FAILURE

    if evidence.bridge_ws_connected_at and evidence.bridge_rx_frames == 0:
        return MediaGateFailure.SIP_UPLINK_MEDIA_FAILURE

    if evidence.bridge_rx_frames > 0 and evidence.nonzero_pcm_frames == 0:
        return MediaGateFailure.NO_NONZERO_PCM

    if evidence.bridge_rx_frames > 0 and not evidence.inbound_has_440_hz:
        return MediaGateFailure.CALLER_TONE_MISSING

    if evidence.bridge_rx_frames > 0 and not evidence.caller_downlink_has_880_hz:
        return MediaGateFailure.OUTBOUND_NOT_RECEIVED

    if (
        evidence.nonzero_pcm_frames > 0
        and evidence.inbound_rms_peak > 50.0
        and evidence.inbound_has_440_hz
        and not evidence.inbound_has_880_hz
        and evidence.caller_downlink_has_880_hz
    ):
        return MediaGateFailure.PASSED

    if evidence.bridge_rx_frames > 0:
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


MEDIA_GATE_STAMP = Path(".run/freeswitch-gate/media_gate.passed")
