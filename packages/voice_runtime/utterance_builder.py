"""Utterance assembly — VAD signals in, one clean user turn out."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from packages.voice_runtime.audio import pcm_rms_s16le


@dataclass(frozen=True)
class UtteranceBuilderConfig:
    pre_roll_ms: int = 300
    silence_hold_ms: int = 500
    post_roll_ms: int = 150
    min_speech_ms: int = 120
    max_utterance_ms: int = 20000
    frame_ms: int = 20


@dataclass
class BuiltUtterance:
    pcm: bytes
    duration_ms: int
    segment_rms: float
    speech_ms: int
    silence_tail_ms: int


class UtteranceBuilder:
    """Merge micro-pauses inside one user turn before STT."""

    def __init__(
        self,
        sample_rate: int,
        config: UtteranceBuilderConfig | None = None,
    ) -> None:
        self.sample_rate = sample_rate
        self.config = config or UtteranceBuilderConfig()
        pre_frames = max(1, self.config.pre_roll_ms // self.config.frame_ms)
        self._pre_roll: deque[bytes] = deque(maxlen=pre_frames)
        self._segment: list[bytes] = []
        self._collecting = False
        self._endpoint_pending = False
        self._silence_frames = 0
        self._speech_frames = 0
        self._post_roll_remaining = 0
        self._post_roll: list[bytes] = []
        self._segment_seq = 0

    def seed_external_preroll(self, pcm: bytes) -> None:
        """Attach blocked-period tail at speech_start (ADR-010; no VAD replay)."""
        if not pcm or self._collecting:
            return
        frame_bytes = max(2, self.sample_rate * 2 * self.config.frame_ms // 1000)
        for offset in range(0, len(pcm), frame_bytes):
            chunk = pcm[offset : offset + frame_bytes]
            if len(chunk) >= 2:
                self._pre_roll.append(chunk)

    @property
    def collecting(self) -> bool:
        return self._collecting or self._endpoint_pending

    @property
    def segment_seq(self) -> int:
        """Acoustic segment identity; a micro-pause does not create a new turn."""
        return self._segment_seq

    def preview_prefix(self, duration_ms: int) -> bytes | None:
        """Copy an exact bounded prefix; never consume/finalize the segment."""
        if not self.collecting or duration_ms <= 0:
            return None
        # Frames are fixed-size on the runtime path. Avoid joining every 20ms.
        if (len(self._segment) + len(self._post_roll)) * self.config.frame_ms < duration_ms:
            return None
        pcm = b"".join(self._segment + self._post_roll)
        prefix_bytes = self.sample_rate * 2 * duration_ms // 1000
        return pcm[:prefix_bytes] if len(pcm) >= prefix_bytes else None

    def reset_pending(self) -> None:
        """Clear in-progress endpoint without emitting (listen handoff)."""
        self._collecting = False
        self._endpoint_pending = False
        self._silence_frames = 0
        self._speech_frames = 0
        self._segment = []
        self._post_roll = []
        self._post_roll_remaining = 0

    def force_finalize(self) -> BuiltUtterance | None:
        if not self._segment:
            self.reset_pending()
            return None
        utterance = self._finalize_now(silence_tail_ms=0)
        self.reset_pending()
        return utterance

    def on_frame(
        self,
        pcm: bytes,
        *,
        speech_started: bool,
        speech_ended: bool,
        speech_active: bool,
        silence_elapsed_ms: int | None = None,
    ) -> BuiltUtterance | None:
        frame_ms = self.config.frame_ms
        hold_frames = max(1, self.config.silence_hold_ms // frame_ms)
        max_frames = max(1, self.config.max_utterance_ms // frame_ms)
        min_frames = max(1, self.config.min_speech_ms // frame_ms)

        if not self._collecting:
            self._pre_roll.append(pcm)
            if speech_started:
                self._segment_seq += 1
                self._collecting = True
                self._endpoint_pending = False
                self._silence_frames = 0
                self._speech_frames = 1
                self._segment = list(self._pre_roll)
            return None

        if (speech_started or speech_active) and self._endpoint_pending:
            self._segment.extend(self._post_roll)
            self._post_roll = []
            self._post_roll_remaining = 0

        if self._post_roll_remaining > 0:
            self._post_roll.append(pcm)
            self._silence_frames += 1
            self._post_roll_remaining -= 1
            if self._post_roll_remaining <= 0:
                self._segment.extend(self._post_roll)
                self._post_roll = []
                return self._maybe_emit(
                    min_frames, silence_tail_ms=self._silence_frames * frame_ms
                )
            return None

        self._segment.append(pcm)
        if speech_active or speech_started:
            self._speech_frames += 1
            self._endpoint_pending = False
            self._silence_frames = 0
        elif speech_ended or not speech_active:
            self._endpoint_pending = True
            self._silence_frames += 1
            if speech_ended and silence_elapsed_ms is not None:
                # VAD already waited for silence. The collector's hold is a
                # minimum total pause, not a second sequential endpoint timer.
                self._silence_frames = max(
                    self._silence_frames, max(0, silence_elapsed_ms) // frame_ms,
                )

        if len(self._segment) >= max_frames:
            return self._maybe_emit(min_frames, silence_tail_ms=self._silence_frames * frame_ms)

        if self._endpoint_pending and self._silence_frames >= hold_frames:
            post_frames = max(0, self.config.post_roll_ms // frame_ms)
            if post_frames > 0 and self._post_roll_remaining == 0:
                self._post_roll_remaining = post_frames
                return None
            return self._maybe_emit(
                min_frames,
                silence_tail_ms=self._silence_frames * frame_ms,
            )
        return None

    def _maybe_emit(self, min_frames: int, *, silence_tail_ms: int) -> BuiltUtterance | None:
        if self._speech_frames < min_frames:
            self.reset_pending()
            return None
        utterance = self._finalize_now(silence_tail_ms=silence_tail_ms)
        self.reset_pending()
        return utterance

    def _finalize_now(self, *, silence_tail_ms: int) -> BuiltUtterance:
        pcm = b"".join(self._segment)
        duration_ms = int(len(pcm) / max(4, self.sample_rate * 2) * 1000)
        speech_ms = self._speech_frames * self.config.frame_ms
        return BuiltUtterance(
            pcm=pcm,
            duration_ms=duration_ms,
            segment_rms=pcm_rms_s16le(pcm),
            speech_ms=speech_ms,
            silence_tail_ms=silence_tail_ms,
        )
