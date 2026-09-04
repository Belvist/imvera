"""Cloud provider adapters (Architecture plan, Stage 1 + Stage 5).

The agent layer programs against the duck-API of STTEngine / LLMClient /
TTSClient. These adapters give the SAME surface to the cloud providers in
moss_providers, so a vendor swap is an env change, not a code change:
  MOSS_STT_PROVIDER=openai      (needs OPENAI_API_KEY)
  MOSS_LLM_PROVIDER=openai      (needs OPENAI_API_KEY)
  MOSS_TTS_PROVIDER=elevenlabs  (needs ELEVENLABS_API_KEY + voice id)
Missing key / missing config -> loud log + automatic local fallback.
"""

import base64
import io
import os
import wave

from adapters.stt import STTResult, audio_energy, confidence_from_result
from conversation_system.turn._cleaners import clean_transcript


class LocalOnlyViolation(RuntimeError):
    """Raised when MOSS_LOCAL_ONLY=1 and a remote cloud provider is configured."""


def _is_localhost_url(url: str) -> bool:
    u = (url or "").strip().lower()
    if not u:
        return False
    return any(
        h in u
        for h in (
            "127.0.0.1",
            "localhost",
            "host.docker.internal",
            "::1",
        )
    )


def enforce_local_only() -> None:
    """Fail-fast when MOSS_LOCAL_ONLY=1 and external cloud APIs are selected."""
    raw = os.environ.get("MOSS_LOCAL_ONLY", "").strip().lower()
    if raw not in ("1", "true", "yes", "on"):
        return
    violations: list[str] = []
    stt = os.environ.get("MOSS_STT_PROVIDER", "local").lower()
    tts = os.environ.get("MOSS_TTS_PROVIDER", "local").lower()
    llm = os.environ.get("MOSS_LLM_PROVIDER", "local").lower()
    if stt in ("openai", "deepgram"):
        violations.append(f"MOSS_STT_PROVIDER={stt}")
    if tts in ("elevenlabs", "openai"):
        violations.append(f"MOSS_TTS_PROVIDER={tts}")
    if llm == "openai":
        base = (
            os.environ.get("MOSS_LLM_BASE_URL")
            or os.environ.get("OPENAI_BASE_URL")
            or os.environ.get("MOSS_LLM_URL")
            or ""
        )
        if not _is_localhost_url(base):
            violations.append(
                "MOSS_LLM_PROVIDER=openai without localhost base URL"
            )
    if violations:
        msg = (
            "MOSS_LOCAL_ONLY=1 forbids external cloud providers: "
            + ", ".join(violations)
        )
        raise LocalOnlyViolation(msg)


class LocalProviderFactory:
    """Force local STT/LLM/TTS when MOSS_LOCAL_ONLY=1 (no cloud fallback)."""

    @staticmethod
    def wrap_stt(local_engine):
        enforce_local_only()
        return local_engine

    @staticmethod
    def wrap_llm(local_client):
        enforce_local_only()
        return local_client

    @staticmethod
    def wrap_tts(local_client):
        enforce_local_only()
        return local_client


def _maybe_cloud_stt(local_engine):
    """Return a cloud STT provider when MOSS_STT_PROVIDER is set
    to a non-local backend (openai, nemotron)."""
    from core.build_info import is_local_only
    if is_local_only():
        return LocalProviderFactory.wrap_stt(local_engine)
    want = os.environ.get("MOSS_STT_PROVIDER", "local").lower()
    if want == "openai":
        from moss_providers import OpenAISTTProvider
        p = OpenAISTTProvider()
        if not p.ready():
            print("[call-agent] MOSS_STT_PROVIDER=openai but "
                  "OPENAI_API_KEY is missing — using local STT",
                  flush=True)
            return local_engine
        print("[call-agent] STT provider: openai (whisper API)",
              flush=True)
        return CloudSTTAdapter(p)
    if want == "nemotron":
        from moss_providers import NemotronSTTProvider
        p = NemotronSTTProvider()
        if not p.ready():
            print("[call-agent] MOSS_STT_PROVIDER=nemotron but "
                  "host not ready — using local STT", flush=True)
            return local_engine
        print("[call-agent] STT provider: nemotron "
              "(streaming ASR)", flush=True)
        return CloudSTTAdapter(p)
    return local_engine


