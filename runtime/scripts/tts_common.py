#!/usr/bin/env python3
"""Shared helpers for MOSS-TTS-Nano + STT pipeline."""
import hashlib
import os
import re
import tempfile
import threading

import numpy as np

DEFAULT_STT_MODEL = "mlx-community/whisper-large-v3-turbo-asr-fp16"
# MOSS-TTS-Nano (OpenMOSS/MOSI.AI, apache-2.0): ~0.1B multilingual zero-shot
# voice-clone TTS that runs on CPU (ONNX, no GPU needed). Native output is
# 48 kHz. Clones a voice from a reference audio; falls back to a built-in
# voice otherwise (MOSS_TTS_VOICE, default "Ava").
DEFAULT_TTS_MODEL = "moss-tts-nano"

CFG_VALUE = 1.5
INFERENCE_TIMESTEPS = 14
STYLE_INSTRUCTION = ""
# Language pinned to Russian everywhere: Whisper auto-detect is a top source
# of ref_text drift, and a fixed language keeps the RU prompts clean
# (P0-STT-002 / P1-TTS-005).
STT_LANGUAGE = os.environ.get("MOSS_STT_LANGUAGE", "ru")
REF_PREPROC_VERSION = "2"

# Inline markers: rendered as natural pauses, never as words the model would
# read aloud. Instruction tokens like "[sigh]" / "[laugh]" must never reach
# the TTS verbatim — mapping them to spoken words makes the model say
# "вздыхает" out loud (fake-emotion bug; P1-TTS-004).
_PAUSE_RE = re.compile(r"\[pause:\s*(\d+(?:\.\d+)?)\s*(ms|s)?\]")
_TAG_RE = re.compile(r"\[[a-z_]+\]")

# Native rate of the MOSS-Audio-Tokenizer-Nano codec is 48 kHz. Keeping the
# merged reference at 48 kHz avoids the legacy 16 kHz downsample round trip
# (48k -> 16k -> 48k) that destroyed timbre and read as a foreign accent.
REFERENCE_SAMPLE_RATE = int(os.environ.get("MOSS_REFERENCE_SAMPLE_RATE", "48000"))
REFERENCE_MAX_SECONDS = 15.0

SENTENCE_SPLIT = re.compile(
    r"(?<=[.!?…])\s+|(?<=[.!?…])\s*\n+",
)

_REF_CACHE_LOCK = threading.Lock()


def hash_file_size(path):
    """Fast content fingerprint: mtime + size. Good enough to invalidate the
    reference-prompt cache when the voice sample is replaced."""
    try:
        st = os.stat(path)
        return f"{int(st.st_mtime_ns)}-{st.st_size}"
    except OSError:
        return None


def hash_references(ref_paths):
    """Key for the per-voice prompt/transcript cache."""
    if not ref_paths:
        return None
    parts = []
    for p in ref_paths:
        if p and os.path.exists(p):
            parts.append(f"{os.path.basename(p)}:{hash_file_size(p)}")
    if not parts:
        return None
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def normalize_waveform(audio, target_peak=0.95, window=1024, max_boost=2.0):
    """Loudness-stabilize a waveform: compensate tail/quiet sections via AGC.

    Peak-normalization leaves the tail "distant" (volume decays) and makes
    residual hiss audible when the voice goes quiet. We compute a slow local
    RMS envelope, gently raise quiet/tail sections toward the clip's average,
    cap the gain (so the noise floor is not pumped), then peak-limit.
    """
    audio = np.asarray(audio, dtype=np.float32)
    if audio.size == 0:
        return audio
    energy = np.convolve(audio ** 2, np.ones(window) / window, mode="same")
    env = np.sqrt(np.maximum(energy, 1e-9))
    ref = float(np.mean(env)) + 1e-9
    gain = np.minimum(ref / env, np.array(max_boost, dtype=np.float32))
    out = audio * gain
    peak = float(np.max(np.abs(out)))
    if peak > 0.0:
        out = out * (target_peak / peak)
    return np.clip(out, -1.0, 1.0)


def highpass_audio(audio, sample_rate, cutoff=80.0, order=4):
    """Remove low-frequency hum that the codec otherwise turns into rumble/hiss."""
    audio = np.asarray(audio, dtype=np.float32)
    if audio.size == 0 or sample_rate <= 0 or cutoff <= 0:
        return audio
    import scipy.signal as sig

    b, a = sig.butter(order, cutoff / (sample_rate / 2.0), btype="high")
    return sig.filtfilt(b, a, audio).astype(np.float32)


