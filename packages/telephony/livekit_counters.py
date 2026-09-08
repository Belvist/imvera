"""LiveKit media plane counters (ADR-012)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class LiveKitMediaCounters:
    livekit_audio_frames_rx: int = 0
    livekit_audio_bytes_rx: int = 0
    livekit_audio_frames_tx: int = 0
    livekit_audio_bytes_tx: int = 0
    livekit_track_subscribed: int = 0
    livekit_track_unsubscribed: int = 0
    livekit_connection_quality: int = 0
    livekit_reconnects: int = 0
    transport_rx_frames: int = 0
    transport_rx_bytes: int = 0
    actor_pcm_bytes: int = 0

    def note_inbound_frame(self, nbytes: int) -> None:
        self.livekit_audio_frames_rx += 1
        self.livekit_audio_bytes_rx += nbytes
        self.transport_rx_frames += 1
        self.transport_rx_bytes += nbytes

    def note_outbound_frame(self, nbytes: int) -> None:
        self.livekit_audio_frames_tx += 1
        self.livekit_audio_bytes_tx += nbytes

    def to_trace_dict(self) -> dict[str, int]:
        return {
            "livekit_audio_frames_rx": self.livekit_audio_frames_rx,
            "livekit_audio_bytes_rx": self.livekit_audio_bytes_rx,
            "livekit_audio_frames_tx": self.livekit_audio_frames_tx,
            "livekit_audio_bytes_tx": self.livekit_audio_bytes_tx,
            "livekit_track_subscribed": self.livekit_track_subscribed,
            "livekit_track_unsubscribed": self.livekit_track_unsubscribed,
            "livekit_connection_quality": self.livekit_connection_quality,
            "livekit_reconnects": self.livekit_reconnects,
            "transport_rx_frames": self.transport_rx_frames,
            "transport_rx_bytes": self.transport_rx_bytes,
            "actor_pcm_bytes": self.actor_pcm_bytes,
        }


@dataclass
class LiveKitInboundFrameStats:
    seq: int = 0
    frames: list[tuple[int, float, float]] = field(default_factory=list)

    def record(self, nbytes: int, rms: float, peak: int) -> int:
        self.seq += 1
        self.frames.append((nbytes, rms, peak))
        return self.seq
