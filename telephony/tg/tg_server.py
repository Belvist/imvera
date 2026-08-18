#!/usr/bin/env python3
"""MossVoice Telegram call server — full-duplex (P0-REALTIME-CORE).

Flow:
  Browser (Telegram WebApp)  --WS-->  tg_server  --/calls/{call_id}/turn_stream-->  call_agent
   (microphone PCM 16k)      <--wav-- tg_server  <------------ (STT+agent+TTS)

Full-duplex design:
  * RX is ALWAYS on — the microphone never stops during agent speech.
  * VAD continuously segments speech; a speech onset detected while the TX
    pipeline is active is a BARGE-IN.
  * TX is a separate pipeline with a cancel token, an auditable queue and a
    flush() — on barge-in we: cancel TTS generation (/stream-cancel),
    clear pending TX audio, send {"type":"flush"} so the client drops any
    queued playback instantly, and never lose the head of the new user turn.

Protocol (JSON over WebSocket):
  client -> server: {"type": "start", "init_data": "<tg initData>",
                     "rate": <mic sample rate>}   begin a call
  server -> client: {"type": "ready"}            mic can start
  server -> client: {"type": "chunk", ..., "greeting": true}   play greeting
  client -> server: binary (PCM int16 mono)                 mic audio chunks
  server -> client: {"type": "chunk", ...}       TTS reply audio/metadata
  server -> client: {"type": "interim", ...}     live partial STT transcript
  server -> client: {"type": "flush"}            drop queued audio (barge-in)
  server -> client: {"type": "finished", ...}    agent says done
  server -> client: {"type": "error", "error": ...}
  client -> server: {"type": "stop"}             hang up

Security (AUDIT FIX):
  * ``start`` may carry the Telegram WebApp ``initData``; when the daemon is
    started with --bot-token (or MOSSVOICE_BOT_TOKEN) the HMAC is verified
    against the bot token before the call session is created. Without a token
    configured the check is skipped (local/loopback operation).
"""

import argparse
import asyncio
import base64
import hashlib
import hmac
import http.client
import io
import json
import os
import socket
import struct
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import wave

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
import uvicorn

SAMPLE_RATE = 16000
CHUNK_MS = 30
CHUNK_SAMPLES = SAMPLE_RATE * CHUNK_MS // 1000          # 480
# End-of-speech detection gap. Was hard-coded 1100 ms which added >1 s after
# every user pause; now defaults to 700 ms and is tunable via env.
# (Too low: natural breathing pauses mid-sentence split an utterance into
# micro-turns with junk transcripts; too high: the agent feels slow.)
SILENCE_GAP_MS = int(os.environ.get("MOSS_SILENCE_GAP_MS", "700"))
MIN_TURN_SAMPLES = SAMPLE_RATE // 10                      # ignore < 0.1s
MAX_TURN_SAMPLES = SAMPLE_RATE * 10                       # hard cap 10s
ENERGY_THRESHOLD = 300.0                                 # absolute RMS gate (16-bit PCM)
MIN_SPEECH_MS = 220                                      # a turn must carry >= this much real speech
NOISE_FLOOR_RATIO = 3.0                                  # adaptive noise floor multiplier
# CONVERSATION FIX (echo suppression): while the AGENT audio is playing the
# device speaker leaks into the mic. That echo is much weaker than a real,
# close-up voice, so we demand a clearly higher energy (and a longer speech
# burst) before treating it as barge-in. Without this the agent kept hearing
# ITS OWN voice and interrupting itself with a phantom turn.
ECHO_THRESHOLD_RATIO = 2.6                              # stricter onset gate
ECHO_MIN_SPEECH_MS = 320                                # longer burst to confirm

# --- Load-handling limits (production hardening) ---------------------------------
# Every client gets a token bucket: a short burst is allowed, sustained
# connection storms are rejected with close code 4429. The global call cap
# backpressures the whole TTS pipeline (one generation at a time downstream),
# so a flood of callers cannot starve an in-progress conversation.
MAX_CALLS = int(os.environ.get("MOSS_TG_MAX_CALLS", "4"))
RATE_LIMIT_PER_SEC = float(os.environ.get("MOSS_TG_RATE", "1.0"))   # WS connects/sec
RATE_LIMIT_BURST = int(os.environ.get("MOSS_TG_BURST", "5"))        # allowed burst
# Total number of live WebSocket sessions we will ever accept. A single user
# with a legit call + a retry stays under this.
MAX_WS_SESSIONS = int(os.environ.get("MOSS_TG_MAX_WS", "16"))

app = FastAPI()


@app.middleware("http")
async def _no_cache_static(request, call_next):
    """FIX(initData): the Telegram in-app WebView aggressively caches the
    WebApp HTML/JS, so a stale page (without telegram-web-app.js, or that
    omits init_data) keeps posting an empty init_data and every call hits
    "init_data validation failed". Force no-store on everything so the client
    always re-fetches the current page."""
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


