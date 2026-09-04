#!/usr/bin/env python3
"""Shared helpers for MOSS-TTS-Nano + STT pipeline."""
import hashlib
import json
import os
import re
import tempfile
import threading
import urllib.error
import urllib.request

import numpy as np

DEFAULT_STT_MODEL = "mlx-community/whisper-large-v3-turbo-asr-fp16"
# Qwen3-ASR host service (voice_runtime/stt_host.py). When MOSS_STT_HOST is
# set, load_stt() prefers this HTTP endpoint — the Qwen3-ASR model runs on
# Apple Silicon (MLX) on the host and beats whisper-small on real Russian
# phone audio (measured 2026-08-29: "настроение" correctly, 0.2-1.8s/file).
STT_HOST = os.environ.get("MOSS_STT_HOST", "")
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
    """Load the STT model once.

    Prefers the Qwen3-ASR host service (Apple Silicon, MLX) when
    MOSS_STT_HOST is set — it beats whisper on real Russian phone audio.
    Then the MLX backend (host, fast on Apple Silicon), then faster-whisper
    (CTranslate2 — 3-4x faster than transformers on CPU), and finally the
    transformers Whisper pipeline.
    """
    if STT_HOST:
        try:
            host = SttHostAdapter()
            try:
                fb = FasterWhisperAdapter(os.environ.get(
                    "MOSS_STT_TRANSFORMERS_MODEL",
                    "openai/whisper-large-v3-turbo",
                ))
                return SttHostWithFallback(host, fb)
            except Exception:
                return host
        except Exception:
            pass
    try:
        from mlx_audio.stt import load as stt_load

        return stt_load(model_id)
    except Exception:
        pass
    try:
        return FasterWhisperAdapter(os.environ.get(
            "MOSS_STT_TRANSFORMERS_MODEL", "openai/whisper-large-v3-turbo"
        ))
    except Exception:
        pass
    from transformers import pipeline

    hf_id = os.environ.get(
        "MOSS_STT_TRANSFORMERS_MODEL", "openai/whisper-large-v3-turbo"
    )
    return WhisperPipelineAdapter(hf_id)


_SILERO_VAD = None
_SILERO_VAD_TS = None
# RLock guards BOTH loading and INFERENCE: the Silero v5 TorchScript model
# keeps its LSTM state inside the module and is NOT thread-safe. Under
# concurrent calls (parallel phone turns -> STT gate + /has_speech) two
# threads interleaving on the same state produced "select(): index out of
# range" and eventually glibc "double free or corruption" -> SIGABRT.
# Inference on a <=5 s chunk costs ~10-50 ms, so serializing is free.
_SILERO_VAD_LOCK = threading.RLock()


def _get_silero_vad():
    """Lazy-load Silero VAD (tiny, ~1 MB) — the authoritative speech/noise
    separator. Cached process-wide."""
    global _SILERO_VAD, _SILERO_VAD_TS
    if _SILERO_VAD is not None:
        return _SILERO_VAD
    with _SILERO_VAD_LOCK:
        if _SILERO_VAD is None:
            import torch
            model, utils = torch.hub.load("snakers4/silero-vad", "silero_vad",
                                          trust_repo=True)
            _SILERO_VAD = model
            # hub returns (model, utils); get_speech_timestamps lives there
            _SILERO_VAD_TS = (utils["get_speech_timestamps"]
                              if isinstance(utils, dict)
                              else getattr(utils, "get_speech_timestamps",
                                           utils[0]))
    return _SILERO_VAD


