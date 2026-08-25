#!/usr/bin/env python3
"""MossVoice provider contracts (Architecture plan, Stage 1).

Single module that defines the vendor-agnostic interfaces the agent layer
programs against:

    STTProvider   audio -> text          (local MLX Whisper | cloud STT)
    LLMProvider   messages -> text       (local mlx_llm | cloud LLM API)
    TTSProvider   text -> wav frames     (local MOSS-TTS-Nano | cloud TTS API)
    AudioTransport PCM frames in/out     (WebSocket/Telegram | LiveKit later)
    SessionStore  dialogue state         (in-memory | Redis later)
    ToolProvider  checked side effects   (CRM/notify with timeout+idempotency)

The dialogue engine must import ONLY these contracts. Concrete backends are
picked at process start by ``build_*()`` factories from environment variables,
so swapping local<->cloud never touches agent code:

    MOSS_STT_PROVIDER = local|openai       (default: local)
    MOSS_LLM_PROVIDER = local|openai       (default: local)
    MOSS_TTS_PROVIDER = local|elevenlabs   (default: local)
    OPENAI_API_KEY / ELEVENLABS_API_KEY    (required for the cloud backends;
                                            when missing the factory logs and
                                            falls back to local automatically)

Design rules honoured here (Stage 9):
  * every network call has a timeout;
  * one safe retry on idempotent requests;
  * a circuit breaker trips after N consecutive failures;
  * failures raise ProviderError — the CALLER decides the fallback phrase,
    this module never invents dialogue content.

Only the Python standard library is required (urllib); the local adapters
delegate to the already-loaded daemons/engines and add no new dependency.
"""

import abc
import base64
import json
import os
import threading
import time
import urllib.request

__all__ = [
    "ProviderError",
    "ProviderCircuitOpen",
    "STTProvider", "LLMProvider", "TTSProvider",
    "AudioTransport", "SessionStore", "ToolProvider",
    "LocalSTTProvider", "LocalLLMProvider", "LocalTTSProvider",
    "OpenAISTTProvider", "OpenAILLMProvider", "ElevenLabsTTSProvider",
    "MemorySessionStore", "RedisSessionStore",
    "build_stt", "build_llm", "build_tts", "build_session_store",
    "session_doc",
]


# ----------------------------------------------------------------------------
# Errors
# ----------------------------------------------------------------------------
class ProviderError(Exception):
    """Any provider failure (timeout, HTTP error, bad response)."""


class ProviderCircuitOpen(ProviderError):
    """Circuit breaker is open — the provider is considered down for now."""


# ----------------------------------------------------------------------------
# Contracts
# ----------------------------------------------------------------------------
class STTProvider(abc.ABC):
    """Speech -> text. ``transcribe`` takes raw WAV bytes (16-bit mono, any
    rate) and returns the transcript or None when nothing usable was heard."""

    name = "stt"

    @abc.abstractmethod
    def ready(self):
        """True when the backend can accept work without a long cold load."""

    @abc.abstractmethod
    def transcribe(self, wav_bytes, language="ru"):
        """Blocking transcription of one utterance. Returns str or None."""


class LLMProvider(abc.ABC):
    """Chat-style text generation. Providers must stay stateless: the full
    message history is passed in on every call (Stage 4: dialogue state lives
    in the DialogueEngine, never inside the model client).

    ``chat_stream`` yields text DELTAS as they are generated (Stage 5 token
    streaming): the caller sends each completed sentence to TTS immediately,
    so the agent starts speaking while the reply is still being generated.
    The default implementation falls back to a single-chunk ``chat`` so every
    provider satisfies the contract even without native streaming."""

    name = "llm"

    @abc.abstractmethod
    def ready(self):
        """True when the backend can answer without a long cold load."""

    @abc.abstractmethod
    def chat(self, messages, max_tokens=120, temp=0.65, timeout=30):
        """messages: [{"role": system|user|assistant, "content": str}].
        Returns the reply text or None on failure."""

    def chat_stream(self, messages, max_tokens=120, temp=0.65, timeout=30):
        """Yield text deltas; default: one delta with the full reply."""
        text = self.chat(messages, max_tokens=max_tokens, temp=temp,
                         timeout=timeout)
        if text:
            yield text


