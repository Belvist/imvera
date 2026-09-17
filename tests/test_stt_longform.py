"""STT long-audio fallback: over-limit audio transcribes via longform, not 500."""

from __future__ import annotations

from pathlib import Path

import pytest

import services.stt.worker as stt_worker


class _LongOnlyBackend:
    def __init__(self) -> None:
        self.short_calls = 0
        self.long_calls = 0

    def transcribe_wav(self, wav_path: Path) -> str:
        self.short_calls += 1
        raise ValueError("Too long wav file, use 'transcribe_longform' method.")

    def transcribe_wav_longform(self, wav_path: Path) -> str:
        self.long_calls += 1
        return "длинная речь часть один длинная речь часть два"


class _ShortBackend:
    def __init__(self) -> None:
        self.long_calls = 0

    def transcribe_wav(self, wav_path: Path) -> str:
        return "коротко"

    def transcribe_wav_longform(self, wav_path: Path) -> str:  # pragma: no cover
        self.long_calls += 1
        raise AssertionError("must not be called for short audio")


def _run(backend, tmp_path: Path) -> dict:
    stt_worker._asr = backend  # noqa: SLF001 — seam under test
    wav = tmp_path / "in.wav"
    wav.write_bytes(b"\x00\x00" * 16000)
    try:
        return stt_worker._transcribe_sync(  # noqa: SLF001
            wav,
            pcm=b"\x00\x00" * 16000,
            sample_rate=16000,
            duration_ms=30000,
            asr_cfg={"engine": "gigaam"},
        )
    finally:
        stt_worker._asr = None  # noqa: SLF001


def test_long_audio_falls_back_to_longform(tmp_path: Path) -> None:
    backend = _LongOnlyBackend()
    out = _run(backend, tmp_path)
    assert backend.short_calls == 1
    assert backend.long_calls == 1
    assert "длинная речь" in out["text"]


def test_short_audio_never_touches_longform(tmp_path: Path) -> None:
    backend = _ShortBackend()
    out = _run(backend, tmp_path)
    assert out["text"] == "коротко"
    assert backend.long_calls == 0


def test_window_split_covers_everything_with_overlap() -> None:
    from services.stt.longform import OVERLAP_S, WINDOW_S, split_pcm_windows

    sr = 16000
    pcm = bytes(i % 256 for i in range(sr * 2 * 37))
    wins = split_pcm_windows(pcm, sr)
    assert len(wins) == 3
    assert wins[0] == pcm[: int(WINDOW_S * sr) * 2]
    assert wins[-1].endswith(pcm[-1024:])
    overlap = int(OVERLAP_S * sr) * 2
    assert wins[1][:overlap] == wins[0][-overlap:]


def test_join_collapses_edge_duplicates() -> None:
    from services.stt.longform import join_window_texts

    assert (
        join_window_texts(["ну не знаю вера", "знаешь вот такое", "такое состояние"])
        == "ну не знаю вера знаешь вот такое состояние"
    )
    assert join_window_texts(["", "а"]) == "а"


def test_long_audio_joins_chunks_with_dedup() -> None:
    from services.stt.longform import transcribe_long_audio

    canned = iter(["раз два", "два три", "четыре"])
    out = transcribe_long_audio(
        b"\x00\x00" * 16000 * 37,
        16000,
        lambda _path: next(canned),
    )
    assert out == "раз два три четыре"


def test_unrelated_value_error_still_raises(tmp_path: Path) -> None:
    class _Boom:
        def transcribe_wav(self, wav_path: Path) -> str:
            raise ValueError("CUDA out of memory")

    stt_worker._asr = _Boom()  # noqa: SLF001
    wav = tmp_path / "in.wav"
    wav.write_bytes(b"\x00\x00" * 160)
    try:
        with pytest.raises(ValueError, match="CUDA"):
            stt_worker._transcribe_sync(  # noqa: SLF001
                wav,
                pcm=b"\x00\x00" * 160,
                sample_rate=16000,
                duration_ms=10,
                asr_cfg={"engine": "gigaam"},
            )
    finally:
        stt_worker._asr = None  # noqa: SLF001
