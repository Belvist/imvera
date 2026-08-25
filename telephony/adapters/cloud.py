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

from core.dialogue import clean_transcript


def _maybe_cloud_stt(local_engine):
    if os.environ.get("MOSS_STT_PROVIDER", "local").lower() != "openai":
        return local_engine
    from moss_providers import OpenAISTTProvider
    p = OpenAISTTProvider()
    if not p.ready():
        print("[call-agent] MOSS_STT_PROVIDER=openai but OPENAI_API_KEY is "
              "missing — using local STT", flush=True)
        return local_engine
    print("[call-agent] STT provider: openai (whisper API)", flush=True)
    return CloudSTTAdapter(p)


def _maybe_cloud_llm(local_client):
    if os.environ.get("MOSS_LLM_PROVIDER", "local").lower() != "openai":
        return local_client
    from moss_providers import OpenAILLMProvider
    p = OpenAILLMProvider()
    if not p.ready():
        print("[call-agent] MOSS_LLM_PROVIDER=openai but OPENAI_API_KEY is "
              "missing — using local LLM", flush=True)
        return local_client
    print("[call-agent] LLM provider: openai", flush=True)
    return CloudLLMAdapter(p)


def _maybe_cloud_tts(local_client):
    if os.environ.get("MOSS_TTS_PROVIDER", "local").lower() != "elevenlabs":
        return local_client
    from moss_providers import ElevenLabsTTSProvider
    p = ElevenLabsTTSProvider()
    if not p.ready():
        print("[call-agent] MOSS_TTS_PROVIDER=elevenlabs but "
              "ELEVENLABS_API_KEY/MOSS_TTS_ELEVEN_VOICE missing — using "
              "local MOSS TTS", flush=True)
        return local_client
    print("[call-agent] TTS provider: elevenlabs", flush=True)
    return CloudTTSAdapter(p)


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

    def chat(self, messages, max_tokens=100, temp=0.65, timeout=60):
        try:
            return self.provider.chat(messages, max_tokens=max_tokens,
                                      temp=temp, timeout=min(timeout, 30))
        except Exception as e:  # noqa: BLE001
            print(f"[call-agent] cloud LLM error: {e}", flush=True)
            return None

    def chat_stream(self, messages, max_tokens=100, temp=0.65, timeout=60):
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