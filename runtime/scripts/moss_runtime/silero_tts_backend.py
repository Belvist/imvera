"""Silero TTS (ru, v5) backend — high-quality female Russian voice on CPU.

Selected via ``--model silero`` (or ``MOSS_TTS_MODEL=silero``). Requires the
``torch`` + ``silero``-hub checkpoint; the hub repo is cached in
``~/.cache/torch/hub`` after the first load, so the daemon works offline.

Speaker is selected with ``MOSS_SILERO_SPEAKER`` (default ``kseniya`` —
female; alternatives: ``baya``, ``xenia``, male: ``aidar``, ``eugene``).

Interface mirrors what tts_server.TTSWorker needs:
    - ``.tts_model`` (duck alias for itself, so ``.tts_model.sample_rate`` works)
    - ``.generate(...) -> (np.float32 mono, sample_rate, None)``
    - ``.stream_generate(...) -> yields np.float32 mono chunks (sentence-aligned)``
"""
import logging
import os
import sys
import threading

import numpy as np

_LOG = logging.getLogger(__name__)
SILERO_SPEAKER = os.environ.get("MOSS_SILERO_SPEAKER", "kseniya")


def _master(audio: np.ndarray, sr: int) -> np.ndarray:
    """Gentle mastering for phone delivery: soften harsh highs, keep the
    level consistent, never clip. No tempo change (that needs listening)."""
    import numpy as np
    # 1) mild high-shelf soften above ~5.5 kHz (harsh sibilance on phones)
    if sr > 8000:
        from scipy.signal import butter, sosfilt
        sos = butter(2, min(5500, sr / 2 - 300), btype="lowpass",
                     fs=sr, output="sos")
        audio = sosfilt(sos, audio)
    # 2) consistent loudness: RMS target -20 dBFS with 3x max gain
    rms = np.sqrt(np.mean(audio ** 2)) + 1e-9
    target = 0.1
    audio = audio * min(3.0, target / rms)
    # 3) soft limiter (tanh knee) — no hard clipping ever
    peak = np.abs(audio).max()
    if peak > 0.92:
        audio = np.tanh(audio / peak * 1.6) / np.tanh(1.6) * 0.92
    return np.clip(audio, -1.0, 1.0)

# apply_tts keeps natural intonation and pauses across the WHOLE utterance.
# Synthesizing sentence-by-sentence resets prosody every chunk and sounds
# choppy ("не связный"), so the whole text goes into one call whenever it
# fits; only longer texts (> ~200 chars, Silero's practical limit) are split
# at sentence boundaries.
MAX_CHARS_PER_SYNTH = 200

# SSML pauses must not disable Silero homograph stress (prod bug 2026-09-04).
_SILERO_ACCENT_KWARGS = {
    "put_accent": True,
    "put_yo": True,
    "put_stress_homo": True,
    "put_yo_homo": True,
    "stress_single_vowel": True,
}


class SileroTtsBackend:
    _is_qwen3 = False
    sample_rate = 48000
    last_tts_trace: dict | None = None

    def __init__(self):
        self.tts_model = self
        self._model = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ #
    def _ensure_model(self):
        if self._model is not None:
            return self._model
        with self._lock:
            if self._model is None:
                import torch
                model, _ = torch.hub.load(
                    "snakers4/silero-models", "silero_tts",
                    language="ru", speaker="v5_ru", trust_repo=True,
                )
                self._model = model
        return self._model

    def _synth(self, text: str) -> np.ndarray:
        model = self._ensure_model()
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from speech_frontend import build_tts_trace, format_tts_trace_lines, to_ssml

        trace = build_tts_trace(text)
        self.last_tts_trace = trace
        if os.environ.get("MOSS_TTS_TRACE", "0").strip() in ("1", "true", "yes"):
            _LOG.info("TTS_TRACE\n%s", format_tts_trace_lines(trace))

        prepared = trace["TTS_INPUT_NORMALIZED"]
        ssml = None
        if os.environ.get("MOSS_TTS_SSML", "1") == "1":
            try:
                ssml = to_ssml(prepared)
            except Exception:
                ssml = None
        if ssml:
            audio = model.apply_tts(
                ssml_text=ssml,
                speaker=SILERO_SPEAKER,
                sample_rate=self.sample_rate,
                **_SILERO_ACCENT_KWARGS,
            )
        else:
            audio = model.apply_tts(
                text=prepared,
                speaker=SILERO_SPEAKER,
                sample_rate=self.sample_rate,
                **_SILERO_ACCENT_KWARGS,
            )
        if hasattr(audio, "detach"):
            audio = audio.detach().cpu().numpy()
        audio = _master(np.asarray(audio, dtype=np.float32), self.sample_rate)
        return audio

    # ------------------------------------------------------------------ #
    @staticmethod
    def _chunks(text: str):
        """Whole utterance as one chunk; longer texts split at sentence ends."""
        if len(text) <= MAX_CHARS_PER_SYNTH:
            yield text
            return
        from tts_common import split_sentences
        cur = ""
        for seg in split_sentences(text) or [text]:
            if cur and len(cur) + len(seg) > MAX_CHARS_PER_SYNTH:
                yield cur
                cur = seg
            else:
                cur += seg
        if cur:
            yield cur

    def generate(self, text, ref_paths=None, max_len=None, cfg_value=None,
                 inference_steps=None, style_enabled=False, reference_text=None):
        from tts_common import apply_style, normalize_waveform
        text = apply_style(text, style_enabled)
        parts = [self._synth(chunk) for chunk in self._chunks(text)]
        audio = np.concatenate(parts) if len(parts) > 1 else parts[0]
        audio = normalize_waveform(audio)
        return audio, self.sample_rate, None

    def stream_generate(self, text, ref_paths=None, max_len=None, cfg_value=None,
                        inference_steps=None, style_enabled=False, reference_text=None,
                        cancel_event=None):
        from tts_common import apply_style, normalize_waveform, split_sentences
        text = apply_style(text, style_enabled)
        for seg in split_sentences(text) or [text]:
            if cancel_event is not None and cancel_event.is_set():
                return
            yield normalize_waveform(self._synth(seg))