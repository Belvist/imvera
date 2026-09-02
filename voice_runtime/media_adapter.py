"""MediaAdapter — realtime media-source contract (read.md G2 / ROADMAP E1).

Production path must NOT depend on a growing ``uuid_record`` WAV. Transports
implement the same contract so the VAD/turn loop never changes:

    adapter.frames_in()   -> list[int16]
    adapter.rate          -> int
    adapter.audio_bytes() -> int
    adapter.broken        -> bool
    adapter.close()

Adapters
--------
* ``NullMedia`` — silence / tests.
* ``StreamingPcmAdapter`` — production-shaped: ``push_frames`` from WS /
  media-bug callbacks (not a filesystem).
* ``LiveWavReader`` (``media_tap.py``) — **dev-only** uuid_record tail.
  Do not use it for production barge-in.

Helpers: ``PreRollBuffer`` (300–500 ms PCM before onset), ``GenerationGuard``
(drop stale TTS after barge-in bump).
"""
from __future__ import annotations

import abc
import array
import threading


class MediaAdapter(abc.ABC):
    """Continuous mono-int16 media source (16 kHz canonical)."""

    SAMPLE_RATE = 16000

    def __init__(self):
        self.broken = False

    @abc.abstractmethod
    def frames_in(self, rate=SAMPLE_RATE):
        ...

    @property
    @abc.abstractmethod
    def rate(self):
        ...

    @abc.abstractmethod
    def audio_bytes(self):
        ...

    def close(self):
        pass


class NullMedia(MediaAdapter):
    """Test/silence adapter: always-empty stream, never broken."""

    def frames_in(self, rate=MediaAdapter.SAMPLE_RATE):
        return []

    @property
    def rate(self):
        return self.SAMPLE_RATE

    def audio_bytes(self):
        return 0


class PreRollBuffer:
    """Ring buffer keeping the last ``ms`` of PCM16 mono samples (default 400)."""

    def __init__(self, ms=400, sample_rate=16000):
        ms = int(ms)
        if ms < 50 or ms > 2000:
            raise ValueError("PreRollBuffer ms must be in [50, 2000]")
        self.ms = ms
        self.sample_rate = int(sample_rate)
        self.capacity = max(1, int(self.sample_rate * (ms / 1000.0)))
        self._buf = array.array("h")
        self._lock = threading.Lock()

    def push(self, samples):
        if not samples:
            return
        with self._lock:
            self._buf.extend(samples)
            overflow = len(self._buf) - self.capacity
            if overflow > 0:
                del self._buf[:overflow]

    def snapshot(self):
        with self._lock:
            return list(self._buf)

    def flush(self):
        """Return and clear the pre-roll (onset handoff to STT)."""
        with self._lock:
            out = list(self._buf)
            del self._buf[:]
            return out

    def clear(self):
        with self._lock:
            del self._buf[:]

    def __len__(self):
        with self._lock:
            return len(self._buf)


class GenerationGuard:
    """Hard barge-in boundary: bump generation to invalidate stale playback."""

    def __init__(self, start=0):
        self._gid = int(start)
        self._lock = threading.Lock()

    @property
    def generation_id(self) -> int:
        with self._lock:
            return self._gid

    def current(self) -> int:
        return self.generation_id

    def bump(self) -> int:
        with self._lock:
            self._gid += 1
            return self._gid

    def is_current(self, gid: int) -> bool:
        with self._lock:
            return int(gid) == self._gid


class StreamingPcmAdapter(MediaAdapter):
    """Production-shaped adapter: push PCM from WS/media-bug callbacks.

    ``uuid_record`` LiveWavReader (``media_tap.py``) remains the DEV adapter;
    this is the contract target for continuous media (ROADMAP E1 / read.md G2).
    """

    def __init__(self, sample_rate=16000, pre_roll_ms=400):
        super().__init__()
        self._rate = int(sample_rate)
        self._pending = array.array("h")
        self._bytes = 0
        self._lock = threading.Lock()
        self.pre_roll = PreRollBuffer(ms=pre_roll_ms, sample_rate=sample_rate)
        self.generation = GenerationGuard()

    @property
    def rate(self):
        return self._rate

    def push_frames(self, data):
        """Accept little-endian PCM16 bytes or a sequence of int samples."""
        if self.broken:
            return
        try:
            if isinstance(data, (bytes, bytearray, memoryview)):
                raw = bytes(data)
                if len(raw) % 2:
                    raw = raw[:-1]
                if not raw:
                    return
                samples = array.array("h")
                samples.frombytes(raw)
                if sys_byteorder_swap_needed():
                    samples.byteswap()
                seq = samples.tolist()
            else:
                seq = [int(x) for x in data]
        except Exception:  # noqa: BLE001
            self.broken = True
            return
        with self._lock:
            self._pending.extend(seq)
            self._bytes += len(seq) * 2
        self.pre_roll.push(seq)

    def frames_in(self, rate=MediaAdapter.SAMPLE_RATE):
        with self._lock:
            out = self._pending.tolist()
            del self._pending[:]
        if rate != self._rate and out:
            ratio = float(rate) / float(self._rate)
            n = int(len(out) * ratio)
            if n <= 0:
                return []
            return [out[min(len(out) - 1, int(i / ratio))] for i in range(n)]
        return out

    def audio_bytes(self):
        with self._lock:
            return self._bytes

    def close(self):
        with self._lock:
            del self._pending[:]
        self.pre_roll.clear()


def sys_byteorder_swap_needed():
    import sys
    return sys.byteorder != "little"