DEFAULT_GREETING = "Здравствуйте! Это МВЕРА. Как вы себя чувствуете?"

# Short timeouts for one-shot control calls (new_call, greeting, end_call).
# AUDIT FIX: they used to share the 600 s read timeout, which meant a wedged
# agent stalled the asyncio loop for up to 10 minutes.
CONTROL_TIMEOUT = 60


class TokenBucket:
    """Per-key token bucket. Small, thread-safe, used to rate-limit WS
    connects per client IP (the request comes through the cloudflared tunnel,
    whose peer IP we see in the CF-Connecting-IP header)."""

    def __init__(self, rate_per_sec, burst):
        self.rate = max(0.01, float(rate_per_sec))
        self.burst = max(1, int(burst))
        self._buckets = {}
        self._lock = threading.Lock()

    def take(self, key):
        now = time.monotonic()
        with self._lock:
            tokens, last = self._buckets.get(key, (float(self.burst), now))
            tokens = min(self.burst, tokens + (now - last) * self.rate)
            if tokens >= 1.0:
                self._buckets[key] = (tokens - 1.0, now)
                return True
            self._buckets[key] = (tokens, now)
            return False

    def size(self):
        with self._lock:
            return len(self._buckets)


connect_limiter = TokenBucket(RATE_LIMIT_PER_SEC, RATE_LIMIT_BURST)

# Live-load counters for the health endpoint and start-time admission control.
LOAD = {
    "ws_sessions": 0,
    "active_calls": 0,
    "rejected_rate": 0,
    "rejected_capacity": 0,
    "calls_total": 0,
}
_load_lock = threading.Lock()


def _load_inc(key, delta=1):
    with _load_lock:
        LOAD[key] = LOAD.get(key, 0) + delta
        return LOAD[key]


def validate_init_data(init_data, bot_token):
    """Verify the Telegram WebApp initData HMAC (AUDIT FIX).

    initData is a url-encoded query string containing key=val pairs plus a
    ``hash`` entry; the check data is the same string minus ``hash``, with
    pairs sorted alphabetically. Key = HMAC_SHA256("WebAppData", bot_token).
    Returns True when valid, False otherwise. Empty initData is invalid.

    Values are percent-decoded before the check string is built: Telegram
    signs the canonical (decoded) values, and parse_qsl converts '+' to ' '
    which would otherwise break the HMAC on JSON payloads.
    """
    if not init_data or not bot_token:
        return False
    try:
        check = {}
        received_hash = None
        for pair in str(init_data).split("&"):
            if "=" not in pair:
                if pair == "hash=":
                    received_hash = ""
                continue
            k, v = pair.split("=", 1)
            kv = urllib.parse.unquote(k.replace("+", " "))
            vv = urllib.parse.unquote(v.replace("+", " "))
            if kv == "hash":
                received_hash = vv
            else:
                check[kv] = vv
        if not received_hash:
            return False
        data_check_string = "\n".join(
            f"{k}={v}" for k, v in sorted(check.items()))
        secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"),
                              hashlib.sha256).digest()
        digest = hmac.new(secret_key, data_check_string.encode("utf-8"),
                          hashlib.sha256).hexdigest()
        return hmac.compare_digest(digest, received_hash)
    except Exception:  # noqa: BLE001
        return False


