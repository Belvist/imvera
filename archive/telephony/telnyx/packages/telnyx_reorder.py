"""Telnyx inbound media chunk reorder buffer (ADR-011)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TelnyxReorderCounters:
    telnyx_media_received: int = 0
    telnyx_media_reordered: int = 0
    telnyx_media_duplicates: int = 0
    telnyx_media_late: int = 0
    telnyx_media_gaps: int = 0
    telnyx_payload_bytes: int = 0

    def to_trace_dict(self) -> dict[str, int]:
        return {
            "telnyx_media_received": self.telnyx_media_received,
            "telnyx_media_reordered": self.telnyx_media_reordered,
            "telnyx_media_duplicates": self.telnyx_media_duplicates,
            "telnyx_media_late": self.telnyx_media_late,
            "telnyx_media_gaps": self.telnyx_media_gaps,
            "telnyx_payload_bytes": self.telnyx_payload_bytes,
        }


@dataclass
class TelnyxMediaReorderBuffer:
    """Reorder inbound chunks by media.chunk; bounded wait, no infinite stall."""

    window: int = 32
    max_gap_skip: int = 8
    _expected: int | None = None
    _pending: dict[int, str] = field(default_factory=dict)
    _delivered: set[int] = field(default_factory=set)
    counters: TelnyxReorderCounters = field(default_factory=TelnyxReorderCounters)

    def push(self, chunk: int, payload_b64: str) -> list[tuple[int, str]]:
        self.counters.telnyx_media_received += 1
        self.counters.telnyx_payload_bytes += len(payload_b64)

        if chunk in self._delivered:
            self.counters.telnyx_media_duplicates += 1
            return []

        if self._expected is None:
            self._expected = chunk

        if chunk < self._expected:
            self.counters.telnyx_media_late += 1
            return []

        if chunk in self._pending:
            self.counters.telnyx_media_duplicates += 1
            return []

        if chunk > self._expected:
            gap = chunk - self._expected
            if gap > self.window:
                self.counters.telnyx_media_gaps += gap
                self._expected = chunk
            else:
                self._pending[chunk] = payload_b64
                self._skip_unfillable_gaps()
                if chunk != self._expected:
                    return []

        ready: list[tuple[int, str]] = []
        if chunk == self._expected:
            ready.append((chunk, payload_b64))
            self._delivered.add(chunk)
            self._expected += 1
            ready.extend(self._drain_pending())
        return ready

    def _drain_pending(self) -> list[tuple[int, str]]:
        ready: list[tuple[int, str]] = []
        while self._expected is not None and self._expected in self._pending:
            chunk = self._expected
            payload = self._pending.pop(chunk)
            ready.append((chunk, payload))
            self._delivered.add(chunk)
            self.counters.telnyx_media_reordered += 1
            self._expected += 1
        return ready

    def _skip_unfillable_gaps(self) -> None:
        while self._expected is not None and self._expected not in self._pending:
            if not self._pending:
                break
            next_chunk = min(self._pending)
            if next_chunk - self._expected > self.max_gap_skip:
                self.counters.telnyx_media_gaps += next_chunk - self._expected
                self._expected = next_chunk
            else:
                break
