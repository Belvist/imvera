"""FreeSWITCH media-plane forensic boundary — RTP vs READ leg vs WS vs CallActor."""

from __future__ import annotations

import wave
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from packages.voice_runtime.audio import pcm_rms_s16le

# Channel variables documented for RTP/media forensics (FreeSWITCH).
RTP_FORENSIC_VARS: tuple[str, ...] = (
    "uuid",
    "direction",
    "call_uuid",
    "channel_name",
    "caller_id_number",
    "destination_number",
    "read_codec",
    "write_codec",
    "rtp_use_codec_name",
    "rtp_use_codec_rate",
    "rtp_use_codec_ptime",
    "rtp_audio_in_packet_count",
    "rtp_audio_in_media_packet_count",
    "rtp_audio_in_raw_bytes",
    "rtp_audio_in_media_bytes",
    "rtp_audio_in_flush_packet_count",
    "rtp_audio_out_packet_count",
    "rtp_audio_out_media_packet_count",
    "rtp_audio_out_raw_bytes",
    "rtp_audio_out_media_bytes",
    "rtp_local_sdp_str",
    "remote_media_ip",
    "remote_media_port",
    "local_media_ip",
    "local_media_port",
    "advertised_media_ip",
    "rtp_auto_adjust_audio",
    "sip_local_network_addr",
    "sip_network_ip",
    "sip_received_ip",
    "sip_received_port",
    "sip_from_host",
    "sip_contact_host",
    "sip_contact_port",
)


class ForensicBoundary(StrEnum):
    """First broken hop — never blame STT/VAD/dialogue above this."""

    OK_CHAIN = "ok_chain"
    # Legacy aliases kept for existing reports
    RTP_RX_ZERO = "rtp_rx_zero"
    FS_READ_SILENT = "fs_read_silent"
    AUDIO_STREAM_SILENT = "audio_stream_silent"
    ACTOR_UPLINK_SILENT = "actor_uplink_silent"
    # P0-A-EXTERNAL boundary taxonomy
    HOST_RTP_RX_ZERO = "host_rtp_rx_zero"
    DOCKER_RTP_FORWARDING_FAILURE = "docker_rtp_forwarding_failure"
    FREESWITCH_RTP_RX_OK_PCM_SILENT = "freeswitch_rtp_rx_ok_pcm_silent"
    MOD_AUDIO_STREAM_DROP = "mod_audio_stream_drop"
    PIPELINE_DROP = "pipeline_drop"
    UNKNOWN = "unknown"