def merge_references(ref_paths, output_path=None):
    """    Merge one or more reference WAVs into a single mono WAV file.

    The TTS backend takes audio via file paths, so the app's normalized clips are
    resampled and merged into one prompt file.

    Returns the path to the merged file, or None if no valid reference exists.
    """
    if not ref_paths:
        return None
    paths = [p for p in ref_paths if p and os.path.exists(p)]
    if not paths:
        return None

    try:
        import librosa
    except Exception:  # noqa: BLE001
        librosa = None

    waves = []
    sr = None
    for p in paths:
        if librosa is not None:
            data, rate = librosa.load(p, sr=REFERENCE_SAMPLE_RATE, mono=True)
        else:
            import soundfile as sf

            data, rate = sf.read(p, dtype="float32", always_2d=False)
            if data.ndim > 1:
                data = data.mean(axis=1)
            if rate != REFERENCE_SAMPLE_RATE:
                import scipy.signal as sig

                samples = int(round(len(data) * REFERENCE_SAMPLE_RATE / rate))
                data = sig.resample_poly(
                    data,
                    REFERENCE_SAMPLE_RATE,
                    rate,
                    window=("kaiser", 5.0),
                )[:samples]
        if sr is None:
            sr = REFERENCE_SAMPLE_RATE
        waves.append(data.astype(np.float32))

    if not waves:
        return None

    audio = np.concatenate(waves)
    max_samples = int(REFERENCE_MAX_SECONDS * sr)
    if len(audio) > max_samples:
        audio = audio[:max_samples]

    audio = highpass_audio(audio, sr, cutoff=80.0)

    if output_path is None:
        fd, output_path = tempfile.mkstemp(suffix=".wav", prefix="moss-ref-")
        os.close(fd)

    import soundfile as sf

    sf.write(output_path, audio, sr)
    return output_path


def audio_seconds(path):
    """Return the duration of a WAV/audio file in seconds, or None."""
    try:
        import soundfile as sf

        info = sf.info(path)
        return float(info.frames) / float(info.samplerate)
    except Exception:  # noqa: BLE001
        return None


def transcribe_reference(ref_paths, stt_model, fallback_text="", language="ru"):
    """Return the transcript text for reference audio.

    Uses the provided STT model when available, otherwise a fallback string.
    Transcribes each source clip separately and returns their concatenation —
    caller code that feeds this text to ``merge_references`` must ensure the
    audio/transcript windows match (prefer ``transcribe_merged`` inside the
    daemon where the merged clip obeying REFERENCE_MAX_SECONDS is known).
    """
    if not ref_paths:
        return None
    paths = [p for p in ref_paths if p and os.path.exists(p)]
    if not paths:
        return None
    if stt_model is not None:
        try:
            texts = []
            for p in paths:
                result = stt_model.generate(p, verbose=False, task="transcribe", language=language)
                text = getattr(result, "text", "").strip()
                if text:
                    texts.append(text)
            if texts:
                return " ".join(texts)
        except Exception:  # noqa: BLE001
            pass
    return (fallback_text or "").strip() or None


def transcribe_merged(merged_path, stt_model, language="ru"):
    """Transcribe the *merged* reference clip itself.

    This is the alignment fix for REFERENCE_MAX_SECONDS truncation: the audio
    actually fed to the model is the merged (and possibly 15 s-chopped) file,
    so transcribing it yields a transcript that always matches the audio.
    Returns (text, audio_seconds) or (None, None).
    """
    if not merged_path or not os.path.exists(merged_path):
        return None, None
    secs = audio_seconds(merged_path)
    if stt_model is None:
        return None, secs
    try:
        result = stt_model.generate(merged_path, verbose=False, task="transcribe", language=language)
        text = getattr(result, "text", "").strip()
        return (text or None), secs
    except Exception:  # noqa: BLE001
        return None, secs


