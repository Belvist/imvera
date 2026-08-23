"""Audio format + upload helpers shared by the telephony layers."""

import datetime
import io
import os
import re
import shutil
import tempfile
import wave


def wav_to_pcm(wav_bytes):
    """Extract raw PCM + sample rate from a WAV file."""
    try:
        with wave.open(io.BytesIO(wav_bytes), "rb") as w:
            if w.getsampwidth() != 2 or w.getnchannels() != 1:
                return None, None
            return w.readframes(w.getnframes()), w.getframerate()
    except Exception:  # noqa: BLE001
        return None, None


def pcm_to_wav(pcm, sample_rate):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm)
    return buf.getvalue()


def parse_multipart_wav(raw, ctype):
    m = re.search(r'boundary=(?:"([^"]+)"|([^\s;]+))', ctype or "")
    if not m:
        return None
    boundary = (m.group(1) or m.group(2)).encode()
    for part in raw.split(b"--" + boundary):
        if b"filename=" not in part[:300]:
            continue
        header, _, body = part.partition(b"\r\n\r\n")
        # DATA INTEGRITY FIX: rstrip(b"\r\n--") strips the SET {0x0D,0x0A,
        # 0x2D} from the end — those are ordinary low bytes of PCM samples
        # (and 0x2D is the high byte of negative little-endian values), so
        # real audio was being truncated. Strip exactly the closing CRLF
        # that precedes the next boundary instead.
        if body.endswith(b"\r\n"):
            body = body[:-2]
        fd, path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        with open(path, "wb") as f:
            f.write(body)
        return path
    return None