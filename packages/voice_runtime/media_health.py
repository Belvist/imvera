"""Media plane health — distinguish silence from transport failure."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import StrEnum


class MediaHealth(StrEnum):
    HEALTHY = "healthy"
    REMOTE_SILENCE = "remote_silence"
    RTP_STALLED = "rtp_stalled"
    CAPTURE_STALLED = "capture_stalled"
    PIPELINE_DROP = "pipeline_drop"


@dataclass
class MediaPipelineCounters:
    """Four-layer pipeline: RTP → capture WS → actor → STT."""

    rtp_rx_packets: int = 0
    rtp_tx_packets: int = 0
    rtp_rx_jitter: float = 0.0
    rtp_packet_loss: float = 0.0
    capture_ws_frames: int = 0
    capture_ws_bytes: int = 0
    capture_nonzero_frames: int = 0
    actor_pcm_frames: int = 0
    actor_pcm_bytes: int = 0
    actor_nonzero_frames: int = 0
    stt_input_utterances: int = 0
    last_rtp_rx_at: float | None = None
    last_capture_frame_at: float | None = None
    last_actor_frame_at: float | None = None
    last_nonzero_capture_at: float | None = None

    def to_trace_dict(self) -> dict[str, float | int | None]:
        return {
            "rtp_rx_packets": self.rtp_rx_packets,
            "rtp_tx_packets": self.rtp_tx_packets,
            "rtp_rx_jitter": round(self.rtp_rx_jitter, 3),
            "rtp_packet_loss": round(self.rtp_packet_loss, 3),
            "capture_ws_frames": self.capture_ws_frames,
            "capture_ws_bytes": self.capture_ws_bytes,
            "capture_nonzero_frames": self.capture_nonzero_frames,
            "transport_rx_frames": self.capture_ws_frames,
            "transport_rx_bytes": self.capture_ws_bytes,
            "last_transport_frame_at": self.last_capture_frame_at,
            "actor_pcm_frames": self.actor_pcm_frames,
            "actor_pcm_bytes": self.actor_pcm_bytes,
            "actor_nonzero_frames": self.actor_nonzero_frames,
            "nonzero_pcm_frames": self.actor_nonzero_frames,
            "stt_input_utterances": self.stt_input_utterances,
            "last_rtp_rx_at": self.last_rtp_rx_at,
            "last_capture_frame_at": self.last_capture_frame_at,
            "last_actor_frame_at": self.last_actor_frame_at,
            "last_nonzero_capture_at": self.last_nonzero_capture_at,
        }


@dataclass
class MediaHealthTracker:
    """Evaluate whether missing UserTurn is silence vs transport failure."""

    counters: MediaPipelineCounters = field(default_factory=MediaPipelineCounters)
    rtp_stall_s: float = 3.0
    capture_stall_s: float = 2.0
    remote_silence_s: float = 5.0
    _rtp_rx_baseline: int = 0
    _waiting_for_answer: bool = False
    _wait_started_mono: float | None = None

    def note_rtp_rx(self, rxcount: int, *, now: float | None = None) -> None:
        ts = now if now is not None else time.monotonic()
        if rxcount > self.counters.rtp_rx_packets:
            self.counters.last_rtp_rx_at = ts
        self.counters.rtp_rx_packets = rxcount

    def note_rtp_tx(self, txcount: int) -> None:
        self.counters.rtp_tx_packets = txcount

    def note_rtp_quality(self, *, jitter: float = 0.0, loss: float = 0.0) -> None:
        self.counters.rtp_rx_jitter = jitter
        self.counters.rtp_packet_loss = loss

    def note_capture_frame(self, nbytes: int, rms: float, *, now: float | None = None) -> None:
        ts = now if now is not None else time.monotonic()
        self.counters.capture_ws_frames += 1
        self.counters.capture_ws_bytes += nbytes
        self.counters.last_capture_frame_at = ts
        if rms > 50.0:
            self.counters.capture_nonzero_frames += 1
            self.counters.last_nonzero_capture_at = ts

    def note_actor_frame(self, nbytes: int, rms: float, *, now: float | None = None) -> None:
        ts = now if now is not None else time.monotonic()
        self.counters.actor_pcm_frames += 1
        self.counters.actor_pcm_bytes += nbytes
        self.counters.last_actor_frame_at = ts
        if rms > 50.0:
            self.counters.actor_nonzero_frames += 1

    def note_stt_input(self) -> None:
        self.counters.stt_input_utterances += 1

    def set_waiting_for_answer(self, active: bool, *, now: float | None = None) -> None:
        ts = now if now is not None else time.monotonic()
        self._waiting_for_answer = active
        if active:
            self._wait_started_mono = ts
            self._rtp_rx_baseline = self.counters.rtp_rx_packets
        else:
            self._wait_started_mono = None

    def evaluate(self, *, now: float | None = None) -> MediaHealth:
        ts = now if now is not None else time.monotonic()
        c = self.counters

        if c.capture_ws_frames > 0 and c.actor_pcm_frames == 0:
            return MediaHealth.PIPELINE_DROP

        if c.rtp_rx_packets > 0 and c.capture_ws_frames == 0:
            if c.last_rtp_rx_at and (ts - c.last_rtp_rx_at) > self.capture_stall_s:
                return MediaHealth.CAPTURE_STALLED

        if self._waiting_for_answer and self._wait_started_mono is not None:
            wait_s = ts - self._wait_started_mono
            if (
                c.last_rtp_rx_at is not None
                and c.rtp_rx_packets <= self._rtp_rx_baseline
                and wait_s >= self.rtp_stall_s
                and (ts - c.last_rtp_rx_at) >= self.rtp_stall_s
            ):
                return MediaHealth.RTP_STALLED
            if (
                c.capture_ws_frames > 0
                and c.capture_nonzero_frames == 0
                and wait_s >= self.remote_silence_s
            ):
                return MediaHealth.REMOTE_SILENCE
            if (
                c.last_rtp_rx_at
                and c.last_capture_frame_at
                and (ts - c.last_capture_frame_at) > self.capture_stall_s
                and (ts - c.last_rtp_rx_at) < self.capture_stall_s
            ):
                return MediaHealth.CAPTURE_STALLED
            if c.capture_ws_frames > c.actor_pcm_frames + 10:
                return MediaHealth.PIPELINE_DROP

        return MediaHealth.HEALTHY

    def is_answer_wait_allowed(self, *, now: float | None = None) -> bool:
        return self.evaluate(now=now) == MediaHealth.HEALTHY