def validate_reference(ref_path, language="ru"):
    """Sanity-check a reference clip before it is used for cloning.

    Returns (status, reasons) where status is "GOOD" | "WARNING" | "REJECT".
    Checks that cheaply run without a model: file decodes, sample rate,
    duration bounds, silence / overload, and (best-effort) plain speech by
    measuring how much of the clip has non-trivial RMS.

    This catches the "recorded a click, gave silence, gave music" failure
    modes before the expensive prompt-cache build happens — the top cause of
    "голос ломается" complaints.
    """
    import soundfile as sf

    reasons = []
    try:
        info = sf.info(ref_path)
        if info.channels < 1:
            return "REJECT", ["файл без аудиоканалов"]
        if info.samplerate <= 0:
            return "REJECT", ["некорректный sample rate"]
    except Exception as exc:  # noqa: BLE001
        return "REJECT", [f"не удалось прочитать файл: {exc}"]

    if info.frames == 0:
        return "REJECT", ["файл пустой"]

    duration = float(info.frames) / float(info.samplerate)
    if duration < 1.0:
        reasons.append(f"очень короткая запись ({duration:.1f} с, рекомендуется ≥5 с)")
    if duration > REFERENCE_MAX_SECONDS:
        reasons.append(
            f"запись {duration:.1f} с — длиннее лимита {REFERENCE_MAX_SECONDS:.0f} с; "
            f"хвост будет обрезан, голос может «скакнуть»"
        )

    try:
        data, rate = sf.read(ref_path, dtype="float32", always_2d=False)
        if data.ndim > 1:
            data = data.mean(axis=1)
        peak = float(np.max(np.abs(data))) if data.size else 0.0
        rms = float(np.sqrt(np.mean(data ** 2))) if data.size else 0.0
        if peak < 1e-4:
            reasons.append("похоже на тишину (пик почти нулевой)")
        else:
            if peak > 0.99:
                reasons.append("сильное ограничение амплитуды (клип / distortion на пиках)")
            if rms < 0.005:
                reasons.append("запись слишком тихая для клонирования")
            # speech-ish ratio: fraction of frames above 1/20 of peak envelope
            env_win = max(256, int(0.02 * rate))
            energy = np.convolve(data ** 2, np.ones(env_win) / env_win, mode="same")
            env = np.sqrt(np.maximum(energy, 1e-12))
            speech_thr = 0.05 * (float(np.max(env)) + 1e-9)
            speech_ratio = float(np.mean(env > speech_thr) if env.size else 0.0)
            if 0.0 < speech_ratio < 0.10 and duration >= 1.0:
                reasons.append(
                    f"похоже, речь занимает всего {speech_ratio * 100:.0f}% записи "
                    f"(фон/паузы могут преобладать)"
                )
    except Exception as exc:  # noqa: BLE001
        reasons.append(f"не удалось анализировать аудио: {exc}")

    if any("пустой" in r or "тишину" in r or "корректный" in r or "читать" in r for r in reasons):
        return "REJECT", reasons
    if reasons:
        return "WARNING", reasons
    return "GOOD", ["образец пригоден"]


def load_stt(model_id=DEFAULT_STT_MODEL):
    """Load the Whisper STT model once.

    Prefers the MLX backend (fast on Apple Silicon). Falls back to a
    transformers Whisper model when mlx is unavailable (e.g. inside the
    isolated runtime venv).
    """
    try:
        from mlx_audio.stt import load as stt_load

        return stt_load(model_id)
    except Exception:
        pass
    from transformers import pipeline

    hf_id = os.environ.get(
        "MOSS_STT_TRANSFORMERS_MODEL", "openai/whisper-large-v3-turbo"
    )
    return WhisperPipelineAdapter(hf_id)


class WhisperPipelineAdapter:
    """Duck-typed like mlx_audio STT: exposes `.generate(path, ...).text`."""

    def __init__(self, model_id):
        from transformers import pipeline

        self._pipe = pipeline(
            "automatic-speech-recognition",
            model=model_id,
            chunk_length_s=30,
            batch_size=8,
        )
        self._id = model_id

    @staticmethod
    def _read(path):
        """Decode a 16-bit mono WAV with the stdlib so no ffmpeg/sox binary
        is required (Docker images ship without it). Returns the
        {"raw","sampling_rate"} dict the HF pipeline consumes; falls back to
        the raw path when the file isn't a simple PCM WAV."""
        try:
            import wave as _wave

            import numpy as _np

            with _wave.open(path, "rb") as w:
                if w.getsampwidth() == 2 and w.getnchannels() == 1:
                    pcm = w.readframes(w.getnframes())
                    sr = w.getframerate()
                    raw = _np.frombuffer(pcm, dtype=_np.int16).astype(_np.float32)
                    raw = raw / 32768.0
                    return {"raw": raw, "sampling_rate": sr}
        except Exception:  # noqa: BLE001
            pass
        return path

    def generate(self, path, verbose=False, task="transcribe", language="ru", **kwargs):
        out = self._pipe(
            self._read(path),
            generate_kwargs={"task": task, "language": language if language else None},
            return_timestamps=False,
        )
        text = (out or {}).get("text") if isinstance(out, dict) else getattr(out, "text", "")
        return type("R", (), {"text": text})()


def load_tts(model_id=DEFAULT_TTS_MODEL, device="auto", optimize=False):
    """Load the TTS model. Returns a backend object exposing ``.tts_model``.

    MOSS-TTS-Nano (ONNX CPU) is the only backend. MOSS_TTS_MODEL_DIR points at
    the weights directory; it is downloaded automatically on first run.
    """
    from moss_backend import load_tts as load_moss_tts

    return load_moss_tts(model_id)


