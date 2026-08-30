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
            ch = w.getnchannels()
            frames = w.readframes(w.getnframes())
            if not frames:
                return 0.0
            samples = array.array("h")
            samples.frombytes(frames)
            if not samples:
                return 0.0
            if ch > 1:
                # Stereo mix: LEFT = caller (matches vad_speech_seconds).
                left = [samples[i] for i in range(0, len(samples), ch)]
                samples = array.array("h", left)
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
    """Deterministic STT confidence: audio-energy gate, then segment metrics.

    Qwen3-ASR host has no per-token logprobs — segments is (). The old code
    returned None → safety treated as low (U9) and the harness needed a fake
    0.85. Honest proxy: VAD speech duration vs real-word tokens + vocab gate.
    """
    if audio_energy(wav_path) < SILENCE_ENERGY:
        return _LOW_CONF_SILENCE
    segs = getattr(result, "segments", None)
    conf = confidence_from_segments(segs)
    if conf is not None:
        return conf
    # Host Qwen3 path: no segments — synthesize from human speech physics
    text = (getattr(result, "text", "") or "").strip()
    if not text:
        return None
    # vocab garbage → low, but critical health never gated (see vocab.py)
    try:
        from core.vocab import looks_like_garbage
        if looks_like_garbage(text):
            return _LOW_CONF_HALLUCINATION
    except Exception:
        pass
    speech_s = getattr(result, "speech_s", None)
    if speech_s and speech_s > 0.2:
        import re
        from core.vocab import contains_real_word
        toks = [t for t in re.findall(r"[а-яёa-z]+", text.lower()) if len(t) >= 2]
        # Qwen host: VAD window << utterance on long phone turns (live
        # 9b01: 68 chars / 1.76s → rate 17 → 0.35 → generic). Trust vocab.
        if contains_real_word(text) and len(toks) >= 2:
            if len(toks) >= 8:
                return 0.88
            if len(toks) >= 4:
                return 0.82
            return 0.78
        rate = len(toks) / speech_s if speech_s else 0
        if 1.2 <= rate <= 5.0:
            return 0.82
        if 0.8 <= rate <= 6.0:
            return 0.68
        return 0.35
    if text:
        try:
            from core.vocab import contains_real_word
            if contains_real_word(text):
                return 0.72
        except Exception:
            pass
    return 0.65


class STTEngine:
    def __init__(self):
        self._model = None
        # TRUTHFUL READINESS (2026-08-27): the engine tracks load state so
        # /ready and the warm-up can distinguish "usable" from "broken".
        # Before, a failed load printed "STT ready" unconditionally — the
        # service claimed health while every turn fell back to "Повторите".
        self._ready = False
        self._failed = False

    def _ensure(self):
        if self._ready:
            return self._model
        if self._failed:
            return None
        if self._model is not None:
            # externally injected model (tests/short-circuit) — loaded and
            # usable by construction
            self._ready = True
            return self._model
        try:
            import tts_common

            self._model = tts_common.load_stt(tts_common.DEFAULT_STT_MODEL)
            self._probe_stt_host(self._model)
            self._ready = True
        except Exception as e:  # noqa: BLE001
            print(f"[call-agent] STT load failed: {e}", flush=True)
            self._failed = True
            self._model = None
        return self._model

    @staticmethod
    def _probe_stt_host(model):
        """Log host /ready status; whisper fallback handles a cold host."""
        host_url = None
        if hasattr(model, "_host"):
            inner = model._host
            host_url = getattr(inner, "_host", inner)
        if not host_url or not isinstance(host_url, str):
            return
        try:
            import json
            import urllib.request
            url = host_url.rstrip("/") + "/ready"
            with urllib.request.urlopen(url, timeout=2) as resp:
                obj = json.loads(resp.read().decode("utf-8"))
            if not obj.get("ready"):
                print("[call-agent] STT host not warm yet (%s) — "
                      "whisper fallback active" % url, flush=True)
        except Exception as e:  # noqa: BLE001
            print("[call-agent] STT host /ready probe failed (%s): %s"
                  % (host_url, e), flush=True)

    def ready(self):
        """True when the STT model is actually loaded and usable."""
        return self._ensure() is not None

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