def _maybe_cloud_llm(local_client):
    """Return the cloud LLM provider when MOSS_LLM_PROVIDER=openai.

    Honest fallback (2026-08-30): cloud is primary (DeepSeek понимает
    лучше Qwen3-4B), но пустой content / 429 / таймаут честно падает в
    локальный llama.cpp, а не в NullLLM-заглушку. Заглушка была продуктом
    29.08 «локальная плохая», но для прототипа «слышит→понимает» фолбэк
    честнее немоты. Локальный клиент возвращается только когда провайдер
    не openai (чистый оффлайн).
    """
    from core.build_info import is_local_only
    if is_local_only():
        return LocalProviderFactory.wrap_llm(local_client)
    if os.environ.get("MOSS_LLM_PROVIDER", "local").lower() != "openai":
        return local_client
    from moss_providers import OpenAILLMProvider
    p = OpenAILLMProvider()
    if not p.ready():
        print("[call-agent] MOSS_LLM_PROVIDER=openai but OPENAI_API_KEY is "
              "missing — falling back to local LLM (was NullLLM)", flush=True)
        return local_client
    print("[call-agent] LLM provider: openai (fallback local)", flush=True)
    return CloudLLMWithFallback(p, local_client)


class NullLLM:
    """A deliberately empty LLM (product decision 2026-08-29): no local
    model, no cloud — used so the dialogue layer NEVER answers with the
    local model when the cloud is unavailable. Chat returns None / empty
    stream, so the canned `fallback` phrase speaks instead."""

    def ready(self):
        return False

    def chat(self, messages, max_tokens=100, temp=0.65, timeout=60):
        return None

    def chat_stream(self, messages, max_tokens=100, temp=0.65, timeout=60):
        return
        yield  # pragma: no cover — make this a generator with no deltas


def _maybe_cloud_tts(local_client):
    """Return a cloud TTS provider when MOSS_TTS_PROVIDER is set
    to a non-local backend (elevenlabs, qwen3)."""
    from core.build_info import is_local_only
    if is_local_only():
        return LocalProviderFactory.wrap_tts(local_client)
    want = os.environ.get("MOSS_TTS_PROVIDER", "local").lower()
    if want == "elevenlabs":
        from moss_providers import ElevenLabsTTSProvider
        p = ElevenLabsTTSProvider()
        if not p.ready():
            print("[call-agent] MOSS_TTS_PROVIDER=elevenlabs but "
                  "ELEVENLABS_API_KEY/MOSS_TTS_ELEVEN_VOICE missing — "
                  "using local MOSS TTS", flush=True)
            return local_client
        print("[call-agent] TTS provider: elevenlabs", flush=True)
        return CloudTTSAdapter(p)
    if want == "qwen3":
        from moss_providers import Qwen3TTSProvider
        p = Qwen3TTSProvider()
        if not p.ready():
            print("[call-agent] MOSS_TTS_PROVIDER=qwen3 but "
                  "host not ready — using local TTS", flush=True)
            return local_client
        print("[call-agent] TTS provider: qwen3 "
              "(Qwen3-TTS 0.6B Base)", flush=True)
        return CloudTTSAdapter(p)
    return local_client


class CloudSTTAdapter:
    """STTProvider -> STTEngine duck-API (``transcribe(wav_path)``)."""

    def __init__(self, provider):
        self.provider = provider

    def transcribe(self, wav_path):
        try:
            with open(wav_path, "rb") as f:
                wav = f.read()
            return self.provider.transcribe(wav)
        except Exception as e:  # noqa: BLE001
            print(f"[call-agent] cloud STT error: {e}", flush=True)
            return None

    def transcribe_clean(self, wav_path):
        return clean_transcript(self.transcribe(wav_path))

    def transcribe_with_confidence(self, wav_path):
        """Phone path contract: same surface as STTEngine."""
        raw = self.transcribe(wav_path)
        text = clean_transcript(raw) if raw else None
        if not text:
            return STTResult(None, None)
        result = type("R", (), {"text": text, "segments": (), "speech_s": 0.0})()
        return STTResult(text, confidence_from_result(wav_path, result))

    def ready(self):
        try:
            return self.provider.ready()
        except Exception:  # noqa: BLE001
            return False