class TTSProvider(abc.ABC):
    """Text -> audio frames. ``synthesize`` returns complete WAV bytes for
    canned/cached phrases; ``stream`` yields dicts
    {"i": n, "wav_b64": ..., "done": bool} and MUST honour ``cancel_event``
    so a barge-in stops real model work (not just the socket read)."""

    name = "tts"

    @abc.abstractmethod
    def ready(self):
        """True when the backend can accept work."""

    @abc.abstractmethod
    def synthesize(self, text):
        """Blocking: returns WAV bytes or None."""

    def stream(self, text, cancel_event=None, stream_id=None):
        """Yield frame dicts; default: one frame with the full synthesis."""
        wav = self.synthesize(text)
        if not wav:
            yield {"done": True}
            return
        yield {"i": 0, "wav_b64": base64.b64encode(wav).decode("ascii"),
               "done": False}
        yield {"done": True}


class AudioTransport(abc.ABC):
    """Bidirectional 20 ms PCM transport (Stage 2). The production path will
    implement this over LiveKit; the current Telegram bridge implements it
    over WebSocket frames. The agent never knows which one is attached."""

    name = "transport"

    @abc.abstractmethod
    def frames_in(self, call_id):
        """Iterate (bytes_pcm16mono, seq, ts_ms, rate) frames from the caller."""

    @abc.abstractmethod
    def send_audio(self, call_id, pcm16, seq, rate):
        """Push one agent audio frame to the caller. Returns False when the
        transport dropped (caller should stop producing)."""

    @abc.abstractmethod
    def flush(self, call_id):
        """Barge-in: discard every queued/playing agent frame immediately."""


class SessionStore(abc.ABC):
    """Dialogue state keyed by call_id (Stage 6). In-memory now, Redis with
    TTL later — the schema is already Redis-friendly (small JSON document,
    never audio blobs)."""

    @abc.abstractmethod
    def get(self, call_id):
        """Return the state dict or None."""

    @abc.abstractmethod
    def put(self, call_id, state, ttl_seconds=None):
        """Store/replace the state document; ttl None = session lifetime."""

    @abc.abstractmethod
    def delete(self, call_id):
        """Drop the session (call finished/expired)."""


class ToolProvider(abc.ABC):
    """Checked side effects (CRM writes, notifications, emergency routing).
    Implementations must enforce a timeout and dedupe via idempotency_key
    (Stage 4). The LLM is allowed to SELECT a tool name from an allow-list
    only; it never executes anything directly."""

    @abc.abstractmethod
    def tool_names(self):
        """Allow-list of tool names the dialogue engine may offer the LLM."""

    @abc.abstractmethod
    def call_tool(self, name, args, idempotency_key, timeout=10):
        """Execute one tool. Raises ProviderError on failure/timeout."""


# ----------------------------------------------------------------------------
# Circuit breaker shared by the network adapters (Stage 9)
# ----------------------------------------------------------------------------
class _Breaker:
    """Trip after ``threshold`` consecutive failures; half-open after
    ``cooldown`` seconds lets one probe through."""

    def __init__(self, threshold=3, cooldown=60.0):
        self.threshold = threshold
        self.cooldown = cooldown
        self.fails = 0
        self.open_until = 0.0

    def guard(self):
        if self.fails >= self.threshold and time.time() < self.open_until:
            raise ProviderCircuitOpen(
                f"circuit open ({self.fails} consecutive failures)")

    def failed(self):
        self.fails += 1
        if self.fails >= self.threshold:
            self.open_until = time.time() + self.cooldown

    def succeeded(self):
        self.fails = 0
        self.open_until = 0.0