class AgentBridge:
    """Blocking HTTP client to call_agent.

    Every method here blocks; the WS layer runs them via run_in_executor
    (AUDIT FIX: they used to block the uvicorn event loop directly).
    """

    def __init__(self, agent_url, tmpdir):
        self.agent_url = agent_url.strip("/")
        parts = urllib.parse.urlsplit(self.agent_url)
        host, _, port = (parts.hostname or "127.0.0.1"), "", parts.port
        self._host = host
        self._port = int(port or 80)
        self.tmpdir = tmpdir
        self.call_id = None
        self._conn_lock = threading.Lock()
        self._active_conns = []          # for abort_all() on barge-in/disconnect
        os.makedirs(tmpdir, exist_ok=True)

    def _url(self, path):
        return self.agent_url + path

    def _post(self, path, payload, timeout=CONTROL_TIMEOUT):
        req = urllib.request.Request(
            self._url(path),
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))

    def greeting(self):
        """Return the greeting as {wav_b64} (Docker-safe, no shared fs) with
        a wav_path fallback for all-in-one host deployments."""
        data = self._post("/say", {"text": DEFAULT_GREETING, "wav_b64": True})
        return data

    def new_call(self):
        """Create an isolated call session; call_id is kept per bridge."""
        try:
            data = self._post("/calls", {})
            self.call_id = data.get("call_id")
        except Exception as e:
            print(f"[tg-server] /calls error: {e}", flush=True)
            self.call_id = None

    def end_call(self):
        if not self.call_id:
            return
        try:
            self._post(f"/calls/{self.call_id}/end", {})
        except Exception as e:
            print(f"[tg-server] /calls/{self.call_id}/end error: {e}", flush=True)
        finally:
            self.call_id = None

    def cancel_stream(self):
        """Ask the agent to abort the currently-generating TTS utterance
        (barge-in). Safe to call when nothing is streaming. The open stream
        connection is unblocked with ``sock.shutdown()`` ONLY — the owner
        thread (turn_stream's ``finally``) is the sole closer; closing here as
        well raced with the owner and raised NoneType/AttributeError on the
        dead socket."""
        with self._conn_lock:
            conns = list(self._active_conns)
        had = bool(conns)
        for c in conns:
            try:
                sock = getattr(c, "sock", None)
                if sock is not None:
                    sock.shutdown(socket.SHUT_RDWR)
            except Exception:  # noqa: BLE001
                pass
        if not self.call_id:
            return
        if not had:
            # CONVERSATION FIX: nothing is streaming — a stream-cancel POST
            # would just 404/log noise. (The greeting path has no call-side
            # stream to cancel anyway.)
            return
        try:
            self._post(f"/calls/{self.call_id}/stream-cancel", {})
        except Exception as e:
            print(f"[tg-server] stream-cancel error: {e}", flush=True)

    def turn_stream(self, pcm, rate=SAMPLE_RATE, cancel_event=None):
        """Yield frames from the agent's scoped /turn_stream endpoint.

        This is a *blocking* HTTP generator; run it in a worker thread (see
        TXPipeline.producer) so the event loop never blocks on network reads.

        The audio turns are sent INLINE as base64 (the telephony container
        does not share its filesystem with this gateway), and the HTTP
        connection is registered in _active_conns so a barge-in can close it
        synchronously (unblocking read1 immediately).
        """
        wav_bytes = pcm_to_wav_bytes(pcm, rate)
        conn = None
        try:
            conn = http.client.HTTPConnection(self._host, self._port,
                                              timeout=CONTROL_TIMEOUT * 10)
            with self._conn_lock:
                self._active_conns.append(conn)
            body = json.dumps(
                {"audio_b64": base64.b64encode(wav_bytes).decode("ascii")}
            ).encode("utf-8")
            path = f"/calls/{self.call_id}/turn_stream" if self.call_id \
                else "/turn_stream"
            conn.request("POST", path, body=body,
                         headers={"Content-Type": "application/json"})
            resp = conn.getresponse()
            if resp.status >= 400:
                # e.g. 429 call busy, 404 call gone — surface as an error frame
                err = resp.read().decode("utf-8", "replace")[:200]
                yield {"error": f"turn rejected ({resp.status})", "done": True}
                return
            buf = b""
            while True:
                if cancel_event is not None and cancel_event.is_set():
                    break
                chunk = resp.read1(65536)
                if not chunk:
                    break
                buf += chunk
                while True:
                    if len(buf) < 4:
                        break
                    n = int.from_bytes(buf[:4], "big")
                    if len(buf) < 4 + n:
                        break
                    payload = buf[4:4 + n]
                    buf = buf[4 + n:]
                    frame = json.loads(payload.decode("utf-8"))
                    yield frame
                    if frame.get("done"):
                        return
        except (http.client.HTTPException, OSError) as e:
            # A barge-in closes our connection on purpose; only log otherwise.
            if not (cancel_event is not None and cancel_event.is_set()):
                print(f"[tg-server] turn_stream connection error: {e}",
                      flush=True)
        finally:
            if conn is not None:
                with self._conn_lock:
                    if conn in self._active_conns:
                        self._active_conns.remove(conn)
                try:
                    conn.close()
                except Exception:  # noqa: BLE001
                    pass


def pcm_to_wav_bytes(pcm, rate):
    """int16 mono sample sequence -> WAV bytes, in memory (no temp file)."""
    if isinstance(pcm, (bytes, bytearray)):
        frames_b = bytes(pcm)
    else:
        frames_b = struct.pack("<%dh" % len(pcm), *pcm)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(rate))
        w.writeframes(frames_b)
    return buf.getvalue()


def rms(samples):
    if not samples:
        return 0.0
    s = sum(x * x for x in samples)
    return (s / len(samples)) ** 0.5