@dataclass
class FreeSwitchForensicEvidence:
    fs_uuid: str
    call_id: str = ""
    channel_vars: dict[str, str] = field(default_factory=dict)
    rtp_audio_in_packets: int = 0
    rtp_audio_in_bytes: int = 0
    rtp_audio_out_packets: int = 0
    negotiated_codec: str = ""
    fs_read_wav: str = ""
    fs_read_rms_peak: float = 0.0
    fs_read_nonzero_frames: int = 0
    ws_raw_wav: str = ""
    ws_rms_peak: float = 0.0
    ws_nonzero_frames: int = 0
    ws_rx_frames: int = 0
    ws_rx_bytes: int = 0
    actor_nonzero_frames: int = 0
    listen_rms_peak: float = 0.0
    stt_utterances: int = 0
    host_rtp_observed: bool = False
    docker_published_rtp_range: str = ""
    local_media_ip: str = ""
    local_media_port: int = 0
    remote_media_ip: str = ""
    remote_media_port: int = 0
    boundary: str = ForensicBoundary.UNKNOWN
    boundary_detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_uuid_dump(text: str) -> dict[str, str]:
    """Parse `fs_cli -x uuid_dump` key=value lines."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = value.strip()
    return out


def _int_var(vars_map: dict[str, str], key: str) -> int:
    raw = vars_map.get(key, "").strip()
    if not raw:
        return 0
    try:
        return int(float(raw))
    except ValueError:
        return 0


DOCKER_PUBLISHED_RTP_RANGE = "16384-16484"


def port_in_published_range(port: int, range_spec: str = DOCKER_PUBLISHED_RTP_RANGE) -> bool:
    if port <= 0 or "-" not in range_spec:
        return False
    start_s, end_s = range_spec.split("-", 1)
    try:
        start, end = int(start_s), int(end_s)
    except ValueError:
        return False
    return start <= port <= end


def analyze_wav_pcm(path: Path, *, frame_bytes: int = 640) -> tuple[float, int]:
    """Return (rms_peak, nonzero_frame_count) for s16le mono wav."""
    if not path.is_file() or path.stat().st_size < 44:
        return 0.0, 0
    peak = 0.0
    nonzero = 0
    with wave.open(str(path), "rb") as wf:
        pcm = wf.readframes(wf.getnframes())
    for i in range(0, len(pcm) - 1, frame_bytes):
        chunk = pcm[i : i + frame_bytes]
        if len(chunk) < 2:
            continue
        rms = pcm_rms_s16le(chunk)
        if rms > 50.0:
            nonzero += 1
        peak = max(peak, rms)
    return peak, nonzero


def classify_media_boundary(
    evidence: FreeSwitchForensicEvidence,
    *,
    rms_speech_threshold: float = 50.0,
) -> FreeSwitchForensicEvidence:
    """Classify first broken hop: host → Docker → FS RTP → READ → WS → CallActor."""
    rtp_pkts = evidence.rtp_audio_in_packets
    fs_voice = (
        evidence.fs_read_rms_peak >= rms_speech_threshold or evidence.fs_read_nonzero_frames > 0
    )
    ws_voice = evidence.ws_rms_peak >= rms_speech_threshold or evidence.ws_nonzero_frames > 0
    actor_voice = (
        evidence.listen_rms_peak >= rms_speech_threshold or evidence.actor_nonzero_frames > 0
    )

    if evidence.host_rtp_observed is False and rtp_pkts <= 0:
        evidence.boundary = ForensicBoundary.HOST_RTP_RX_ZERO
        evidence.boundary_detail = (
            "No RTP observed on Mac LAN interface and FreeSWITCH rtp_in=0 — "
            "Zoiper SDP/mic/STUN or caller not sending to advertised port."
        )
        return evidence

    if rtp_pkts <= 0:
        if evidence.host_rtp_observed:
            evidence.boundary = ForensicBoundary.DOCKER_RTP_FORWARDING_FAILURE
            evidence.boundary_detail = (
                "RTP reached Mac host but FreeSWITCH rtp_audio_in_packet_count=0 — "
                "Docker Desktop UDP publish / wrong advertised RTP port."
            )
        else:
            evidence.boundary = ForensicBoundary.RTP_RX_ZERO
            evidence.boundary_detail = (
                "FreeSWITCH rtp_audio_in_packet_count=0 — caller RTP never arrived "
                f"(local={evidence.local_media_ip}:{evidence.local_media_port}, "
                f"remote={evidence.remote_media_ip}:{evidence.remote_media_port})."
            )
        return evidence

    if not fs_voice:
        evidence.boundary = ForensicBoundary.FREESWITCH_RTP_RX_OK_PCM_SILENT
        evidence.boundary_detail = (
            f"RTP packets={rtp_pkts} but FS READ leg silent "
            f"(rms_peak={evidence.fs_read_rms_peak:.1f}) — codec/decode/media negotiation."
        )
        return evidence

    if not ws_voice:
        evidence.boundary = ForensicBoundary.MOD_AUDIO_STREAM_DROP
        evidence.boundary_detail = (
            f"FS READ has audio (rms={evidence.fs_read_rms_peak:.1f}) but "
            f"mod_audio_stream WS silent (rms={evidence.ws_rms_peak:.1f})."
        )
        return evidence

    if not actor_voice:
        evidence.boundary = ForensicBoundary.PIPELINE_DROP
        evidence.boundary_detail = (
            "WS had energy but CallActor saw only silence — bridge/actor ingress bug."
        )
        return evidence

    evidence.boundary = ForensicBoundary.OK_CHAIN
    evidence.boundary_detail = "RTP → FS READ → WS → CallActor uplink show energy."
    return evidence


def evidence_from_channel_vars(
    fs_uuid: str,
    vars_map: dict[str, str],
    *,
    call_id: str = "",
) -> FreeSwitchForensicEvidence:
    codec = vars_map.get("rtp_use_codec_name") or vars_map.get("read_codec") or ""
    ev = FreeSwitchForensicEvidence(
        fs_uuid=fs_uuid,
        call_id=call_id,
        channel_vars={k: vars_map[k] for k in RTP_FORENSIC_VARS if k in vars_map},
        rtp_audio_in_packets=_int_var(vars_map, "rtp_audio_in_packet_count"),
        rtp_audio_in_bytes=_int_var(vars_map, "rtp_audio_in_media_bytes")
        or _int_var(vars_map, "rtp_audio_in_raw_bytes"),
        rtp_audio_out_packets=_int_var(vars_map, "rtp_audio_out_packet_count"),
        negotiated_codec=codec,
        local_media_ip=vars_map.get("local_media_ip", ""),
        local_media_port=_int_var(vars_map, "local_media_port"),
        remote_media_ip=vars_map.get("remote_media_ip", ""),
        remote_media_port=_int_var(vars_map, "remote_media_port"),
    )
    return ev
