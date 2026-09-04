"""End-to-end ingress / turn latency trace (Track J, Wave RT-1)."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


def _mono_ns() -> int:
    return time.monotonic_ns()


@dataclass
class IngressTrace:
    """Structured timestamps for one call or proof session."""

    call_id: str = ""
    generation_id: int = 0
    events: list[dict[str, Any]] = field(default_factory=list)
    _t0: int = field(default_factory=_mono_ns)

    def mark(self, name: str, **fields: Any) -> None:
        self.events.append(
            {
                "name": name,
                "t_mono_ns": _mono_ns(),
                "t_rel_ms": round((_mono_ns() - self._t0) / 1_000_000, 2),
                **fields,
            }
        )

    def pcm_frame(
        self,
        *,
        sequence: int,
        nbytes: int,
        rms: float,
        speech_active: bool,
    ) -> None:
        self.mark(
            "pcm_frame",
            sequence=sequence,
            nbytes=nbytes,
            rms=round(rms, 2),
            speech_active=speech_active,
        )

    def speech_start(self) -> None:
        self.mark("user_speech_start")

    def speech_end(self) -> None:
        self.mark("user_speech_end")

    def endpoint_decision(self, *, source: str, silence_ms: float) -> None:
        self.mark(
            "endpoint_decision",
            source=source,
            silence_ms=round(silence_ms, 1),
        )

    def turn_committed(self, *, sample_count: int) -> None:
        self.mark("turn_committed", sample_count=sample_count)

    def to_dict(self) -> dict[str, Any]:
        return {
            "call_id": self.call_id,
            "generation_id": self.generation_id,
            "events": list(self.events),
        }

    def prove_continuous_ingress(self) -> dict[str, Any]:
        """True when PCM frames arrived before speech_end (not batch-after-record)."""
        frames = [e for e in self.events if e["name"] == "pcm_frame"]
        speech_starts = [e for e in self.events if e["name"] == "user_speech_start"]
        speech_ends = [e for e in self.events if e["name"] == "user_speech_end"]
        if not frames:
            return {
                "ok": False,
                "reason": "no_pcm_frames",
                "frame_count": 0,
            }
        first_frame_ms = frames[0]["t_rel_ms"]
        last_frame_before_end_ms = None
        if speech_ends:
            end_ms = speech_ends[-1]["t_rel_ms"]
            end_idx = self.events.index(speech_ends[-1])
            during = [
                e
                for e in self.events[:end_idx]
                if e["name"] == "pcm_frame"
            ]
            last_frame_before_end_ms = during[-1]["t_rel_ms"] if during else None
            frames_during_speech = len(during)
        else:
            end_ms = None
            frames_during_speech = len(frames)

        ok = frames_during_speech >= 3 and (
            speech_ends == [] or last_frame_before_end_ms is not None
        )
        return {
            "ok": ok,
            "frame_count": len(frames),
            "frames_during_speech": frames_during_speech,
            "first_pcm_ms": first_frame_ms,
            "speech_end_ms": end_ms,
            "last_pcm_before_end_ms": last_frame_before_end_ms,
            "speech_started": bool(speech_starts),
        }