class VAD:
    """Always-on RX voice activity detector. No busy/embargo gating — the
    microphone is never muted because of what the agent is doing.

    Feed it int16 samples; timing accumulates as ``chunk_ms`` per feed (default
    CHUNK_MS). Callers that know the real chunk duration (client-reported
    sample rate) should pass it so silence/speech timers are exact (AUDIT FIX:
    the browser actually sends 1024-sample ScriptProcessor buffers, not 480).
    """

    def __init__(self):
        self.silence = 0
        self.speech_ms = 0
        self.buffer = []
        self.noise_floor = None

    def reset(self):
        self.silence = 0
        self.speech_ms = 0
        self.buffer = []
        self.noise_floor = None

    def speech_threshold(self, agent_speaking=False):
        base = ENERGY_THRESHOLD
        if self.noise_floor is not None:
            base = max(base, self.noise_floor * NOISE_FLOOR_RATIO)
        if agent_speaking:
            # CONVERSATION FIX: stricter gate while agent audio is playing so
            # speaker echo does not register as a barge-in.
            return base * ECHO_THRESHOLD_RATIO
        return base

    def feed(self, samples, chunk_ms=None, agent_speaking=False):
        """Returns (completed_turn_or_None, barge_in_onset_bool).

        barge-in onset is True exactly once, right when a speech burst starts,
        so the caller can cancel TTS/flush TX instantly while still buffering
        the whole utterance for STT (nothing is lost).

        ``agent_speaking`` enables speaker-echo suppression (CONVERSATION FIX):
        the onset gate is raised and the burst must last longer before it can
        close a turn, so the agent's own voice leaking through the mic does
        not create phantom user turns.
        """
        ms = float(chunk_ms or CHUNK_MS)
        e = rms(samples)
        if self.noise_floor is None:
            self.noise_floor = e if e < ENERGY_THRESHOLD * 4 else ENERGY_THRESHOLD
        thr = self.speech_threshold(agent_speaking=agent_speaking)
        onset = False
        if e >= thr:
            was_silent = self.speech_ms == 0
            self.silence = 0
            self.speech_ms += ms
            self.buffer.extend(samples)
            self.noise_floor = 0.999 * self.noise_floor + 0.001 * min(e, thr * 1.1)
            # onset alone triggers an immediate playback flush; the raised
            # echo threshold is the primary guard against speaker leakage, so
            # keep onset live for a fast real barge-in (CONVERSATION FIX: an
            # earlier version suppressed onset entirely while the agent spoke,
            # which added latency to legitimate interruptions).
            onset = was_silent and ms >= 10
        else:
            self.silence += ms
            self.noise_floor = 0.95 * self.noise_floor + 0.05 * e
            if self.silence < SILENCE_GAP_MS:
                self.buffer.extend(samples)

        if len(self.buffer) > MAX_TURN_SAMPLES:
            turn, self.buffer = self.buffer, []
            self.silence = 0
            self.speech_ms = 0
            return turn, onset

        if self.silence >= SILENCE_GAP_MS:
            min_ms = ECHO_MIN_SPEECH_MS if agent_speaking else MIN_SPEECH_MS
            if self.speech_ms < min_ms or len(self.buffer) < MIN_TURN_SAMPLES:
                self.buffer = []
                self.silence = 0
                self.speech_ms = 0
                return None, onset
            turn, self.buffer = self.buffer, []
            self.silence = 0
            self.speech_ms = 0
            return turn, onset
        return None, onset