def _http_json(method, url, body=None, headers=None, timeout=30):
    """Small stdlib JSON client with explicit timeout. Raises ProviderError."""
    data = json.dumps(body).encode() if body is not None else None
    hdrs = {"Content-Type": "application/json"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        raise ProviderError(f"{method} {url}: {e}") from e
    try:
        return json.loads(raw)
    except ValueError as e:
        raise ProviderError(f"bad JSON from {url}: {e}") from e


def _split_host_port(url):
    """"http://host:port/path" -> (host, port) for http.client."""
    from urllib.parse import urlsplit

    parts = urlsplit(url)
    host = parts.hostname or "127.0.0.1"
    port = parts.port or (443 if parts.scheme == "https" else 80)
    return host, port


# ----------------------------------------------------------------------------
# Local backends (delegate to the already-running MossVoice daemons)
# ----------------------------------------------------------------------------
class LocalSTTProvider(STTProvider):
    """Whisper via the voice daemon's /transcribe (9600)."""

    name = "stt-local"

    def __init__(self, host=None, port=None):
        self.host = host or os.environ.get("MOSS_TTS_HOST", "127.0.0.1")
        self.port = int(port or os.environ.get("MOSS_TTS_PORT", "9600"))
        self._breaker = _Breaker()

    def ready(self):
        try:
            obj = _http_json("GET", f"http://{self.host}:{self.port}/health",
                             timeout=3)
            return bool(obj.get("ok"))
        except ProviderError:
            return False

    def transcribe(self, wav_bytes, language="ru"):
        self._breaker.guard()
        b64 = base64.b64encode(wav_bytes).decode("ascii")
        try:
            # two attempts: a transient daemon hiccup must not lose the turn
            for attempt in (0, 1):
                try:
                    obj = _http_json(
                        "POST", f"http://{self.host}:{self.port}/transcribe",
                        body={"audio_b64": b64, "language": language},
                        timeout=120)
                    self._breaker.succeeded()
                    text = (obj.get("text") or "").strip()
                    return text or None
                except ProviderError:
                    if attempt == 0:
                        continue
                    raise
        except ProviderError as e:
            self._breaker.failed()
            raise e
        return None


class LocalLLMProvider(LLMProvider):
    """Qwen via the answers daemon's /chat (9500). Falls back to the
    in-process mlx_lm path only inside the call_agent daemon itself."""

    name = "llm-local"

    def __init__(self, url=None):
        self.url = (url or os.environ.get(
            "MOSS_LLM_URL", "http://127.0.0.1:9500")).rstrip("/")
        self._breaker = _Breaker()

    def ready(self):
        try:
            obj = _http_json("GET", self.url + "/health", timeout=3)
            return bool(obj.get("ready"))
        except ProviderError:
            return False

    def chat(self, messages, max_tokens=120, temp=0.65, timeout=30):
        self._breaker.guard()
        try:
            obj = _http_json("POST", self.url + "/chat",
                             body={"messages": messages,
                                   "max_tokens": max_tokens, "temp": temp},
                             timeout=timeout)
            if obj.get("ok") and obj.get("text"):
                self._breaker.succeeded()
                return obj["text"]
            raise ProviderError("llm daemon returned no text")
        except ProviderError as e:
            self._breaker.failed()
            raise e

    def chat_stream(self, messages, max_tokens=120, temp=0.65, timeout=30):
        """Token streaming via llm-server /chat_stream (REALTIME FIX).

        Reads length-prefixed JSON frames and yields the ``delta`` of each;
        the final frame carries the full text. A daemon without the endpoint
        (old image) raises ProviderError so the caller falls back to chat().
        """
        import http.client as _http_client

        self._breaker.guard()
        body = json.dumps({"messages": messages, "max_tokens": max_tokens,
                           "temp": temp}).encode()
        try:
            host, port = _split_host_port(self.url)
            conn = _http_client.HTTPConnection(host, port, timeout=timeout)
            try:
                conn.request("POST", "/chat_stream", body=body,
                             headers={"Content-Type": "application/json"})
                resp = conn.getresponse()
                if resp.status != 200:
                    raise ProviderError(
                        f"llm /chat_stream HTTP {resp.status}")
                buf = b""
                while True:
                    chunk = resp.read1(65536)
                    if not chunk:
                        break
                    buf += chunk
                    while len(buf) >= 4:
                        n = int.from_bytes(buf[:4], "big")
                        if len(buf) < 4 + n:
                            break
                        frame = json.loads(buf[4:4 + n].decode("utf-8"))
                        buf = buf[4 + n:]
                        if frame.get("error") and not frame.get("delta"):
                            raise ProviderError(frame["error"])
                        if frame.get("delta"):
                            yield frame["delta"]
                        if frame.get("done"):
                            self._breaker.succeeded()
                            return
            finally:
                conn.close()
        except ProviderError as e:
            self._breaker.failed()
            raise e
        except Exception as e:  # noqa: BLE001
            self._breaker.failed()
            raise ProviderError(f"llm-local stream: {e}") from e


class LocalTTSProvider(TTSProvider):
    """MOSS-TTS-Nano via the voice daemon's /generate + /stream (9600)."""

    name = "tts-local"

    def __init__(self, engine=None, ref_paths=None, reference_text=""):
        if engine is not None:
            self._engine = engine
        else:
            from call_agent import TTSClient
            self._engine = TTSClient(
                ref_paths=ref_paths, reference_text=reference_text,
                port=int(os.environ.get("MOSS_TTS_PORT", "9600")),
                host=os.environ.get("MOSS_TTS_HOST", ""),
            )

    def ready(self):
        return bool(self._engine.ready())

    def synthesize(self, text):
        try:
            return self._engine.generate(text)
        except Exception as e:  # noqa: BLE001
            raise ProviderError(f"tts-local: {e}") from e

    def stream(self, text, cancel_event=None, stream_id=None):
        try:
            yield from self._engine.stream(
                text, cancel_event=cancel_event, stream_id=stream_id)
        except Exception as e:  # noqa: BLE001
            raise ProviderError(f"tts-local stream: {e}") from e


# ----------------------------------------------------------------------------
# Cloud backends (Stage 5 fast path) — enabled only when keys are present
# ----------------------------------------------------------------------------
class OpenAISTTProvider(STTProvider):
    """OpenAI /v1/audio/transcriptions (whisper-1)."""

    name = "stt-openai"
    URL = "https://api.openai.com/v1/audio/transcriptions"

    def __init__(self, api_key=None, model=None, timeout=30):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.model = model or os.environ.get("MOSS_STT_OPENAI_MODEL",
                                             "whisper-1")
        self.timeout = timeout
        self._breaker = _Breaker()

    def ready(self):
        return bool(self.api_key)

    def transcribe(self, wav_bytes, language="ru"):
        self._breaker.guard()
        if not self.api_key:
            raise ProviderError("OPENAI_API_KEY missing")
        import uuid
        boundary = uuid.uuid4().hex
        body = b"".join([
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"model\""
            f"\r\n\r\n{self.model}\r\n".encode(),
            f"--{boundary}\r\nContent-Disposition: form-data; "
            f"name=\"language\"\r\n\r\n{language}\r\n".encode(),
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
            f"filename=\"utterance.wav\"\r\nContent-Type: audio/wav\r\n\r\n"
            .encode(),
            wav_bytes, f"\r\n--{boundary}--\r\n".encode(),
        ])
        req = urllib.request.Request(
            self.URL, data=body, method="POST",
            headers={"Authorization": f"Bearer {self.api_key}",
                     "Content-Type": f"multipart/form-data; "
                                     f"boundary={boundary}"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                obj = json.loads(r.read().decode("utf-8", "replace"))
            self._breaker.succeeded()
            text = (obj.get("text") or "").strip()
            return text or None
        except Exception as e:  # noqa: BLE001
            self._breaker.failed()
            raise ProviderError(f"openai-stt: {e}") from e


class OpenAILLMProvider(LLMProvider):
    """OpenAI /v1/chat/completions."""

    name = "llm-openai"
    URL = "https://api.openai.com/v1/chat/completions"

    def __init__(self, api_key=None, model=None, timeout=30):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.model = model or os.environ.get("MOSS_LLM_OPENAI_MODEL",
                                             "gpt-4o-mini")
        # Cloud experiment (2026-08-25): any OpenAI-compatible endpoint —
        # official OpenAI or OpenRouter — via MOSS_LLM_BASE_URL.
        self.URL = os.environ.get("MOSS_LLM_BASE_URL", self.URL)
        # DeepSeek-style reasoning models on OpenRouter burn the token budget
        # on <reasoning> and return empty content under our 100-150 token
        # cap (seen live 2026-08-25). Only OpenRouter accepts this param —
        # the official OpenAI endpoint would reject it with 400.
        self._no_reasoning = "openrouter" in self.URL
        self.timeout = timeout
        self._breaker = _Breaker()

    def ready(self):
        return bool(self.api_key)

    def chat(self, messages, max_tokens=120, temp=0.65, timeout=30):
        self._breaker.guard()
        if not self.api_key:
            raise ProviderError("OPENAI_API_KEY missing")
        body = {**({"reasoning": {"enabled": False}}
                   if self._no_reasoning else {}),
                "model": self.model, "messages": messages,
                "max_tokens": max_tokens, "temperature": temp}
        obj = _http_json(
            "POST", self.URL,
            body=body,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=min(timeout, self.timeout))
        try:
            text = obj["choices"][0]["message"]["content"].strip()
            self._breaker.succeeded()
            return text or None
        except Exception as e:  # noqa: BLE001
            self._breaker.failed()
            raise ProviderError(f"openai-llm bad response: {e}") from e

    def chat_stream(self, messages, max_tokens=120, temp=0.65, timeout=30):
        """SSE (server-sent events) delta-streaming against the OpenAI API."""
        import http.client as _http_client

        self._breaker.guard()
        if not self.api_key:
            raise ProviderError("OPENAI_API_KEY missing")
        body = dict({"reasoning": {"enabled": False}}
                 if self._no_reasoning else {})
        body.update({"model": self.model, "messages": messages,
                     "max_tokens": max_tokens, "temperature": temp,
                     "stream": True})
        body = json.dumps(body).encode()
        try:
            from urllib.parse import urlsplit
            u = urlsplit(self.URL)
            conn = _http_client.HTTPSConnection(
                u.hostname or "api.openai.com", 443,
                timeout=min(timeout, self.timeout))
            try:
                conn.request("POST", u.path or "/v1/chat/completions",
                             body=body,
                             headers={"Authorization": f"Bearer {self.api_key}",
                                      "Content-Type": "application/json"})
                resp = conn.getresponse()
                if resp.status != 200:
                    detail = resp.read(512).decode("utf-8", "replace")
                    raise ProviderError(
                        f"openai stream HTTP {resp.status}: {detail[:160]}")
                pending = ""
                while True:
                    chunk = resp.read1(65536)
                    if not chunk:
                        break
                    pending += chunk.decode("utf-8", "replace")
                    while "\n" in pending:
                        line, pending = pending.split("\n", 1)
                        line = line.strip()
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            self._breaker.succeeded()
                            return
                        try:
                            evt = json.loads(data)
                        except ValueError:
                            continue
                        delta = (evt.get("choices") or [{}])[0].get("delta") or {}
                        piece = delta.get("content") or ""
                        if piece:
                            yield piece
                self._breaker.succeeded()
            finally:
                conn.close()
        except ProviderError as e:
            self._breaker.failed()
            raise e
        except Exception as e:  # noqa: BLE001
            self._breaker.failed()
            raise ProviderError(f"openai-llm stream: {e}") from e


class ElevenLabsTTSProvider(TTSProvider):
    """ElevenLabs text-to-speech (returns a full WAV; streaming endpoint can
    be added later without changing the contract)."""

    name = "tts-elevenlabs"

    def __init__(self, api_key=None, voice_id=None, model_id=None, timeout=30):
        self.api_key = api_key or os.environ.get("ELEVENLABS_API_KEY", "")
        self.voice_id = voice_id or os.environ.get("MOSS_TTS_ELEVEN_VOICE", "")
        self.model_id = model_id or os.environ.get(
            "MOSS_TTS_ELEVEN_MODEL", "eleven_multilingual_v2")
        self.timeout = timeout
        self._breaker = _Breaker()

    def ready(self):
        return bool(self.api_key and self.voice_id)

    def synthesize(self, text):
        self._breaker.guard()
        if not (self.api_key and self.voice_id):
            raise ProviderError("ELEVENLABS_API_KEY/MOSS_TTS_ELEVEN_VOICE "
                                "missing")
        url = (f"https://api.elevenlabs.io/v1/text-to-speech/"
               f"{self.voice_id}?output_format=pcm_44100")
        body = json.dumps({"text": text, "model_id": self.model_id}).encode()
        req = urllib.request.Request(
            url, data=body, method="POST",
            headers={"xi-api-key": self.api_key,
                     "Content-Type": "application/json",
                     "Accept": "audio/mpeg"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                raw = r.read()
            self._breaker.succeeded()
            return raw or None
        except Exception as e:  # noqa: BLE001
            self._breaker.failed()
            raise ProviderError(f"elevenlabs: {e}") from e


# ----------------------------------------------------------------------------
# Factories (env-selected, local fallback)
# ----------------------------------------------------------------------------
def _fallback(kind, want, err):
    print(f"[providers] {want} provider unavailable ({err}); "
          f"falling back to local {kind}", flush=True)


def build_stt(prefer=None):
    """Pick the STT backend. MOSS_STT_PROVIDER=openai requests the cloud
    path; anything else (or missing keys) uses the local daemon."""
    want = (prefer or os.environ.get("MOSS_STT_PROVIDER", "local")).lower()
    if want == "openai":
        p = OpenAISTTProvider()
        if p.ready():
            return p
        _fallback("stt", want, "no API key")
    return LocalSTTProvider()


def build_llm(prefer=None, url=None):
    want = (prefer or os.environ.get("MOSS_LLM_PROVIDER", "local")).lower()
    if want == "openai":
        p = OpenAILLMProvider()
        if p.ready():
            return p
        _fallback("llm", want, "no API key")
    return LocalLLMProvider(url=url)


def build_tts(prefer=None, refs=None, reference_text=""):
    want = (prefer or os.environ.get("MOSS_TTS_PROVIDER", "local")).lower()
    if want == "elevenlabs":
        p = ElevenLabsTTSProvider()
        if p.ready():
            return p
        _fallback("tts", want, "no API key / voice id")
    return LocalTTSProvider(ref_paths=refs, reference_text=reference_text)


# ----------------------------------------------------------------------------
# SessionStore implementations (Stage 6)
# ----------------------------------------------------------------------------
# Stage-6 document schema (kept Redis-friendly: small JSON, no audio blobs):
#   {"call_id","customer_id","dialogue_step","summary","last_intent",
#    "worker_id","updated_at"}
# Full audio never goes through the store — recordings are written in
# parallel by the recorder and (later) uploaded to S3.
SESSION_STATE_SCHEMA = {
    "call_id": str,
    "customer_id": str,
    "dialogue_step": int,
    "summary": str,
    "last_intent": str,
    "worker_id": str,
    "updated_at": float,
}


def session_doc(call_id, dialogue_step=0, summary="", last_intent="",
                worker_id="", customer_id=""):
    """Build a Stage-6 session document (schema above)."""
    return {
        "call_id": str(call_id),
        "customer_id": str(customer_id or ""),
        "dialogue_step": int(dialogue_step),
        "summary": str(summary or ""),
        "last_intent": str(last_intent or ""),
        "worker_id": str(worker_id or os.environ.get("MOSS_WORKER_ID", "")),
        "updated_at": time.time(),
    }


class MemorySessionStore(SessionStore):
    """In-process session store with TTL sweeping (default). A worker-local
    copy of the same schema Redis uses — two identical agent-workers can each
    run it until Stage 6 promotes sessions to Redis."""

    def __init__(self, default_ttl_seconds=3600):
        self.default_ttl = default_ttl_seconds
        self._data = {}
        self._lock = threading.Lock()

    def get(self, call_id):
        with self._lock:
            item = self._data.get(call_id)
            if item is None:
                return None
            state, expires = item
            if expires is not None and time.time() >= expires:
                self._data.pop(call_id, None)
                return None
            return json.loads(json.dumps(state))  # defensive copy

    def put(self, call_id, state, ttl_seconds=None):
        ttl = self.default_ttl if ttl_seconds is None else ttl_seconds
        expires = time.time() + ttl if ttl and ttl > 0 else None
        with self._lock:
            self._data[call_id] = (json.loads(json.dumps(state)), expires)
            self._sweep_locked()

    def delete(self, call_id):
        with self._lock:
            self._data.pop(call_id, None)

    def _sweep_locked(self):
        now = time.time()
        expired = [k for k, (_, exp) in self._data.items()
                   if exp is not None and now >= exp]
        for k in expired:
            self._data.pop(k, None)


class RedisSessionStore(SessionStore):
    """Redis-backed store (Stage 6): ``mossvoice:session:<call_id>`` keys with
    native TTL. Lazy-imports ``redis`` so the project runs without the package
    installed; construction raises RuntimeError when unavailable so the
    factory can fall back to MemorySessionStore."""

    KEY_PREFIX = "mossvoice:session:"

    def __init__(self, url=None, default_ttl_seconds=3600, socket_timeout=3):
        try:
            import redis as _redis
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(f"redis package not installed: {e}") from e
        self.default_ttl = default_ttl_seconds
        url = url or os.environ.get("MOSS_REDIS_URL", "redis://127.0.0.1:6379/0")
        self._client = _redis.Redis.from_url(
            url, socket_timeout=socket_timeout,
            socket_connect_timeout=socket_timeout)
        # fail fast on a dead connection so the factory can fall back
        self._client.ping()

    def _key(self, call_id):
        return self.KEY_PREFIX + str(call_id)

    def get(self, call_id):
        raw = self._client.get(self._key(call_id))
        if not raw:
            return None
        try:
            return json.loads(raw.decode("utf-8"))
        except ValueError:
            return None

    def put(self, call_id, state, ttl_seconds=None):
        ttl = self.default_ttl if ttl_seconds is None else int(ttl_seconds)
        payload = json.dumps(state, ensure_ascii=False)
        if ttl and ttl > 0:
            self._client.setex(self._key(call_id), ttl, payload)
        else:
            self._client.set(self._key(call_id), payload)

    def delete(self, call_id):
        self._client.delete(self._key(call_id))


def build_session_store(prefer=None, url=None):
    """Pick the session store. MOSS_SESSION_STORE=redis (or MOSS_REDIS_URL
    set) requests Redis. An unreachable *requested* Redis goes DEGRADED: the
    returned store is a process-local memory cache with ``degraded=True``
    (loud log + surfaced in /health) — NOT a silent fallback. Postgres stays
    the source of truth for durable state."""
    want = (prefer or os.environ.get(
        "MOSS_SESSION_STORE",
        "redis" if os.environ.get("MOSS_REDIS_URL") else "memory")).lower()
    if want == "redis":
        try:
            store = RedisSessionStore(url=url)
            store.degraded = False
            store.redis_requested = True
            print("[providers] session store: redis", flush=True)
            return store
        except Exception as e:  # noqa: BLE001
            print(f"[providers] session store: DEGRADED — Redis requested but "
                  f"unavailable ({e}); using process-local memory cache. "
                  f"Surfaced in /health; Postgres remains the truth.",
                  flush=True)
            store = MemorySessionStore(
                default_ttl_seconds=int(
                    os.environ.get("MOSS_SESSION_TTL", "3600")))
            store.degraded = True
            store.redis_requested = True
            return store
    store = MemorySessionStore(
        default_ttl_seconds=int(os.environ.get("MOSS_SESSION_TTL", "3600")))
    store.degraded = False
    store.redis_requested = False
    return store
