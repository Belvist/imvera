"""Semantic text chunking for LLM SSE → TTS (Track A2 / E)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_SENT_BOUND = re.compile(r"(?<=[.!?…])(?=\S|\s)")
_STRONG_BOUND = re.compile(r"(?<=[;:])(?=\S|\s)")


@dataclass
class ChunkMetrics:
    llm_request_ms: float | None = None
    llm_ttft_ms: float | None = None
    first_chunk_ms: float | None = None
    second_chunk_ms: float | None = None
    generation_end_ms: float | None = None


@dataclass
class StreamTextChunker:
    """Accumulate LLM tokens; emit speakable chunks at natural boundaries."""

    first_chunk_max_chars: int = 30
    first_chunk_min_chars: int = 15
    chunk_max_chars: int = 70
    chunk_min_chars: int = 30
    max_chunks: int = 4
    max_total_chars: int = 380

    _buffer: str = ""
    _emitted: int = 0
    _emitted_chars: int = 0
    _prefix_stripped: bool = False

    def feed(self, delta: str) -> list[str]:
        if not delta:
            return []
        self._buffer = " ".join((self._buffer + delta).split())
        if not self._prefix_stripped:
            self._buffer = re.sub(
                r"^(Вера|Assistant|Ответ)\s*:\s*",
                "",
                self._buffer,
                flags=re.IGNORECASE,
            )
            self._prefix_stripped = True
        out: list[str] = []
        while True:
            chunk = self._try_emit()
            if not chunk:
                break
            out.append(chunk)
            if self._emitted >= self.max_chunks:
                break
        return out

    def flush(self) -> str | None:
        tail = self._buffer.strip()
        if not tail or self._emitted >= self.max_chunks:
            return None
        if self._emitted_chars + len(tail) > self.max_total_chars:
            cut = tail[: self.max_total_chars - self._emitted_chars].rfind(" ")
            tail = (tail[:cut].rstrip() if cut > 0 else tail[: self.max_total_chars]) + "."
        self._emitted += 1
        self._buffer = ""
        return tail

    def _try_emit(self) -> str | None:
        if self._emitted >= self.max_chunks:
            return None
        min_c = self.first_chunk_min_chars if self._emitted == 0 else self.chunk_min_chars
        max_c = self.first_chunk_max_chars if self._emitted == 0 else self.chunk_max_chars

        cut = self._find_boundary(min_chars=min_c, max_chars=max_c)
        if cut is None:
            return None
        seg = self._buffer[:cut].strip()
        if len(seg) < 2:
            return None
        if self._emitted_chars + len(seg) > self.max_total_chars:
            return None
        self._emitted += 1
        self._emitted_chars += len(seg)
        self._buffer = self._buffer[cut:].strip()
        return seg

    def _find_boundary(self, *, min_chars: int, max_chars: int) -> int | None:
        buf = self._buffer
        if len(buf) < min_chars:
            return None
        for pat in (_SENT_BOUND, _STRONG_BOUND):
            for sm in pat.finditer(buf):
                end = sm.end()
                if min_chars <= end <= max_chars:
                    return end
        if len(buf) >= max_chars:
            for marker in (", ", " — ", " – "):
                i = buf.rfind(marker, min_chars, max_chars)
                if i > 0:
                    return i + len(marker)
            sp = buf.rfind(" ", min_chars, max_chars)
            if sp > 0:
                return sp
        if self._emitted == 0 and len(buf) >= min_chars:
            for marker in (", ", ". ", "? ", "! "):
                i = buf.find(marker)
                if 0 < i < max_chars:
                    return i + len(marker) - 1
        return None