class TXPipeline:
    """Separate TX pipeline: turns a completed user utterance into audio
    frames sent to the browser, with cancellation + flush for barge-in.

    AUDIT FIXES vs the first implementation:
      * a single send lock is created once and shared forever (previously a
        new lock per generation allowed two coroutines to write frames
        concurrently during the overlap window);
      * each generation captures ITS OWN cancel event in a local variable and
        passes it explicitly to the producer thread (previously the producer
        re-read self._cancel_event after it had already been replaced for the
        next generation, so old producers could not be cancelled);
      * producer threads are tracked and joined; abandoning a turn now tears
        down the HTTP connection immediately instead of leaking it for 600 s;
      * the producer queue is bounded so a wedged client cannot grow RAM
        without limit.
    """

    def __init__(self, bridge, send):
        self.bridge = bridge
        self.send = send                      # async callable(payload: dict)
        self._task = None
        self._cancel_event = threading.Event()
        self._send_lock = asyncio.Lock()      # shared, never swapped
        self.greeting_active = False          # greeting still playing on client
        # CONVERSATION FIX: while true, the RX VAD uses the stricter echo gate.
        # Tracks "the client is plausibly still playing agent audio" = we sent
        # audio within the last (sent + grace) seconds.
        self.speaking_until = 0.0
        self._gen = 0
        self._threads = []                    # live producer threads

    @property
    def busy(self):
        return self._task is not None and not self._task.done()

    @property
    def agent_speaking(self):
        return self.greeting_active or time.monotonic() < self.speaking_until

    def note_audio_chunk(self, wav_b64):
        """A TTS audio frame went to the client: extend the echo window."""
        try:
            nbytes = len(base64.b64decode(wav_b64, validate=False))
        except Exception:  # noqa: BLE001
            nbytes = 0
        # MOSS-TTS-Nano frames are 48 kHz mono 16-bit WAV => ~96000 bytes/s
        # of raw PCM + a small WAV header. (The legacy backend used 24 kHz =
        # 48000 bytes/s, which halved the window and let a phantom barge-in
        # fire on the tail of still-playing agent audio.)
        dur = nbytes / 96000.0 + 0.25
        self.speaking_until = max(self.speaking_until, time.monotonic() + dur)

    def barge_in(self):
        """Cancel current TTS generation and tell the client to flush its
        playback buffer. Called on user speech onset. Never blocks: the
        blocking cancel_stream HTTP call is offloaded to the loop's executor."""
        self._cancel_event.set()
        try:
            loop = asyncio.get_running_loop()
            loop.run_in_executor(None, self.bridge.cancel_stream)
        except RuntimeError:
            # called outside an event loop (tests) — run inline, it's cheap
            try:
                self.bridge.cancel_stream()
            except Exception:  # noqa: BLE001
                pass
        except Exception:  # noqa: BLE001
            pass
        try:
            loop = asyncio.get_running_loop()
            if self._task is not None and not self._task.done():
                # the running task will notice cancel_event and flush itself
                return
            loop.create_task(self._safe_send({"type": "flush"}))
        except Exception:  # noqa: BLE001
            pass

    def start_turn(self, pcm, rate=SAMPLE_RATE):
        """Start processing a completed user turn (non-blocking)."""
        self.greeting_active = False  # a real user turn supersedes the greeting
        self._gen += 1
        gen = self._gen
        cancel = threading.Event()  # AUDIT FIX: owned by THIS generation
        prev = self._task
        needs_flush = False
        if prev is not None and not prev.done():
            # overlapping turn: cancel the previous one cleanly first.
            self._cancel_event.set()
            prev.cancel()
            needs_flush = True
        self._cancel_event = cancel
        self._task = asyncio.create_task(self._run(pcm, rate, gen, cancel))
        if needs_flush:
            try:
                asyncio.get_running_loop().create_task(
                    self._safe_send({"type": "flush"}))
            except Exception:  # noqa: BLE001
                pass

    async def _run(self, pcm, rate, gen, cancel):
        meta = {}
        thread = None
        try:
            loop = asyncio.get_running_loop()
            # Latency-bound queue: at most ~48 audio frames (~1.5 s of audio).
            # When it overflows the OLDEST AUDIO is dropped so a stalled client
            # can never accumulate a 15 s backlog; control frames
            # (done/error/aborted/sentinel) are never dropped.
            MAX_QUEUE_FRAMES = 48
            queue = asyncio.Queue()  # unbounded; the cap is enforced in push

            def _is_ctl(frame):
                return frame is None or frame.get("done") or frame.get("error")

            def push(frame):
                if not _is_ctl(frame):
                    while queue.qsize() >= MAX_QUEUE_FRAMES:
                        old = queue.get_nowait()
                        if _is_ctl(old):
                            # restore a control frame we must not drop; the
                            # internal deque keeps FIFO order (runs on the
                            # event-loop thread via call_soon_threadsafe).
                            queue._queue.append(old)
                queue.put_nowait(frame)

            def producer():
                try:
                    for frame in self.bridge.turn_stream(
                            pcm, rate=rate, cancel_event=cancel):
                        loop.call_soon_threadsafe(push, frame)
                except Exception as e:
                    print(f"[tg-server] turn_stream producer: {e}", flush=True)
                    loop.call_soon_threadsafe(push, {"error": str(e), "done": True})
                finally:
                    loop.call_soon_threadsafe(push, None)  # sentinel

            thread = threading.Thread(target=producer, daemon=True)
            thread.start()
            self._threads.append(thread)

            while True:
                if cancel.is_set():
                    # barge-in: drop everything queued, emit flush + aborted
                    # done frame, stop.
                    await self._safe_send({"type": "flush"})
                    await self._safe_send({"type": "chunk", "done": True,
                                           "aborted": True, **meta})
                    break
                try:
                    frame = await asyncio.wait_for(queue.get(), timeout=0.05)
                except asyncio.TimeoutError:
                    continue
                if cancel.is_set():
                    # BARGE-IN RACE FIX (AUDIT A2): the producer's own
                    # aborted/done frame may already sit in the queue while we
                    # were inside a send. It must NEVER be treated as a normal
                    # completion — without this re-check the aborted flag was
                    # lost and the client saw a regular "finished" event.
                    await self._safe_send({"type": "flush"})
                    await self._safe_send({"type": "chunk", "done": True,
                                           "aborted": True, **meta})
                    break
                if frame is None:
                    break
                wire = self._to_wire(frame)
                if wire is None:
                    continue
                # interim STT frames stream live transcripts to the page but must
                # never clobber the real reply/transcript meta (P0-REALTIME-11).
                if frame.get("type") != "interim" and (
                        "transcript" in frame or "reply" in frame):
                    meta = {"transcript": frame.get("transcript"),
                            "reply": frame.get("reply"),
                            "finished": bool(frame.get("finished"))}
                if wire.get("wav_b64"):
                    # CONVERSATION FIX: extend the echo-suppression window while
                    # audio flows to the client.
                    self.note_audio_chunk(wire["wav_b64"])
                await self._safe_send(wire)
                if frame.get("done"):
                    # finished event separately so the UI can decide to end
                    await self._safe_send({"type": "finished",
                                           "finished": bool(frame.get("finished")),
                                           "transcript": frame.get("transcript"),
                                           "reply": frame.get("reply"),
                                           "outcome": frame.get("outcome"),
                                           "done": True})
                    break
        except asyncio.CancelledError:
            cancel.set()
            raise
        finally:
            # AUDIT FIX: join the producer thread so it cannot outlive its
            # generation; the connection is unblocked by cancel_stream.
            if thread is not None:
                try:
                    await asyncio.get_running_loop().run_in_executor(
                        None, thread.join, 5.0)
                except Exception:  # noqa: BLE001
                    pass
                try:
                    self._threads.remove(thread)
                except ValueError:
                    pass
            if gen == self._gen:
                self._task = None

    async def _safe_send(self, payload):
        try:
            async with self._send_lock:
                await self.send(payload)
        except Exception as e:
            print(f"[tg-server] send: {e}", flush=True)

    @staticmethod
    def _to_wire(frame):
        if frame.get("type") == "interim":
            # streaming-STT (P0-REALTIME-CORE step 11): pass partial transcripts
            # through to the client immediately for live display.
            wire = {"type": "interim", "transcript": frame.get("transcript"),
                    "final": bool(frame.get("final"))}
            if frame.get("reply"):
                wire["reply"] = frame.get("reply")
            return wire
        if frame.get("done"):
            wire = {"type": "chunk", "done": True,
                    "transcript": frame.get("transcript"),
                    "reply": frame.get("reply"),
                    "finished": bool(frame.get("finished"))}
            # preserve the cancel-origin of the done frame (AUDIT A2)
            if frame.get("aborted"):
                wire["aborted"] = True
            return wire
        wire = {"type": "chunk", "i": frame.get("i"),
                "wav_b64": frame.get("wav_b64"),
                "done": bool(frame.get("done"))}
        if frame.get("sample_rate"):
            wire["sample_rate"] = frame.get("sample_rate")
        return wire