def vad_speech_seconds(path: str, tail_s: float = None):
    """Seconds of real human speech in a wav file (Silero VAD).
    tail_s: only inspect the LAST N seconds (endpointing cares about the
    chunk tail, not its beginning).
    Returns None when the VAD itself is unavailable — callers must FAIL OPEN
    (treat as speech) instead of going deaf."""
    import wave as _wave
    import numpy as np
    try:
        with _wave.open(path, "rb") as w:
            sr = w.getframerate()
            ch = w.getnchannels()
            raw = w.readframes(w.getnframes())
    except Exception:  # noqa: BLE001
        return None
    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        # record_stereo (FreeSWITCH): LEFT = caller read stream, RIGHT =
        # played audio (Vera). Keep LEFT only — Vera's playback must not
        # count as caller speech in the endpointing gate.
        audio = audio.reshape(-1, ch)[:, 0]
    if tail_s is not None and len(audio) > int(tail_s * sr):
        audio = audio[-int(tail_s * sr):]
    if sr != 16000:
        from scipy.signal import resample_poly
        import math
        g = math.gcd(sr, 16000)
        audio = resample_poly(audio, 16000 // g, sr // g)
        sr = 16000
    try:
        import torch
        with _SILERO_VAD_LOCK:
            model = _get_silero_vad()
            ts = _SILERO_VAD_TS(torch.from_numpy(audio), model,
                                sampling_rate=16000, return_seconds=True)
    except Exception as e:  # noqa: BLE001
        print(f"[vad] unavailable ({e}) — failing open", flush=True)
        return None
    secs = sum(float(t["end"]) - float(t["start"]) for t in ts)
    # ENERGY FLOOR: a phone microphone hears the CALLER much louder than a
    # TV across the room. Speech detected by VAD but this quiet is
    # background voice (TV/neighbours), not the caller -> not a turn.
    if ts and secs > 0:
        frame = int(sr * 0.03)
        energies = []
        for t in ts:
            s0 = int(float(t["start"]) * sr)
            s1 = min(int(float(t["end"]) * sr), len(audio))
            seg = audio[s0:s1]
            for k in range(0, max(1, len(seg) - frame), frame):
                energies.append(np.sqrt(np.mean(seg[k:k + frame] ** 2)))
        if energies and float(np.median(energies)) < 0.004:
            return 0.0
    return secs


def mean_audio_energy(path: str) -> float:
    """Mean |sample| normalized to [0,1] — matches telephony adapters.stt."""
    import wave as _wave
    try:
        with _wave.open(path, "rb") as w:
            ch = w.getnchannels()
            raw = w.readframes(w.getnframes())
        if not raw:
            return 0.0
        import numpy as np
        audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        if ch > 1:
            audio = audio.reshape(-1, ch)[:, 0]
        return float(np.mean(np.abs(audio)))
    except Exception:  # noqa: BLE001
        return 1.0


# Quiet elderly phone speech often lands 0.003–0.007 mean energy — below
# Silero's TV-rejection floor but still real voice; trust STT host when
# energy clears the orchestrator silence gate (0.002).
_STT_HOST_MIN_ENERGY = 0.002

class SttHostAdapter:
    """Duck-typed like mlx_audio STT: exposes `.generate(path, ...).text`.

    Delegates to the Qwen3-ASR host service (voice_runtime/stt_host.py).
    The container cannot run MLX, so the model lives on the host and this
    adapter is the transport. Same `.generate` contract as the whisper
    adapters (used by STTEngine.transcribe_with_confidence).
    """

    def __init__(self, host=None, timeout=60):
        self._host = (host or STT_HOST).rstrip("/")
        self._timeout = timeout
        self._id = "qwen3-asr-host"
        if not self._host:
            raise ValueError("MOSS_STT_HOST is empty")

    def _wav(self, path):
        """Read a wav file into memory (max 50 MB)."""
        with open(path, "rb") as f:
            data = f.read()
        if len(data) > 50 * 1024 * 1024:
            raise ValueError("audio too large for host STT")
        return data

    def generate(self, path, verbose=False, task="transcribe", language="ru",
                 **kwargs):
        class _R:
            text = ""
            segments = ()
            speech_s = 0.0

        # NOISE GATE pass 1: Silero VAD — skip only when BOTH no VAD speech
        # AND file energy is below the phone silence gate. Quiet callers
        # (live c112a3017a2f: en=0.0044, vad=0) must still reach Qwen host.
        vad_speech = vad_speech_seconds(path)
        energy = mean_audio_energy(path)
        r = _R()
        if vad_speech is not None and vad_speech < 0.15 and energy < _STT_HOST_MIN_ENERGY:
            return r
        r.speech_s = vad_speech if vad_speech is not None else max(energy * 2.0, 0.2)
        boundary = "--mossstt" + hashlib.md5(path.encode()).hexdigest()[:8]
        payload = self._wav(path)
        body = (("--%s\r\nContent-Disposition: form-data; name=\"file\"; "
                 "filename=\"turn.wav\"\r\nContent-Type: audio/wav\r\n\r\n")
                % boundary).encode("utf-8") + payload + \
            ("\r\n--%s--\r\n" % boundary).encode("utf-8")
        req = urllib.request.Request(
            self._host + "/transcribe", data=body,
            headers={"Content-Type": "multipart/form-data; boundary=%s"
                     % boundary},
            method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                obj = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            print("[stt-host] HTTP %d: %s"
                  % (e.code, e.read().decode("utf-8", "replace")[:120]),
                  flush=True)
            return r
        except Exception as e:  # noqa: BLE001
            print("[stt-host] error: %s" % e, flush=True)
            return r
        r.text = (obj.get("text") or "").strip()
        # Честно: у Qwen3-ASR нет per-token logprob — segments остаётся (),
        # confidence синтезирует stt.py: VAD speech_s vs токены + vocab.
        # Не фейкуем 1.0 здесь.
        return r


class SttHostWithFallback:
    """Qwen host primary; faster-whisper when the host errors or returns empty."""

    def __init__(self, host_adapter, fallback_adapter):
        self._host = host_adapter
        self._fallback = fallback_adapter
        self._id = getattr(host_adapter, "_id", "qwen3-asr-host") + "+fallback"

    def generate(self, path, verbose=False, task="transcribe", language="ru",
                 **kwargs):
        r = self._host.generate(path, verbose=verbose, task=task,
                                language=language, **kwargs)
        if (getattr(r, "text", "") or "").strip():
            return r
        vad_speech = vad_speech_seconds(path)
        energy = mean_audio_energy(path)
        if vad_speech is not None and vad_speech < 0.15 and energy < _STT_HOST_MIN_ENERGY:
            return r
        print("[stt-host] host empty/error -> whisper fallback", flush=True)
        try:
            return self._fallback.generate(path, verbose=verbose, task=task,
                                           language=language, **kwargs)
        except Exception as e:  # noqa: BLE001
            print("[stt-host] fallback error: %s" % e, flush=True)
            return r


class FasterWhisperAdapter:
    """Duck-typed like mlx_audio STT: exposes `.generate(path, ...).text`.

    CTranslate2 runs whisper-small int8 on CPU ~3-4x faster than the
    transformers pipeline. Segments carry no_speech_prob/compression_ratio/
    avg_logprob like the MLX path, so STT confidence keeps working.
    """

    def __init__(self, model_id):
        from faster_whisper import WhisperModel

        # Accept both "small" and HF ids like "openai/whisper-small".
        size = (model_id or "small").rsplit("/", 1)[-1]
        size = size.replace("whisper-", "") or "small"
        if size not in ("tiny", "base", "small", "medium", "large",
                        "large-v1", "large-v2", "large-v3", "turbo",
                        "large-v3-turbo"):
            size = "small"
        self._model = WhisperModel(
            size, device="cpu",
            # NOTE: int8 is ~2x SLOWER than fp32 on ARM (Apple Silicon VM,
            # no int8 acceleration in Docker) — fp32 is the right default.
            compute_type=os.environ.get("MOSS_STT_COMPUTE", "float32"),
            # CONCURRENCY: 3 threads/transcribe beats 10 — with several
            # requests in flight, 10-thread jobs fight over cores
            # (measured: 1.4 -> 2.3 phrases/sec aggregate).
            cpu_threads=int(os.environ.get("MOSS_STT_THREADS", "3")))
        self._id = model_id

    def generate(self, path, verbose=False, task="transcribe", language="ru",
                 **kwargs):
        class _R:
            text = ""
            segments = ()
            speech_s = 0.0

        # NOISE GATE pass 1: authoritative Silero VAD on the file. Pure
        # noise/TV/music is rejected HERE without running whisper at all
        # (fast + no hallucinations possible).
        vad_speech = vad_speech_seconds(path)
        if vad_speech is not None and vad_speech < 0.15:
            r = _R()
            return r

        segs = []
        parts = []
        speech_s = 0.0
        raw_segments, _info = self._model.transcribe(
            path, language=language or None, task=task, vad_filter=True,
            # ACCURACY (STEP 4, STREAMING STT): a beam 1 greedy decode makes
            # whisper-tiny mishear common phrases ("здравствуйте" -> "сам
            # оттвыж") on real phone audio. Beam 5 is the measured sweet spot
            # for RTF on this stack and is now tunable via MOSS_STT_BEAM.
            beam_size=int(os.environ.get("MOSS_STT_BEAM", "5")),
            # temperature 0.0 + no retry ladder stays: retries cost up to 5
            # passes on noisy audio and the noise gate already rejects pure
            # silence/TV before we get here. accuracy comes from the beam.
            temperature=0.0,
            condition_on_previous_text=False,  # no cross-segment hallucination
        )
        for s in raw_segments:
            segs.append({
                "no_speech_prob": getattr(s, "no_speech_prob", 0.0),
                "compression_ratio": getattr(s, "compression_ratio", 0.0),
                "avg_logprob": getattr(s, "avg_logprob", -1.0),
            })
            speech_s += max(0.0, float(getattr(s, "end", 0.0)) -
                            float(getattr(s, "start", 0.0)))
            parts.append(s.text)
        r = _R()
        r.text = " ".join(parts).strip()
        r.segments = segs
        # Silero VAD is the authority on speech duration (whisper segment
        # timing is unreliable on short confirmations like «да»).
        r.speech_s = vad_speech
        return r


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
        # max_new_tokens caps hallucination loops (repeated "аааа..." can
        # otherwise spin the CPU decoder for minutes); no_repeat_ngram_size
        # breaks 3-gram repetition loops outright.
        out = self._pipe(
            self._read(path),
            generate_kwargs={
                "task": task,
                "language": language if language else None,
                "max_new_tokens": 128,
                "no_repeat_ngram_size": 3,
            },
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
