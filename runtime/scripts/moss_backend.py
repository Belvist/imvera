#!/usr/bin/env python3
"""MOSS-TTS-Nano ONNX CPU backend.

Lightweight multilingual zero-shot voice-clone TTS (OpenMOSS / MOSI.AI,
apache-2.0): ~0.1B parameters, runs on CPU in a single core, native 48 kHz
output, streaming decode. Weights: OpenMOSS-Team/MOSS-TTS-Nano-100M-ONNX +
OpenMOSS-Team/MOSS-Audio-Tokenizer-Nano-ONNX (downloaded automatically into
``runtime/models`` on first run, or served from MOSS_TTS_MODEL_DIR).

With a reference audio the model clones that voice; without one it falls
back to a built-in voice (MOSS_TTS_VOICE, default ``Ava``).

The model object is duck-typed to the interface ``tts_common`` expects:
``.sample_rate``, ``.build_prompt_cache``, ``.generate_with_prompt_cache``,
``._generate_with_prompt_cache`` (streaming generator).
"""
import os
import threading

import numpy as np

DEFAULT_MODEL_ID = "moss-tts-nano"
DEFAULT_VOICE = os.environ.get("MOSS_TTS_VOICE", "Ava")
_THREAD_COUNT = int(os.environ.get("MOSS_TTS_THREADS", str(os.cpu_count() or 4)))
_MAX_VOICE_CLONE_TEXT_TOKENS = 75

_runtime = None
_runtime_lock = threading.Lock()


def _default_model_dir():
    explicit = os.environ.get("MOSS_TTS_MODEL_DIR", "").strip()
    if explicit:
        return explicit
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(os.path.dirname(here), "models")


def _get_runtime():
    global _runtime
    with _runtime_lock:
        if _runtime is None:
            from moss_runtime.onnx_tts_runtime import (
                OnnxTtsRuntime,
                _download_default_browser_onnx_assets,
                _find_manifest_path,
            )
            from pathlib import Path

            model_dir = Path(_default_model_dir())
            if _find_manifest_path(model_dir) is None:
                # Docker / fresh installs: pull the ONNX weights into the
                # configured directory (usually a persistent volume) on first
                # run. Local checkouts ship the weights in runtime/models.
                _download_default_browser_onnx_assets(model_dir)
            _runtime = OnnxTtsRuntime(
                model_dir=model_dir,
                thread_count=_THREAD_COUNT,
            )
    return _runtime


class MossTTSModel:
    """Duck-typed replacement for the legacy Qwen3 TTS model handle."""

    _is_qwen3 = False
    _is_moss = True

    def __init__(self):
        self._rt = _get_runtime()
        self.sample_rate = int(self._rt.codec_meta["codec_config"]["sample_rate"])
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ #
    # Cache: reference audio -> prompt audio codes (clone) or built-in voice.
    # ------------------------------------------------------------------ #
    def build_prompt_cache(self, reference_wav_path=None, ref_text=None):
        if reference_wav_path and os.path.exists(reference_wav_path):
            with self._lock:
                codes = self._rt.encode_reference_audio(reference_wav_path)
            return {"codes": codes, "ref": str(reference_wav_path)}
        return {"codes": None, "ref": None}

    def _prompt_codes(self, prompt_cache):
        if prompt_cache and prompt_cache.get("codes") is not None:
            return prompt_cache["codes"]
        voice = DEFAULT_VOICE
        if prompt_cache and prompt_cache.get("voice"):
            voice = prompt_cache["voice"]
        return self._rt.resolve_prompt_audio_codes(voice=voice, prompt_audio_path=None)

    def _chunks(self, text):
        prepared = self._rt.prepare_synthesis_text(
            text=text,
            voice="",
            enable_wetext=False,
            enable_normalize_tts_text=True,
        )
        return self._rt.split_voice_clone_text(
            str(prepared["text"]), max_tokens=_MAX_VOICE_CLONE_TEXT_TOKENS
        )

    def generate_with_prompt_cache(
        self,
        target_text,
        prompt_cache=None,
        min_len=None,
        max_len=None,
        inference_timesteps=None,
        cfg_value=None,
    ):
        wav = None
        parts = []
        codes = self._prompt_codes(prompt_cache)
        chunks = self._chunks(target_text) if (target_text or "").strip() else []
        for chunk in chunks:
            with self._lock:
                res = self._rt.synthesize_single_chunk(
                    text=chunk, prompt_audio_codes=codes, streaming=False
                )
            parts.append(res["waveform"])
        if parts:
            wav = np.concatenate(parts, axis=0)
        else:
            wav = np.zeros((0, 2), dtype=np.float32)
        # stereo -> mono for the server's mono WAV writers
        if wav.ndim == 2:
            wav = wav.mean(axis=1)
        return wav.astype(np.float32, copy=False), None, None

    def _generate_with_prompt_cache(
        self,
        target_text,
        prompt_cache=None,
        min_len=None,
        max_len=None,
        inference_timesteps=None,
        cfg_value=None,
        streaming=False,
        streaming_prefix_len=None,
    ):
        # Sentence/chunk-level streaming: each chunk decodes fully and is
        # yielded as its own frame, so first audio arrives after one chunk.
        codes = self._prompt_codes(prompt_cache)
        chunks = self._chunks(target_text) if (target_text or "").strip() else []
        for idx, chunk in enumerate(chunks):
            with self._lock:
                res = self._rt.synthesize_single_chunk(
                    text=chunk, prompt_audio_codes=codes, streaming=False
                )
            wav = res["waveform"]
            if wav.ndim == 2:
                wav = wav.mean(axis=1)
            wav = wav.astype(np.float32, copy=False)
            if wav.size:
                yield wav
            if idx < len(chunks) - 1:
                pause = self._rt.estimate_voice_clone_inter_chunk_pause_seconds(chunk)
                pause_samples = max(0, int(round(self.sample_rate * pause)))
                if pause_samples:
                    yield np.zeros(pause_samples, dtype=np.float32)


def load_tts(model_id=DEFAULT_MODEL_ID, device="auto", optimize=False):
    """Load MOSS-TTS-Nano and return a backend object exposing ``.tts_model``."""
    model = MossTTSModel()

    class _Backend:
        tts_model = model

    return _Backend()