@app.websocket("/ws")
async def ws(ws: WebSocket):
    # PROD: rate-limit WS connection attempts by client IP before accepting.
    try:
        headers = {k.decode("latin-1"): v.decode("latin-1")
                   for k, v in (ws.scope.get("headers") or [])}
        ip = (headers.get("cf-connecting-ip")
              or headers.get("x-forwarded-for", "").split(",")[0].strip()
              or (ws.client.host if ws.client else "unknown"))
    except Exception:  # noqa: BLE001
        ip = ws.client.host if ws.client else "unknown"
    if not connect_limiter.take(ip):
        _load_inc("rejected_rate")
        # 4429: custom "too many requests" — the WebApp page can surface it.
        await ws.accept()
        await ws.send_json({"type": "error", "error": "too many requests, retry later"})
        await ws.close(code=4429)
        return
    if LOAD["ws_sessions"] >= MAX_WS_SESSIONS or LOAD["active_calls"] >= MAX_CALLS:
        _load_inc("rejected_capacity")
        await ws.accept()
        await ws.send_json({"type": "error", "error": "server is busy, retry later"})
        await ws.close(code=4503)
        return

    await ws.accept()
    _load_inc("ws_sessions")
    bridge = AgentBridge(AGENT_URL, TMPDIR)
    vad = VAD()
    tx = TXPipeline(bridge, ws.send_json)
    active = False
    loop = asyncio.get_running_loop()
    mic_rate = SAMPLE_RATE        # client-reported, used for exact VAD timing
    greeting_play_task = None

    async def off(fn, *a):
        """Run a blocking bridge call off the event loop (AUDIT FIX B1)."""
        return await loop.run_in_executor(None, fn, *a)

    try:
        while True:
            raw = await ws.receive()
            if "bytes" in raw and raw["bytes"]:
                data = raw["bytes"]
                frames = len(data) // 2
                if frames == 0:
                    continue
                samples = struct.unpack("<%dh" % frames, data[: frames * 2])
                # exact chunk duration from the client's real sample rate
                chunk_ms = frames / float(mic_rate or SAMPLE_RATE) * 1000.0
                # CONVERSATION FIX: while the agent audio is plausibly still
                # playing on the client, use the stricter echo-suppression gate
                # so speaker leakage does not interrupt the agent mid-reply.
                turn, onset = vad.feed(samples, chunk_ms=chunk_ms,
                                       agent_speaking=tx.agent_speaking)
                if onset and (tx.busy or tx.greeting_active):
                    # USER STARTED TALKING WHILE THE AGENT SPEAKS -> barge-in
                    tx.barge_in()
                if turn and active:
                    tx.start_turn(turn)
                continue
            if "text" not in raw:
                continue
            try:
                msg = json.loads(raw["text"])
            except json.JSONDecodeError:
                continue
            if not isinstance(msg, dict):
                continue
            mtype = msg.get("type")
            if mtype == "start":
                # AUDIT FIX: validate the Telegram WebApp session when the
                # daemon was configured with a bot token. Without a token we
                # fall back to transport-level trust (loopback/tunnel).
                if BOT_TOKEN:
                    _init = msg.get("init_data") or ""
                    if not validate_init_data(_init, BOT_TOKEN):
                        if ALLOW_UNVERIFIED:
                            # DEV MODE: accept the session without HMAC so the
                            # page can be tested from a plain browser. NEVER
                            # set MOSS_TG_ALLOW_UNVERIFIED in production.
                            print("[tg-server] DEV MODE: accepting session "
                                  "without initData verification", flush=True)
                        else:
                            # SECURITY FIX(initData): never log initData
                            # (it carries the signed user identity) — log only
                            # reason, length and a safe non-reversible hash.
                            if not _init:
                                print("[tg-server] init_data EMPTY: WebApp page "
                                      "did not provide window.Telegram.WebApp."
                                      "initData (old cached page or script "
                                      "blocked)", flush=True)
                            else:
                                print(f"[tg-server] init_data HMAC FAILED "
                                      f"len={len(_init)} "
                                      f"hash={hashlib.sha256(_init.encode('utf-8','replace')).hexdigest()[:12]}",
                                      flush=True)
                            await ws.send_json({"type": "error",
                                                "error": "init_data validation failed"})
                            await ws.close(code=4401)
                            return
                # honour the client-reported mic sample rate (AUDIT FIX: the
                # server blindly assumed 16 kHz and VAD timers drifted ~40%).
                try:
                    r = int(msg.get("rate") or SAMPLE_RATE)
                    if 4000 <= r <= 96000:
                        mic_rate = r
                except (TypeError, ValueError):
                    pass
                vad.reset()
                if not active:
                    _load_inc("active_calls")
                    _load_inc("calls_total")
                active = True
                await off(bridge.new_call)
                await ws.send_json({"type": "ready"})
                gresp = await off(bridge.greeting)
                gb64 = (gresp or {}).get("wav_b64") or ""
                gpath = (gresp or {}).get("wav_path")
                if gb64 or (gpath and os.path.exists(gpath)):
                    if not gb64:
                        with open(gpath, "rb") as gf:
                            gb64 = base64.b64encode(gf.read()).decode("ascii")
                    tx.greeting_active = True
                    tx.note_audio_chunk(gb64)
                    await ws.send_json({"type": "chunk", "i": 0, "wav_b64": gb64,
                                        "greeting": True})
                    # greeting_active stays True until the client has had time
                    # to play the whole phrase (barge-in during it). Estimate
                    # from the local file if present, else from the known
                    # greeting length.
                    dur = 0.0
                    try:
                        if gpath and os.path.exists(gpath):
                            with wave.open(gpath, "rb") as gw:
                                dur = gw.getnframes() / float(gw.getframerate())
                    except Exception:  # noqa: BLE001
                        dur = 0.0
                    if dur <= 0:
                        # Docker: no local file — measure the WAV payload
                        # directly from its header (LATENCY FIX: the old code
                        # assumed 24 kHz mono and doubled the estimate for
                        # 48 kHz MOSS-TTS-Nano frames).
                        try:
                            raw = base64.b64decode(gb64, validate=False)
                            with wave.open(io.BytesIO(raw), "rb") as gw:
                                dur = gw.getnframes() / float(gw.getframerate())
                        except Exception:  # noqa: BLE001
                            dur = 0.0
                    if dur <= 0:
                        # last resort: 48 kHz mono 16-bit ≈ 96000 bytes/s
                        try:
                            nbytes = len(base64.b64decode(gb64, validate=False))
                        except Exception:  # noqa: BLE001
                            nbytes = 0
                        dur = max(1.0, nbytes / 96000.0)
                    greeting_play_task = loop.create_task(
                        _reset_greeting_after(tx, dur + 0.3))
                await ws.send_json({"type": "finished", "finished": False,
                                    "reply": DEFAULT_GREETING,
                                    "outcome": {"status": "started"}})
            elif mtype == "samplerate":
                # The WebApp confirms the REAL mic rate after its AudioContext
                # resumes (which can differ from the "start" guess). Accepting
                # it late keeps VAD timing exact (AUDIT FIX follow-up).
                try:
                    r = int(msg.get("sampleRate") or msg.get("rate") or 0)
                    if 4000 <= r <= 96000:
                        mic_rate = r
                except (TypeError, ValueError):
                    pass
            elif mtype == "stop":
                tx.barge_in()
                await off(bridge.end_call)
                await ws.close()
                return
    except WebSocketDisconnect:
        tx.barge_in()
        await off(bridge.end_call)
    except Exception as e:
        try:
            await ws.send_json({"type": "error", "error": str(e)})
        except Exception:  # noqa: BLE001
            pass
        await off(bridge.end_call)
    finally:
        _load_inc("ws_sessions", -1)
        if active:
            _load_inc("active_calls", -1)
        if greeting_play_task is not None:
            greeting_play_task.cancel()


