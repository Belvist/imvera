"""Per-call latency timeline — observability ONLY (reviewer item 10).

Records monotonic timestamps at existing hook sites; computes deltas;
emits one `timeline` stage event at disconnect. No behavior change:
no branches, no thresholds, no state machine impact. If this module
throws, the caller must swallow (never break audio).

Marks: answer(media_ready) → first_inbound_pcm → vad_start → vad_end →
stt_final → decision → tts_first_pcm → playout → hangup.
Only FIRST occurrence per mark (first-turn latency = the SLO).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class CallTimeline:
    call_id: str
    marks: dict[str, float] = field(default_factory=dict)

    def mark(self, name: str) -> None:
        try:
            if name not in self.marks:
                self.marks[name] = time.monotonic()
        except Exception:  # noqa: BLE001 — observability never breaks audio
            pass

    def to_payload(self) -> dict:
        try:
            out: dict[str, float | None] = {}
            # Base = earliest mark (opening turn may decide before media-ready
            # fires; never emit negative segments).
            base = min(self.marks.values()) if self.marks else 0.0
            order = (
                "answer", "first_inbound_pcm", "vad_start", "vad_end",
                "stt_final", "decision", "tts_first_pcm", "playout", "hangup",
            )
            for name in order:
                ts = self.marks.get(name)
                out[name + "_ms"] = round((ts - base) * 1000, 1) if ts is not None else None
            # Key SLO segments (reviewer item 10).
            def seg(a: str, b: str) -> float | None:
                if a in self.marks and b in self.marks:
                    return round((self.marks[b] - self.marks[a]) * 1000, 1)
                return None

            out["seg_answer_to_stt_final_ms"] = seg("answer", "stt_final")
            out["seg_stt_final_to_decision_ms"] = seg("stt_final", "decision")
            out["seg_decision_to_tts_first_pcm_ms"] = seg("decision", "tts_first_pcm")
            out["seg_tts_first_pcm_to_playout_ms"] = seg("tts_first_pcm", "playout")
            out["seg_answer_to_playout_ms"] = seg("answer", "playout")
            out["call_id"] = self.call_id
            return out  # type: ignore[return-value]
        except Exception:  # noqa: BLE001
            return {"call_id": self.call_id}