def expand_inline(text: str) -> str:
    """Strip inline markers, mapping them to natural pauses.

    ``[pause:800ms]`` => "…", any other ``[tag]`` is dropped entirely (it must
    never be read aloud by the model). Applied consistently across backends so
    MLX and Torch produce the same clean input. P1-TTS-004.
    """
    if not text:
        return text
    text = _PAUSE_RE.sub(lambda _m: "…", text)
    text = _TAG_RE.sub("", text)
    return text.strip()


def apply_style(text, enable=False):
    """Normalize inline markers for synthesis (also called per request so TTS
    never sees raw ``[sigh]``/``[laugh]`` tokens). ``enable`` is kept for API
    compatibility; on Base models there is no instruction channel, so style
    control is limited to pauses — all inline tags are handled identically.
    """
    text = expand_inline(text)
    if not enable:
        return text
    return text


def split_sentences(text, max_len=160):
    """Split into sentence-aligned chunks for low start-latency streaming.
    The first chunk is kept deliberately short so audio begins quickly."""
    pieces = []
    for line in text.splitlines() or [text]:
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in SENTENCE_SPLIT.split(line) if p.strip()]
        for p in parts:
            while p and len(p) > max_len:
                cut = max_len
                space = p.rfind(" ", 0, cut + 1)
                if space > cut * 0.6:
                    cut = space
                pieces.append(p[:cut])
                p = p[cut:].strip()
            if p:
                pieces.append(p)
    return pieces


def split_long_text(text, max_chars=300):
    """Split long text into sentence-aligned segments to keep generation stable."""
    segments = []
    current = ""
    for line in text.splitlines() or [text]:
        piece = line.strip()
        if not piece:
            continue
        if len(current) + len(piece) + 1 <= max_chars:
            current = f"{current} {piece}" if current else piece
        else:
            if current:
                segments.append(current)
            current = piece
    if current:
        segments.append(current)
    return segments or [text]


def build_prompt_cache(model, merged_ref_path, ref_text=None):
    """Build (and return) the reusable per-voice cache descriptor.

    MOSS-TTS-Nano clones zero-shot from the reference audio when present and
    falls back to a built-in voice otherwise, so both paths return a usable
    cache. Legacy engines that strictly required a reference keep the guard.
    """
    m = model.tts_model
    needs_ref = getattr(m, "_is_qwen3", True)
    if needs_ref and (not merged_ref_path or not os.path.exists(merged_ref_path)):
        return None
    return m.build_prompt_cache(
        reference_wav_path=merged_ref_path, ref_text=ref_text
    )


def _to_mono_waveform(wav):
    """Normalize a backend waveform to a 1-D np.float32 numpy array.

    ONNX backends already return a mono numpy array; defensive conversion
    for tensor-shaped (1, samples) returns is applied as well.
    """
    if hasattr(wav, "cpu"):  # torch tensor
        wav = wav.cpu().numpy()
    wav = np.asarray(wav, dtype=np.float32)
    if wav.ndim == 2:
        if min(wav.shape) == 1:
            wav = wav.reshape(-1)
        else:
            wav = wav.mean(axis=1)
    return wav.astype(np.float32)


def generate_single(
    tts_model,
    text,
    prompt_cache,
    cfg_value=CFG_VALUE,
    inference_timesteps=INFERENCE_TIMESTEPS,
    min_len=2,
    max_len=2000,
):
    """Synthesize a full utterance at once (non-streaming decode) using a
    pre-built prompt cache. Returns a single np.float32 waveform."""
    if not prompt_cache:
        raise ValueError("prompt cache is required for voice cloning")
    wav, _tokens, _feat = tts_model.generate_with_prompt_cache(
        target_text=text,
        prompt_cache=prompt_cache,
        min_len=min_len,
        max_len=max_len,
        inference_timesteps=inference_timesteps,
        cfg_value=cfg_value,
    )
    return _to_mono_waveform(wav)


def generate_stream_chunks(
    tts_model,
    text,
    prompt_cache,
    cfg_value=CFG_VALUE,
    inference_timesteps=INFERENCE_TIMESTEPS,
    min_len=2,
    max_len=2000,
):
    """Synthesize in streaming chunks using a pre-built prompt cache.

    Yields np.float32 waveform chunks (and a final flag via StopIteration is
    indicated by the caller finishing the loop). Raises if generation fails.
    """
    if not prompt_cache:
        raise ValueError("prompt cache is required for voice cloning")
    gen = tts_model._generate_with_prompt_cache(
        target_text=text,
        prompt_cache=prompt_cache,
        min_len=min_len,
        max_len=max_len,
        inference_timesteps=inference_timesteps,
        cfg_value=cfg_value,
        streaming=True,
        streaming_prefix_len=4,
    )
    try:
        for item in gen:
            wav = item[0] if isinstance(item, tuple) else item
            yield _to_mono_waveform(wav)
    except GeneratorExit:
        try:
            gen.close()
        except Exception:  # noqa: BLE001
            pass
        raise
