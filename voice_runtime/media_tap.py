"""Live media tape: tail-read a `uuid_record` WAV while it is still growing.

Fixes over the step-5 POC (`esl_stream.py`):
  * no sample loss — `read_new()` returns ALL bytes appended since the last
    read; the POC's `read_new()[:PCM_CHUNK]` discarded the surplus forever;
  * partial trailing frames are buffered across reads (`_pending`) instead
    of silently dropped, so the STT never sees a spliced sample;
  * real-world tape params are parsed from the fmt chunk — channel count
    AND sample rate — so an 8 kHz u-law/PCM leg (G.711 caller) is resampled
    to the 16 kHz the VAD/STT expect, instead of being misread as 16 kHz;
  * broken/empty WAVs are REFUSED (`broken` flag): this FS build writes
    garbage 44-byte files after a bad record_stereo state, and feeding them
    to VAD/STT made the assistant "hear" hallucinated speech (she answered
    nonsense). A valid header must be present before any sample is emitted.
"""
import os
import struct
import wave

from media_adapter import MediaAdapter  # noqa: E402

SAMPLE_RATE = 16000
WAV_HEADER = 44
_BYTES_PER_SAMPLE = 2


def resample_linear(samples, src_rate, dst_rate):
    """Linear-interpolation resample (no numpy on this host).

    Handles 8 kHz -> 16 kHz (G.711 legs) and keeps equal rates untouched.
    O(n) in output length; fine for 30 ms VAD chunks.
    """
    if src_rate == dst_rate or not samples:
        return samples
    n = len(samples)
    out_len = max(1, int(n * dst_rate / src_rate))
    out = [0] * out_len
    for i in range(out_len):
        pos = i * src_rate / dst_rate
        lo = int(pos)
        if lo >= n - 1:
            out[i] = samples[-1]
            continue
        frac = pos - lo
        out[i] = int(samples[lo] * (1.0 - frac) + samples[lo + 1] * frac)
    return out


class LiveWavReader(MediaAdapter):
    """Tail-reader for a growing `uuid_record` WAV (DEV-ONLY, read.md G2).

    Implements the ``MediaAdapter`` contract so the VAD/turn loop does not
    care which transport delivers media. The production cutover replaces this
    with a continuous PCM stream (ESL media bug / WebSocket / RTP); until
    then ``uuid_record`` remains the dev adapter only.

    Emits int16 mono samples (LEFT channel when stereo) resampled to the
    requested rate. ``broken`` is True once the file is proven NOT a valid
    WAV (the 44-byte garbage headers of a failed record_stereo) — callers
    must stop feeding VAD/STT in that case.
    """

    def __init__(self, path):
        super().__init__()
        self.path = path
        self._pos = 0
        self._header_seen = False
        self._channels = 1
        self._rate = SAMPLE_RATE
        self._pending = b""

    @staticmethod
    def _parse_header(head):
        """``(channels, sample_rate)`` for a standard RIFF/WAVE PCM header,
        or ``None`` when the block is not a valid fixed-offset WAV header."""
        if len(head) < WAV_HEADER:
            return None
        if head[:4] != b"RIFF" or head[8:12] != b"WAVE" \
                or head[36:40] != b"data":
            return None
        try:
            fmt = struct.unpack("<H", head[20:22])[0]
            nch = struct.unpack("<H", head[22:24])[0]
            rate = struct.unpack("<I", head[24:28])[0]
            bits = struct.unpack("<H", head[34:36])[0]
        except struct.error:
            return None
        if fmt != 1 or nch not in (1, 2) or bits != 16:
            return None
        if not (1000 <= rate <= 96000):
            return None
        return nch, rate

    def probe(self):
        """Parse/validate the header if it has landed.

        Returns ``channels`` when the tape is a valid WAV (header consumed),
        ``None`` while the header is still incomplete, and flags
        ``self.broken`` when the block is definitively garbage.
        """
        if self.broken or self._header_seen:
            return self._channels if not self.broken else None
        size = self.size
        if size < WAV_HEADER:
            return None
        try:
            with open(self.path, "rb") as f:
                head = f.read(WAV_HEADER)
        except OSError:
            return None
        parsed = self._parse_header(head)
        if parsed is None:
            self.broken = True
            return None
        self._channels, self._rate = parsed
        self._header_seen = True
        self._pos = WAV_HEADER
        return self._channels

    def read_new(self, rate=SAMPLE_RATE):
        """int16 LEFT-channel samples written since the last call, resampled
        to ``rate``. Returns ``[]`` until a VALID header has been seen; after
        a broken file is detected it keeps returning ``[]`` (never garbage)."""
        probe = self.probe()
        if probe is None:
            return []
        size = self.size
        if size <= self._pos:
            return []
        try:
            with open(self.path, "rb") as f:
                f.seek(self._pos)
                data = f.read(size - self._pos)
        except OSError:
            return []
        self._pos = size
        data = self._pending + data
        frame = 2 * self._channels
        complete = len(data) - (len(data) % frame)
        self._pending = data[complete:]
        data = data[:complete]
        if not data:
            return []
        vals = struct.unpack("<%dh" % (len(data) // 2), data)
        if self._channels == 2:
            vals = vals[0::2]  # record_stereo: LEFT = caller
        if self._rate != rate:
            vals = resample_linear(vals, self._rate, rate)
        return list(vals)

    @property
    def channels(self):
        return self._channels

    @property
    def rate(self):
        return self._rate

    @property
    def size(self):
        try:
            return os.path.getsize(self.path)
        except OSError:
            return 0

    def audio_bytes(self):
        """Bytes of PCM payload written so far (0 while header/waiting)."""
        if self.broken or not self._header_seen:
            return 0
        size = self.size
        return max(0, size - WAV_HEADER)

    # MediaAdapter contract alias (read.md G2): the VAD loop calls
    # frames_in(); LiveWavReader implements it as the tail-read.
    def frames_in(self, rate=SAMPLE_RATE):
        return self.read_new(rate=rate)


def write_wav(path, samples, rate=SAMPLE_RATE):
    """int16 mono sample sequence -> WAV on disk (atomic)."""
    tmp = path + ".tmp"
    with wave.open(tmp, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(_BYTES_PER_SAMPLE)
        w.setframerate(int(rate))
        if isinstance(samples, (bytes, bytearray)):
            w.writeframes(bytes(samples))
        else:
            w.writeframes(struct.pack("<%dh" % len(samples), *samples))
    os.replace(tmp, path)
    return path


def read_pcm(path, channels=None, rate=None):
    """Whole-file reader for verification/test helper (not hot path)."""
    with wave.open(path, "rb") as w:
        nch = w.getnchannels()
        frames = w.readframes(w.getnframes())
    vals = struct.unpack("<%dh" % (len(frames) // 2), frames)
    if channels == "left" or (channels is None and nch == 2):
        vals = vals[0::2]
    return list(vals), nch