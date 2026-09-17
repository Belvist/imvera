"""Chunked transcription for audio over the single-pass model limit (~25s).

Fixed windows + overlap + word-boundary dedup. No new dependencies
(deliberately not gigaam.transcribe_longform: it needs gated pyannote
weights). Input is already one VAD utterance; seams land mid-stream, so
every window overlaps the previous one and duplicated edge words collapse.
"""

from __future__ import annotations

import wave
from collections.abc import Callable
from pathlib import Path

WINDOW_S = 18.0
OVERLAP_S = 2.0
MAX_EDGE_DUP_WORDS = 10


def split_pcm_windows(pcm: bytes, sample_rate: int) -> list[bytes]:
    """Split mono s16le PCM into overlapping windows."""
    frame = max(1, int(WINDOW_S * sample_rate) * 2)
    overlap = max(1, int(OVERLAP_S * sample_rate) * 2)
    if len(pcm) <= frame:
        return [pcm]
    out: list[bytes] = []
    start = 0
    while start < len(pcm):
        out.append(pcm[start : start + frame])
        if start + frame >= len(pcm):
            break
        start += frame - overlap
    return out


def _collapse_edge_dup(prev_words: list[str], words: list[str]) -> list[str]:
    for k in range(min(MAX_EDGE_DUP_WORDS, len(prev_words), len(words)), 0, -1):
        if prev_words[-k:] == words[:k]:
            return words[k:]
    return words


def join_window_texts(texts: list[str]) -> str:
    words: list[str] = []
    for text in texts:
        parts = text.split()
        if not parts:
            continue
        words.extend(_collapse_edge_dup(words, parts))
    return " ".join(words).strip()


def transcribe_long_audio(
    pcm: bytes,
    sample_rate: int,
    transcribe_wav: Callable[[Path], str],
) -> str:
    """Transcribe long PCM by overlapping windows; returns joined text."""
    import tempfile

    texts: list[str] = []
    for window in split_pcm_windows(pcm, sample_rate):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            path = Path(tmp.name)
        try:
            with wave.open(str(path), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes(window)
            texts.append(transcribe_wav(path))
        finally:
            path.unlink(missing_ok=True)
    return join_window_texts(texts)