async def _reset_greeting_after(tx, delay):
    try:
        await asyncio.sleep(delay)
        tx.greeting_active = False
    except asyncio.CancelledError:
        pass


@app.get("/health")
def health():
    with _load_lock:
        load = {
            "ws_sessions": LOAD["ws_sessions"],
            "active_calls": LOAD["active_calls"],
            "calls_total": LOAD["calls_total"],
            "rejected_rate": LOAD["rejected_rate"],
            "rejected_capacity": LOAD["rejected_capacity"],
        }
    return {
        "ok": True,
        "init_data_check": bool(BOT_TOKEN),
        "limits": {"max_calls": MAX_CALLS, "max_ws_sessions": MAX_WS_SESSIONS,
                   "rate_per_sec": RATE_LIMIT_PER_SEC, "burst": RATE_LIMIT_BURST},
        "load": load,
    }


@app.get("/metrics")
def metrics():
    with _load_lock:
        return {"ok": True, "load": dict(LOAD),
                "rate_buckets": connect_limiter.size()}


def main():
    global AGENT_URL, TMPDIR, BOT_TOKEN, ALLOW_UNVERIFIED
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8600)
    ap.add_argument("--agent", default="http://127.0.0.1:9400")
    ap.add_argument("--tmpdir", default="/tmp/mossvoice_ws")
    ap.add_argument("--web-dir", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "web"))
    ap.add_argument("--host", default="0.0.0.0",
                    help="bind address (keep 0.0.0.0: the Telegram WebApp "
                         "arrives through the cloudflared tunnel; initData "
                         "HMAC validation guards the /ws endpoint instead)")
    ap.add_argument("--bot-token", default=os.environ.get("MOSSVOICE_BOT_TOKEN", ""),
                    help="Telegram bot token used to validate WebApp initData "
                         "(empty = validation disabled)")
    ap.add_argument("--allow-unverified", action="store_true",
                    default=os.environ.get("MOSS_TG_ALLOW_UNVERIFIED") == "1",
                    help="DEV ONLY: accept sessions with empty/invalid "
                         "initData (e.g. testing the page in a plain "
                         "browser). Never enable in production.")
    args = ap.parse_args()
    AGENT_URL = args.agent
    TMPDIR = args.tmpdir
    BOT_TOKEN = (args.bot_token or "").strip()
    ALLOW_UNVERIFIED = bool(args.allow_unverified)

    web_dir = os.path.abspath(args.web_dir)

    class _NoCacheStatic(StaticFiles):
        """FIX(initData): the Telegram in-app WebView aggressively cached the
        HTML/JS, so an old page (without telegram-web-app.js) kept posting an
        empty init_data and every call hit "init_data validation failed".
        Force no-store caching so the client always fetches the current page."""

        async def get_response(self, full_path, scope):
            resp = await super().get_response(full_path, scope)
            resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            resp.headers["Pragma"] = "no-cache"
            resp.headers["Expires"] = "0"
            return resp

    if os.path.isdir(web_dir):
        app.mount("/", _NoCacheStatic(directory=web_dir, html=True), name="web")

    print(f"[tg-server] listening on {args.host}:{args.port}, agent={AGENT_URL}, "
          f"initData_check={'on' if BOT_TOKEN else 'off'}", flush=True)
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


AGENT_URL = "http://127.0.0.1:9400"
TMPDIR = "/tmp/mossvoice_ws"
BOT_TOKEN = ""
ALLOW_UNVERIFIED = False


if __name__ == "__main__":
    main()