class CloudLLMAdapter:
    """LLMProvider -> LLMClient duck-API (``chat(messages, ...)``)."""

    def __init__(self, provider):
        self.provider = provider

    def ready(self):
        try:
            return self.provider.ready()
        except Exception:  # noqa: BLE001
            return False

    def chat(self, messages, max_tokens=100, temp=0.65, timeout=15):
        try:
            return self.provider.chat(messages, max_tokens=max_tokens,
                                      temp=temp, timeout=min(timeout, 30))
        except Exception as e:  # noqa: BLE001
            print(f"[call-agent] cloud LLM error: {e}", flush=True)
            return None

    def chat_stream(self, messages, max_tokens=100, temp=0.65, timeout=15):
        """Yield text deltas from the cloud provider (OpenAI-compatible SSE).
        Never raises: on failure the dialogue layer falls back to scripted
        phrases via the canned `fallback`."""
        try:
            yield from self.provider.chat_stream(
                messages, max_tokens=max_tokens, temp=temp,
                timeout=min(timeout, 30))
        except Exception as e:  # noqa: BLE001
            print(f"[call-agent] cloud LLM stream error: {e}", flush=True)
            return


class CloudLLMWithFallback:
    """Cloud primary + local fallback (honest, no stub)."""

    def __init__(self, provider, local_client):
        self.provider = provider
        self.local = local_client
        self._cloud = CloudLLMAdapter(provider)

    def ready(self):
        try:
            if self.provider.ready():
                return True
        except Exception:
            pass
        try:
            return bool(getattr(self.local, "ready", lambda: False)())
        except Exception:
            return False

    def chat(self, messages, max_tokens=100, temp=0.65, timeout=15):
        try:
            r = self.provider.chat(messages, max_tokens=max_tokens,
                                   temp=temp, timeout=min(timeout, 30))
            if r and r.strip():
                return r
            print("[call-agent] cloud LLM empty → fallback local", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[call-agent] cloud LLM error → fallback local: {e}",
                  flush=True)
        # honest fallback — not NullLLM
        try:
            return self.local.chat(messages, max_tokens=max_tokens,
                                   temp=temp, timeout=timeout)
        except Exception as e:  # noqa: BLE001
            print(f"[call-agent] local LLM fallback error: {e}", flush=True)
            return None

    def chat_stream(self, messages, max_tokens=100, temp=0.65, timeout=15):
        # try cloud first; if it yields nothing, fallback
        got = False
        try:
            for d in self.provider.chat_stream(
                    messages, max_tokens=max_tokens, temp=temp,
                    timeout=min(timeout, 30)):
                got = True
                yield d
            if got:
                return
            print("[call-agent] cloud LLM stream empty → fallback local",
                  flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[call-agent] cloud LLM stream error → fallback: {e}",
                  flush=True)
            if got:
                # PARTIAL-STREAM GUARD: deltas may already be playing over
                # TTS. Starting a fresh local answer now would make Vera say
                # two overlapping/duplicated replies.
                return
        # fallback to local stream
        try:
            yield from self.local.chat_stream(
                messages, max_tokens=max_tokens, temp=temp, timeout=timeout)
        except Exception as e:  # noqa: BLE001
            print(f"[call-agent] local LLM stream fallback error: {e}",
                  flush=True)
            return


class CloudTTSAdapter:
    """TTSProvider -> TTSClient duck-API (generate/stream/cancel)."""

    # ElevenLabs pcm_44100 delivers raw 16-bit mono PCM; wrap it in a WAV so
    # wav_to_pcm / save_wav downstream keep working unchanged.
    PCM_RATE = 44100

    def __init__(self, provider):
        self.provider = provider

    def ready(self):
        try:
            return bool(self.provider.ready())
        except Exception:  # noqa: BLE001
            return False

    def generate(self, text):
        try:
            return self._ensure_wav(self.provider.synthesize(text))
        except Exception as e:  # noqa: BLE001
            print(f"[call-agent] cloud TTS error: {e}", flush=True)
            return None

    def stream(self, text, cancel_event=None, stream_id=None):
        try:
            for frame in self.provider.stream(
                    text, cancel_event=cancel_event, stream_id=stream_id):
                if cancel_event is not None and cancel_event.is_set():
                    return
                if frame.get("wav_b64"):
                    wav = self._ensure_wav(base64.b64decode(frame["wav_b64"]))
                    if wav:
                        frame = {**frame,
                                 "wav_b64": base64.b64encode(wav).decode("ascii")}
                yield frame
        except Exception as e:  # noqa: BLE001
            print(f"[call-agent] cloud TTS stream error: {e}", flush=True)
            yield {"done": True}

    def cancel_stream_by_id(self, stream_id):
        # full-clip providers have no server-side generation to abort
        pass

    @classmethod
    def _ensure_wav(cls, raw):
        if not raw:
            return None
        if raw[:4] == b"RIFF":
            return raw
        buf = io.BytesIO()
        try:
            with wave.open(buf, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(cls.PCM_RATE)
                w.writeframes(raw)
        except Exception:  # noqa: BLE001
            return None
        return buf.getvalue()