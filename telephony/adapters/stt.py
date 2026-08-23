"""STT (Whisper via mlx_audio / transformers) adapter.

Returns a cleaned transcript AND a deterministic 0..1 confidence so the
safety engine can distrust hallucinations (U9):

  * audio-energy gate (both backends): silent audio can only produce a
    whisper hallucination ("Продолжение следует..."), never real speech —
    confidence is pinned low regardless of what the model "heard";
  * whisper segment metrics (mlx path): no_speech_prob / compression_ratio
    (whisper's own hallucination signals) and avg_logprob (length-normalized
    log probability) mapped monotonically to confidence;
  * transformers path: no per-segment metrics are exposed, so confidence is
    the audio-energy gate only (None otherwise) — whisper-small is far less
    hallucination-prone, and the gate catches its worst case (silence).
"""

import array
import wave

from core.dialogue import clean_transcript

# audio-energy gate (mean |sample| normalized to full scale)
SILENCE_ENERGY = 0.004
_LOW_CONF_SILENCE = 0.05
# whisper's own hallucination thresholds (mirrors openai/whisper defaults)
_HALLUCINATED_NO_SPEECH = 0.6
_HALLUCINATED_COMPRESSION = 2.4
_LOW_CONF_HALLUCINATION = 0.15
# avg_logprob (always <= 0, closer to 0 = more confident) -> confidence:
#   -0.4 -> ~1.0, -1.0 -> ~0.57, -1.8 -> 0.0
_LOGPROB_BASE = 1.8
_LOGPROB_RANGE = 1.4


class STTResult:
    __slots__ = ("text", "confidence")

    def __init__(self, text, confidence):
        self.text = text             # cleaned transcript or None
        self.confidence = confidence  # 0..1 or None (unknown)


def audio_energy(wav_path):
    """Mean |sample| of a 16-bit PCM WAV, normalized to [0,1]. Silence ~ 0.

    Any unreadable/invalid wav returns 1.0 (full energy) so the gate only
    ever fires on demonstrably silent audio — never on a decode hiccup.
    """
    try:
        with wave.open(wav_path, "rb") as w:
            frames = w.readframes(w.getnframes())
            if not frames:
                return 0.0
            samples = array.array("h")
            samples.frombytes(frames)
            if not samples:
                return 0.0
            total = 0
            for s in samples:
                total += abs(s)
            return total / (32768.0 * len(samples))
    except Exception:  # noqa: BLE001
        return 1.0


def confidence_from_segments(segments):
    """Whisper segment metrics -> 0..1 confidence (None when unavailable)."""
    segs = list(segments or [])
    if not segs:
        return None
    no_speech = max(s.get("no_speech_prob", 0.0) for s in segs)
    if no_speech > _HALLUCINATED_NO_SPEECH:
        return _LOW_CONF_SILENCE
    compression = max(s.get("compression_ratio", 0.0) for s in segs)
    if compression > _HALLUCINATED_COMPRESSION:
        return _LOW_CONF_HALLUCINATION
    logs = [s.get("avg_logprob", -1.0) for s in segs]
    avg = sum(logs) / len(logs)
    conf = (avg + _LOGPROB_BASE) / _LOGPROB_RANGE
    return round(min(max(conf, _LOW_CONF_SILENCE), 1.0), 3)


def confidence_from_result(wav_path, result):
    """Deterministic STT confidence: audio-energy gate, then segment metrics."""
    if audio_energy(wav_path) < SILENCE_ENERGY:
        return _LOW_CONF_SILENCE
    return confidence_from_segments(getattr(result, "segments", None))


class STTEngine:
    def __init__(self):
        self._model = None

    def _ensure(self):
        if self._model is None:
            import tts_common

            self._model = tts_common.load_stt(tts_common.DEFAULT_STT_MODEL)
        return self._model

    def transcribe(self, wav_path):
        """Raw transcript (unchanged public contract) or None."""
        try:
            model = self._ensure()
            result = model.generate(
                wav_path,
                verbose=False,
                task="transcribe",
                language="ru",
            )
            text = (getattr(result, "text", "") or "").strip()
            return text or None
        except Exception as e:  # noqa: BLE001
            print(f"[call-agent] STT error: {e}", flush=True)
            return None

    def transcribe_with_confidence(self, wav_path):
        """(cleaned transcript, 0..1 confidence | None) as an STTResult."""
        try:
            model = self._ensure()
            result = model.generate(
                wav_path,
                verbose=False,
                task="transcribe",
                language="ru",
            )
        except Exception as e:  # noqa: BLE001
            print(f"[call-agent] STT error: {e}", flush=True)
            return STTResult(None, None)
        raw = (getattr(result, "text", "") or "").strip()
        text = clean_transcript(raw) or None
        return STTResult(text, confidence_from_result(wav_path, result))

    def transcribe_clean(self, wav_path):
        """Cleaned transcript (unchanged public contract) or None."""
        return self.transcribe_with_confidence(wav_path).text