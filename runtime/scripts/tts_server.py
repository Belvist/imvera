#!/usr/bin/env python3
"""MossVoice TTS daemon — loads the TTS (+optional STT) model once and serves requests.

HTTP on 127.0.0.1:<port>. When chosen by the OS, the actual port is written to
``$runtime/port.txt`` so the macOS app can discover it.

Endpoints:
    GET  /health                 metrics + readiness
    GET  /history?client_id=     stored conversation for a client
    POST /generate               {text, refs, ...} -> full WAV (voice clone)
    POST /stream                 {text, refs, ...} -> length-prefixed JSON audio frames
    POST /transcribe             {audio_b64}       -> STT text
    POST /log                    {client_id, role, text} -> persist a turn
    POST /shutdown               graceful exit

Design notes
------------
- The voice-reference prompt cache is built ONCE per reference set (keyed by a
  content hash) and reused across requests — this removes the per-request
  reference-encoding cost, the single biggest latency win for short utterances.
- Generation is serialised via a single generation lock (only one model
  instance fits in RAM). Extra clients are admitted to a small FIFO wait-queue;
  when that is full we answer HTTP 503 + Retry-After instead of queuing forever.
- Streaming returns length-prefixed binary frames: 4-byte big-endian length,
  then a JSON payload with base64 WAV chunks for sentence-aligned, gapless
  playback (start-to-sound well under a second for short sentences).
"""
import argparse
import base64
import hashlib
import hmac
import io
import json
import os
import queue
import re
import sys
import threading
import time
import wave
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tts_common  # noqa: E402
from moss_runtime.silero_tts_backend import SileroTtsBackend  # noqa: E402


# SECURITY (MEDIUM-1): when set, every non-health endpoint requires
# ``Authorization: Bearer <MOSS_AUTH_TOKEN>``. The macOS app generates a
# random token per launch and passes it to its child daemon via the
# environment, so another local process can no longer use the app's TTS
# instance for free (generation costs seconds of GPU/CPU and queues ahead of
# the user). Unset = auth disabled (telephony daemons, Swift fallback path
# and tests keep working unchanged).
AUTH_TOKEN = os.environ.get("MOSS_AUTH_TOKEN", "").strip()


def auth_header_ok(headers):
    """Constant-time check of the shared auth token. Open when unset."""
    if not AUTH_TOKEN:
        return True
    hdr = headers.get("Authorization", "") if headers else ""
    return hmac.compare_digest(hdr, f"Bearer {AUTH_TOKEN}")


def sanitize_client_id(cid):
    """AUDIT FIX: client_id is used as a filename component. Restrict it to a
    safe charset, then collapse any residual ".." sequences so ``..`` can
    never appear in the resulting filename (dots alone remain legal)."""
    if not cid:
        return "local"
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", str(cid))[:64] or "local"
    while ".." in cleaned:
        cleaned = cleaned.replace("..", "__")
    return cleaned


class BusyError(Exception):
    pass


class StreamCancelled(Exception):
    """Raised internally when a client aborts an in-flight stream (barge-in)."""


class SingleFlight:
    """One in-flight generation (RAM limit) + a bounded wait-queue.

    Exactly one request runs the model at a time. If the model is already busy
    we wait in a small FIFO (max ``queue_size``); overflowing requests are
    rejected with HTTP 503 + Retry-After rather than queuing forever. This lets
    the HTTP layer accept many concurrent clients while the hardware (a single
    8 GB model instance) serialises the real compute.
    """

    def __init__(self, queue_size=8, reserve_timeout=30.0):
        self.queue_size = queue_size
        self.reserve_timeout = reserve_timeout
        self._cond = threading.Condition()
        self.in_flight = 0
        self.queued = 0
        self.accepted = 0
        self.rejected = 0

    @contextmanager
    def acquire(self):
        granted = self._reserve()
        if not granted:
            raise BusyError("server is busy")
        try:
            yield
        finally:
            self._release()

    def _reserve(self):
        with self._cond:
            if self.in_flight == 0:
                self.in_flight = 1
                self.accepted += 1
                return True
            if self.queued >= self.queue_size:
                self.rejected += 1
                return False
            self.queued += 1
            try:
                # AUDIT FIX: the wait used to be unbounded — a wedged
                # generation would hold the only slot forever and every queued
                # request would block a handler thread forever with it. The
                # timed wait turns a wedged slot into a 503 instead.
                deadline = time.time() + self.reserve_timeout
                while self.in_flight > 0:
                    remaining = deadline - time.time()
                    if remaining <= 0:
                        self.rejected += 1
                        return False
                    self._cond.wait(remaining)
                self.in_flight = 1
                self.accepted += 1
                return True
            finally:
                self.queued -= 1

    def _release(self):
        with self._cond:
            self.in_flight = 0
            self._cond.notify()

    def metrics(self):
        with self._cond:
            return {
                "in_flight": self.in_flight,
                "queued": self.queued,
                "accepted": self.accepted,
                "rejected": self.rejected,
                "capacity": 1,
                "max_queue": self.queue_size,
            }


class TTSWorker:
    # Bump when reference/preprocessing semantics change so a stale in-memory
    # prompt cache (built under an older code path) is never reused.
    REF_PREPROC_VERSION = "2"  # v2: aligned transcript via transcribe_merged

    def __init__(self, model_id, stt_model_id, load_stt):
        self.model_id = model_id
        self.sample_rate = None
        self.stt_model = None
        self.stt_model_needs_load = load_stt
        self.stt_model_loaded = not load_stt
        self.ready = False
        self.error = None
        self._stt_model_id = stt_model_id
        self._tts = None
        self._lock = threading.Lock()
        # STT lazy-load lock: two concurrent first /transcribe calls both see
        # stt_model is None and would load Whisper twice without this.
        self._stt_lk = threading.Lock()
        self._merged_lk = threading.Lock()
        self.merged_refs = {}
        self.prompt_cache = {}
        self.transcripts = {}
        self.ref_meta = {}
        self.stats = {"generate": 0, "stream": 0, "transcribe": 0, "total_ms": 0.0}
        # AUDIT FIX: server-side stream cancellation. Each in-flight /stream
        # registers a cancel event keyed by stream_id so a client can abort
        # generation mid-flight (barge-in) instead of relying on a socket RST
        # to eventually stop the model.
        self._streams = {}
        self._streams_lock = threading.Lock()
        self._load_tts(model_id)

    # ------------------------------------------------------------------ #
    # Stream-cancellation registry (AUDIT FIX)
    # ------------------------------------------------------------------ #
    def register_stream(self, stream_id):
        ev = threading.Event()
        with self._streams_lock:
            self._streams[stream_id] = ev
        return ev

    def cancel_stream(self, stream_id):
        with self._streams_lock:
            ev = self._streams.get(stream_id)
        if ev is not None:
            ev.set()
            return True
        return False

    def unregister_stream(self, stream_id):
        with self._streams_lock:
            self._streams.pop(stream_id, None)

    # ------------------------------------------------------------------ #
    def _load_tts(self, model_id):
        try:
            if model_id == "silero":
                self._tts = SileroTtsBackend()
            else:
                self._tts = tts_common.load_tts(model_id)
            self.sample_rate = int(self._tts.tts_model.sample_rate)
            self.ready = True
            self.error = None
        except Exception as exc:  # noqa: BLE001
            self.ready = False
            self.error = str(exc)

    def _key(self, ref_paths, reference_text=None):
        """Cache key: audio fingerprint + transcript + model + language + preproc.

        P0-VC-003: a cache entry is valid only if BOTH the reference audio and
        the exact ref_text used for ICL match, on THIS model/language build.
        """
        ref_text = ((reference_text or "").strip()) or None
        key = tts_common.hash_references(ref_paths)
        if not key:
            return None
        parts = [key]
        if ref_text:
            parts.append(hashlib.sha256(ref_text.encode("utf-8")).hexdigest())
        parts.append(tts_common.STT_LANGUAGE)
        parts.append(tts_common.REF_PREPROC_VERSION)
        return "|".join(parts) + f"|{self.model_id}"

    def _ensure_ref(self, ref_paths):
        """Return (key, merged_ref_path) for a reference set."""
        key = self._key(ref_paths)
        if not key:
            return None, None
        if key in self.merged_refs:
            return key, self.merged_refs[key]
        with self._merged_lk:
            if key in self.merged_refs:
                return key, self.merged_refs[key]
            merged = tts_common.merge_references(ref_paths)
            self.merged_refs[key] = merged
        return key, merged

    def _resolve_ref_text(self, merged, reference_text=None):
        """Return (ref_text, source, audio_seconds).

        source is "client" (explicit reference_text), "stt" (auto-transcribed
        from the actual merged audio so it is aligned with truncation) or None.
        """
        secs = tts_common.audio_seconds(merged) if merged else None
        ref_text = ((reference_text or "").strip()) or None
        if ref_text:
            return ref_text, "client", secs
        if not merged:
            return None, None, secs
        is_qwen = getattr(getattr(self._tts, "tts_model", None), "_is_qwen3", False)
        if not is_qwen:
            # MOSS-TTS-Nano clones zero-shot from the audio itself — no
            # transcript is required.
            return None, None, secs
        # Legacy ICL cloning needed the reference transcript; STT on the
        # merged (post-truncation) audio aligned the text with the audio.
        self._ensure_stt()
        text, secs = tts_common.transcribe_merged(merged, self.stt_model)
        return text, "stt" if text else None, secs

    def _ensure_cache(self, ref_paths, reference_text=None):
        """Build the per-voice prompt cache once per reference set.

        MOSS-TTS-Nano (non-Qwen3 engine) clones zero-shot from the merged
        reference audio and needs no transcript; with no reference it falls
        back to its built-in voice, keyed by model_id.
        """
        if not getattr(getattr(self._tts, "tts_model", None), "_is_qwen3", True):
            ref_text = ((reference_text or "").strip()) or None
            key = self._key(ref_paths, ref_text) or self.model_id
            _, merged = self._ensure_ref(ref_paths)
            if key in self.prompt_cache:
                return key, self.prompt_cache[key]
            with self._lock:
                if key in self.prompt_cache:
                    return key, self.prompt_cache[key]
                if self._tts is None:
                    return key, None
                secs = tts_common.audio_seconds(merged) if merged else None
                quality = None
                if merged:
                    try:
                        quality = tts_common.validate_reference(merged)
                    except Exception:  # noqa: BLE001
                        quality = None
                self.ref_meta[key] = {
                    "source": "client" if ref_text else ("audio" if merged else "none"),
                    "audio_seconds": secs,
                    "text": ref_text or None,
                    "quality": quality,
                }
                self.prompt_cache[key] = tts_common.build_prompt_cache(
                    self._tts, merged, ref_text=ref_text
                )
            return key, self.prompt_cache[key]
        ref_text = ((reference_text or "").strip()) or None
        key = self._key(ref_paths, ref_text)
        _, merged = self._ensure_ref(ref_paths)
        if not key or not merged:
            return None, None
        if key in self.prompt_cache:
            return key, self.prompt_cache[key]
        with self._lock:
            if key in self.prompt_cache:
                return key, self.prompt_cache[key]
            if self._tts is None:
                return key, None
            resolved, source, secs = self._resolve_ref_text(merged, ref_text)
            quality = None
            if resolved:
                try:
                    quality = tts_common.validate_reference(merged)
                except Exception:  # noqa: BLE001
                    quality = None
            if resolved:
                self.transcripts[key] = resolved
            self.ref_meta[key] = {
                "source": source,
                "audio_seconds": secs,
                "text": resolved,
                "quality": quality,
            }
            self.prompt_cache[key] = tts_common.build_prompt_cache(
                self._tts, merged, ref_text=resolved
            )
        return key, self.prompt_cache[key]

    # ------------------------------------------------------------------ #
    # STT
    # ------------------------------------------------------------------ #
    def _ensure_stt(self):
        if self.stt_model is not None:
            return True
        if self.stt_model_loaded:
            return False
        with self._stt_lk:
            if self.stt_model is not None:
                return True
            if self.stt_model_loaded:
                return False
            try:
                self.stt_model = tts_common.load_stt(self._stt_model_id)
                self.stt_model_loaded = True
                return True
            except Exception as exc:  # noqa: BLE001
                print(f"[tts-server] STT load failed: {exc}", file=sys.stderr)
                self.stt_model_loaded = True
                self.stt_model = None
                return False

    def transcribe(self, audio_path):
        if not (self._ensure_stt() and self.stt_model is not None):
            return None
        return tts_common.transcribe_reference([audio_path], self.stt_model)

    # ------------------------------------------------------------------ #
    # Non-streaming generate
    # ------------------------------------------------------------------ #
    def generate(self, text, ref_paths, max_len, cfg_value=None,
                 inference_steps=None, style_enabled=False, reference_text=None):
        if not self.ready or self._tts is None:
            return None, None, self.error or "model not ready"
        start = time.time()
        if isinstance(self._tts, SileroTtsBackend):
            audio, sr, err = self._tts.generate(
                text=text, style_enabled=style_enabled)
            self._bump("generate", start)
            return audio, sr, err
        cfg = cfg_value if isinstance(cfg_value, (int, float)) and cfg_value > 0 else tts_common.CFG_VALUE
        steps = int(inference_steps) if inference_steps and int(inference_steps) > 0 else tts_common.INFERENCE_TIMESTEPS

        _key, cache = self._ensure_cache(ref_paths, reference_text)
        if cache is None:
            return None, "Не удалось построить кэш голоса (проверьте образец)."

        with self._lock:
            segments = tts_common.split_sentences(tts_common.apply_style(text, style_enabled))
            all_audio = []
            for seg in segments:
                all_audio.append(
                    tts_common.generate_single(
                        self._tts.tts_model, seg, cache,
                        cfg_value=cfg, inference_timesteps=steps, max_len=max_len,
                    )
                )
            if not all_audio:
                return None, "Генерация не вернула аудио.", None
            audio = np.concatenate(all_audio)

        audio = tts_common.normalize_waveform(audio)
        self._bump("generate", start)
        return audio, self.sample_rate, None

    # ------------------------------------------------------------------ #
    # Streaming generator
    # ------------------------------------------------------------------ #
    def stream_generate(self, text, ref_paths, max_len, cfg_value=None,
                        inference_steps=None, style_enabled=False, reference_text=None,
                        cancel_event=None):
        if not self.ready or self._tts is None:
            raise RuntimeError(self.error or "model not ready")
        start = time.time()
        if isinstance(self._tts, SileroTtsBackend):
            for wav in self._tts.stream_generate(
                    text=text, style_enabled=style_enabled,
                    cancel_event=cancel_event):
                yield wav
            self._bump("stream", start)
            return
        cfg = cfg_value if isinstance(cfg_value, (int, float)) and cfg_value > 0 else tts_common.CFG_VALUE
        steps = int(inference_steps) if inference_steps and int(inference_steps) > 0 else tts_common.INFERENCE_TIMESTEPS

        _key, cache = self._ensure_cache(ref_paths, reference_text)
        if cache is None:
            raise RuntimeError("Не удалось построить кэш голоса.")

        segments = tts_common.split_sentences(tts_common.apply_style(text, style_enabled))
        for seg in segments:
            # AUDIT FIX: check the cancel token before each segment so a
            # barge-in does not keep generating the rest of the utterance.
            if cancel_event is not None and cancel_event.is_set():
                self._bump("stream", start)
                raise StreamCancelled("stream cancelled")
            try:
                # Cancellation is checked between yielded chunks (below); a
                # single chunk is ~a decode step so that is the abort
                # granularity for the model itself.
                for wav in tts_common.generate_stream_chunks(
                    self._tts.tts_model, seg, cache,
                    cfg_value=cfg, inference_timesteps=steps, max_len=max_len,
                ):
                    if cancel_event is not None and cancel_event.is_set():
                        self._bump("stream", start)
                        raise StreamCancelled("stream cancelled")
                    yield wav
            except StreamCancelled:
                raise
            except Exception as exc:  # noqa: BLE001
                if cancel_event is not None and cancel_event.is_set():
                    raise StreamCancelled("stream cancelled") from exc
                raise
        self._bump("stream", start)

    def _bump(self, kind, start):
        self.stats[kind] += 1
        self.stats["total_ms"] += (time.time() - start) * 1000


# --------------------------------------------------------------------------- #
# Conversation log (what the interlocutor wants, persisted per client)
# --------------------------------------------------------------------------- #
class Registry:
    def __init__(self, runtime_dir):
        self.conv_dir = os.path.join(runtime_dir, "conversations") if runtime_dir else None
        if self.conv_dir:
            os.makedirs(self.conv_dir, exist_ok=True)
        self._lock = threading.Lock()

    def append(self, client_id, role, text, audio_path=None):
        client_id = sanitize_client_id(client_id)
        if not client_id or not self.conv_dir:
            return
        entry = {
            "ts": time.time(),
            "role": role,
            "text": str(text)[:4000],
            "audio": audio_path,
        }
        with self._lock:
            f = os.path.join(self.conv_dir, f"{client_id}.jsonl")
            with open(f, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def read(self, client_id, limit=200):
        client_id = sanitize_client_id(client_id)
        if not client_id or not self.conv_dir:
            return []
        f = os.path.join(self.conv_dir, f"{client_id}.jsonl")
        if not os.path.exists(f):
            return []
        out = []
        with self._lock:
            with open(f, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        out.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return out[-limit:]


ALLOWED_REF_ROOTS = []


def ref_allowed(path):
    """SECURITY FIX: only accept reference audio inside trusted directories.

    Previously any local process could pass arbitrary file paths as ``refs``;
    the daemon transcribed them and returned the text in ``reference_text``
    (arbitrary audio -> text exfiltration, incl. phone-call recordings).
    """
    if not path:
        return False
    real = os.path.realpath(path)
    for root in ALLOWED_REF_ROOTS:
        if real == os.path.realpath(root) or real.startswith(
                os.path.realpath(root) + os.sep):
            return True
    return False


def refs_valid(paths):
    return bool(paths) and any(p and os.path.exists(p) and ref_allowed(p)
                                for p in paths)


def make_wav_bytes(audio, sample_rate):
    buf = io.BytesIO()
    # AUDIT FIX: clip before casting. Un-normalised streamed audio could
    # exceed [-1, 1] and wrap around on the int16 cast, producing crackle.
    pcm = (np.clip(audio, -1.0, 1.0) * 32767.0).astype(np.int16)
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(sample_rate))
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


def _frame(sample_rate, idx, total, done, audio, extra=None):
    frame = {"sample_rate": sample_rate, "i": idx, "total": total, "done": done}
    if extra:
        frame.update(extra)
    if audio is not None:
        frame["wav_b64"] = base64.b64encode(make_wav_bytes(audio, sample_rate)).decode("ascii")
    payload = json.dumps(frame, ensure_ascii=False).encode("utf-8")
    return len(payload).to_bytes(4, "big") + payload


def _error_frame(error):
    payload = json.dumps({"error": str(error), "done": True}, ensure_ascii=False).encode("utf-8")
    return len(payload).to_bytes(4, "big") + payload


def build_handler(worker, registry):
    def refs_or_clone_free(paths):
        refs = [p for p in paths if p]
        if not refs:
            # No reference given: MOSS falls back to a built-in voice.
            return not getattr(getattr(worker._tts, "tts_model", None), "_is_qwen3", False)
        return refs_valid(paths)

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        # AUDIT FIX: without a timeout, handler threads parked on idle
        # keep-alive connections (or half-closed streaming peers) leaked
        # forever, one per dead socket.
        timeout = 30

        def log_message(self, *args):
            pass

        def _raw(self, status, content, ctype="application/json"):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def _json(self, obj, status=200):
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self._raw(status, body)

        def _body(self):
            length = self.headers.get("Content-Length")
            try:
                length = int(length or 0)
            except ValueError:
                length = 0
            return self.rfile.read(length) if length else b""

        def _json_body(self):
            raw = self._body()
            if not raw:
                return {}
            try:
                return json.loads(raw.decode("utf-8"))
            except Exception as exc:  # noqa: BLE001
                raise ValueError(f"bad request: {exc}")

        def _authorized(self):
            return auth_header_ok(self.headers)

        def _forbidden(self):
            self._json({"ok": False, "error": "forbidden: missing or bad token"}, 401)

        # ---------------- GET ----------------
        def do_GET(self):
            path = self.path.split("?")[0]
            if path in ("/health", "/healthz"):
                self._json({
                    # read.md rev-3 G4: identity contract — the supervisor
                    # refuses to adopt a port whose /health does not answer
                    # this service name + protocol_version.
                    "service": "mossvoice-tts",
                    "protocol_version": 1,
                    "ok": True,
                    "ready": worker.ready,
                    "sample_rate": worker.sample_rate,
                    "stt_ready": worker.stt_model_loaded,
                    "error": worker.error,
                    "metrics": worker.slot.metrics(),
                    "stats": worker.stats,
                })
            elif path == "/history":
                if not self._authorized():
                    self._forbidden()
                    return
                qs = parse_qs(urlparse(self.path).query)
                cid = (qs.get("client_id") or [""])[0] or "local"
                limit = int((qs.get("limit") or ["200"])[0])
                self._json({"ok": True, "client_id": cid, "history": registry.read(cid, limit)})
            else:
                self._json({"ok": False, "error": "not found"}, 404)

        # ---------------- POST ----------------
        def do_POST(self):
            path = self.path.split("?")[0]
            if not self._authorized():
                self._forbidden()
                return
            if path == "/transcribe":
                self._handle_transcribe()
            elif path == "/log":
                self._handle_log()
            elif path == "/generate":
                self._handle_generate()
            elif path == "/stream":
                self._handle_stream()
            elif path == "/stream-cancel":
                self._handle_stream_cancel()
            elif path == "/shutdown":
                self._handle_shutdown()
            else:
                self._json({"ok": False, "error": "not found"}, 404)

        # ---------------- stream-cancel (AUDIT FIX) ----------------
        def _handle_stream_cancel(self):
            try:
                payload = self._json_body()
            except ValueError as exc:
                self._json({"ok": False, "error": str(exc)}, 400)
                return
            stream_id = str(payload.get("stream_id") or "")
            if not stream_id:
                self._json({"ok": False, "error": "missing stream_id"}, 400)
                return
            hit = worker.cancel_stream(stream_id)
            self._json({"ok": True, "cancelled": hit})

        # ---------------- shutdown (AUDIT FIX: loopback only) ----------------
        def _handle_shutdown(self):
            # The daemon has no auth; /shutdown was previously world-callable
            # on loopback. It is meant for the owning app only, which connects
            # from ::1 (IPv6 loopback) when using 127.0.0.1 listeners on
            # macOS. Accept 127.0.0.1/::1 peers; reject anything else.
            peer = self.client_address[0] if self.client_address else ""
            if peer not in ("127.0.0.1", "::1", "localhost"):
                self._json({"ok": False, "error": "forbidden"}, 403)
                return
            self._json({"ok": True, "shutting_down": True})
            threading.Thread(target=self.server.shutdown, daemon=True).start()

        # ---------------- generate ----------------
        def _handle_generate(self):
            # AUDIT FIX: read the request body BEFORE reserving the single
            # generation slot. A slow/malicious body sender used to hold the
            # slot while trickling bytes, starving every real request.
            try:
                payload = self._json_body()
            except ValueError as exc:
                self._json({"ok": False, "error": str(exc)}, 400)
                return
            try:
                with worker.slot.acquire():
                    text = (payload.get("text") or "").strip()
                    refs_p = payload.get("refs") or []
                    if not text:
                        raise ValueError("empty text")
                    if not refs_or_clone_free(refs_p):
                        raise ValueError("no reference audio")
                    cfg = payload.get("cfg_value") or 0
                    steps = payload.get("inference_steps") or 0
                    max_len = int(payload.get("max_new_tokens") or 4096)
                    style = bool(payload.get("style_enabled"))
                    ref_text = (payload.get("reference_text") or "").strip() or None
                    ref_texts = payload.get("reference_texts") or []
                    if ref_texts:
                        joined = " ".join(
                            str(t).strip() for t in ref_texts if str(t).strip()
                        ).strip()
                        if joined:
                            ref_text = joined
                    cid = payload.get("client_id") or "local"

                    audio, sr, err = worker.generate(
                        text=text, ref_paths=refs_p, max_len=max_len,
                        cfg_value=cfg, inference_steps=steps, style_enabled=style,
                        reference_text=ref_text,
                    )
                    if err is not None:
                        self._json({"ok": False, "error": err}, 500)
                        return
                    wav_bytes = make_wav_bytes(audio, sr)
                    registry.append(cid, "assistant", text)
                    resp = {
                        "ok": True,
                        "sample_rate": sr,
                        "wav_b64": base64.b64encode(wav_bytes).decode("ascii"),
                        "text": text,
                    }
                    trace = getattr(worker._tts, "last_tts_trace", None)
                    if isinstance(trace, dict):
                        resp["tts_trace"] = trace
                    meta = worker.ref_meta.get(worker._key(refs_p, ref_text))
                    if meta:
                        resp["reference_text_source"] = meta.get("source")
                        resp["reference_audio_seconds"] = meta.get("audio_seconds")
                        resp["reference_text"] = meta.get("text")
                        if meta.get("quality"):
                            resp["reference_quality"], resp["reference_warnings"] = meta["quality"]
                    self._json(resp)
            except BusyError:
                self._send_busy()
            except ValueError as exc:
                self._json({"ok": False, "error": str(exc)}, 400)
            except Exception as exc:  # noqa: BLE001
                self._json({"ok": False, "error": str(exc)}, 500)

        # ---------------- stream ----------------
        def _handle_stream(self):
            # AUDIT FIX: parse/validate the body BEFORE reserving the slot and
            # before writing streaming headers, so a slow or malformed sender
            # can't wedge the generation slot or force a half-written stream.
            try:
                payload = self._json_body()
            except ValueError as exc:
                self._json({"ok": False, "error": str(exc)}, 400)
                return
            text = (payload.get("text") or "").strip()
            refs_p = payload.get("refs") or []
            if not text:
                self._json({"ok": False, "error": "empty text"}, 400)
                return
            if not refs_or_clone_free(refs_p):
                self._json({"ok": False, "error": "no reference audio"}, 400)
                return
            cfg = payload.get("cfg_value") or 0
            steps = payload.get("inference_steps") or 0
            max_len = int(payload.get("max_new_tokens") or 4096)
            style = bool(payload.get("style_enabled"))
            ref_text = (payload.get("reference_text") or "").strip() or None
            ref_texts = payload.get("reference_texts") or []
            if ref_texts:
                joined = " ".join(
                    str(t).strip() for t in ref_texts if str(t).strip()
                ).strip()
                if joined:
                    ref_text = joined
            cid = payload.get("client_id") or "local"
            # AUDIT FIX: server-side cancellation. The caller may send a
            # stream_id and later POST /stream-cancel with it to abort
            # generation mid-flight (barge-in).
            stream_id = str(payload.get("stream_id") or "")

            try:
                with worker.slot.acquire():
                    self.send_response(200)
                    self.send_header("Content-Type", "application/octet-stream")
                    self.send_header("Transfer-Encoding", "chunked")
                    self.end_headers()

                    def write_chunked(data, cssize=48 * 1024):
                        for i in range(0, len(data), cssize):
                            part = data[i:i + cssize]
                            self.wfile.write(b"%X\r\n" % len(part))
                            self.wfile.write(part)
                            self.wfile.write(b"\r\n")

                    try:
                        try:
                            sent = 0
                            cancel_event = worker.register_stream(stream_id) \
                                if stream_id else None
                            for wav in worker.stream_generate(
                                text=text, ref_paths=refs_p, max_len=max_len,
                                cfg_value=cfg, inference_steps=steps,
                                style_enabled=style,
                                reference_text=ref_text,
                                cancel_event=cancel_event,
                            ):
                                write_chunked(_frame(worker.sample_rate, sent,
                                                     sent + 1, False, wav))
                                sent += 1
                        except StreamCancelled:
                            write_chunked(_frame(worker.sample_rate, sent, sent,
                                                 True, None,
                                                 extra={"cancelled": True}))
                            self.wfile.write(b"0\r\n\r\n")
                            self.wfile.flush()
                            return
                        meta = worker.ref_meta.get(worker._key(refs_p, ref_text))
                        extra = {}
                        if meta:
                            extra["reference_text_source"] = meta.get("source")
                            extra["reference_audio_seconds"] = meta.get("audio_seconds")
                            extra["reference_text"] = meta.get("text")
                            if meta.get("quality"):
                                extra["reference_quality"], extra["reference_warnings"] = meta["quality"]
                        write_chunked(_frame(worker.sample_rate, sent, sent, True, None, extra=extra))
                        self.wfile.write(b"0\r\n\r\n")
                        self.wfile.flush()
                        registry.append(cid, "assistant", text)
                    finally:
                        if stream_id:
                            worker.unregister_stream(stream_id)
            except BusyError:
                self._send_busy()
            except Exception as exc:  # noqa: BLE001
                try:
                    write_chunked(_error_frame(exc))
                    self.wfile.write(b"0\r\n\r\n")
                    self.wfile.flush()
                except Exception:  # noqa: BLE001
                    pass

        # ---------------- transcribe ----------------
        def _handle_transcribe(self):
            try:
                payload = self._json_body()
                b64 = payload.get("audio_b64") or ""
                if not b64:
                    raise ValueError("missing audio_b64")
                import tempfile as _tf
                with _tf.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
                    tf.write(base64.b64decode(b64.encode("ascii")))
                    tmp = tf.name
                try:
                    # SingleFlight: STT shares the CPU with TTS synthesis —
                    # running it outside the slot broke the "one generation
                    # at a time" invariant and let Whisper compete with the
                    # realtime voice path.
                    with worker.slot.acquire():
                        text = worker.transcribe(tmp)
                except BusyError:
                    self._json({"ok": False,
                                "error": "server is busy"}, 503)
                    return
                finally:
                    try:
                        os.unlink(tmp)
                    except OSError:
                        pass
                if text is None:
                    self._json({"ok": False, "error": "STT недоступен"}, 503)
                    return
                registry.append(payload.get("client_id") or "local", "user", text)
                self._json({"ok": True, "text": text})
            except ValueError as exc:
                self._json({"ok": False, "error": str(exc)}, 400)
            except Exception as exc:  # noqa: BLE001
                self._json({"ok": False, "error": str(exc)}, 500)

        # ---------------- log ----------------
        def _handle_log(self):
            try:
                payload = json.loads(self._body().decode("utf-8") or "{}")
            except Exception as exc:  # noqa: BLE001
                self._json({"ok": False, "error": str(exc)}, 400)
                return
            cid = payload.get("client_id") or "local"
            role = payload.get("role") if payload.get("role") in ("user", "assistant") else "user"
            text = (payload.get("text") or "").strip()
            if not text:
                self._json({"ok": False, "error": "empty text"}, 400)
                return
            registry.append(cid, role, text, audio_path=payload.get("audio"))
            self._json({"ok": True, "client_id": cid})

        # ---------------- helpers ----------------
        def _send_busy(self):
            self.send_response(503)
            self.send_header("Content-Type", "application/json")
            self.send_header("Retry-After", "1")
            body = b'{"ok":false,"error":"server is busy"}'
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    # assign slot to worker
    worker.slot = SingleFlight()
    return Handler


def _main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=tts_common.DEFAULT_TTS_MODEL)
    ap.add_argument("--stt-model", default=tts_common.DEFAULT_STT_MODEL)
    ap.add_argument("--port", type=int, default=int(os.environ.get("MOSS_PORT", "0")))
    ap.add_argument("--host", default=os.environ.get("MOSS_BIND_HOST", "127.0.0.1"),
                    help="bind address; loopback by default, other values are "
                         "for isolated networks (Docker)")
    ap.add_argument("--runtime", default=os.environ.get("MOSS_RUNTIME", ""))
    ap.add_argument("--threads", type=int, default=int(os.environ.get("MOSS_THREADS", "0")))
    ap.add_argument("--no-stt", action="store_true")
    ap.add_argument("--queue-size", type=int, default=int(os.environ.get("MOSS_QUEUE", "8")))
    ap.add_argument("--allow-ref-dir", action="append", default=[],
                    help="extra directory whose audio files may be used as TTS references "
                         "(may be repeated); the macOS app support dir is always allowed")
    a = ap.parse_args()

    # SECURITY FIX: whitelist the directories the daemon will read reference
    # audio from. Default root is the app's own support dir (work/, recordings/,
    # outputs/); callers like the telephony stack add theirs via --allow-ref-dir.
    global ALLOWED_REF_ROOTS
    default_root = os.path.expanduser(
        os.path.join("~", "Library", "Application Support", "MossVoice"))
    ALLOWED_REF_ROOTS = [default_root] + [os.path.abspath(d) for d in a.allow_ref_dir]

    if a.threads > 0:
        try:
            import torch
            torch.set_num_threads(a.threads)
            os.environ.setdefault("OMP_NUM_THREADS", str(a.threads))
        except Exception as exc:  # noqa: BLE001
            print(f"[tts-server] thread config ignored: {exc}", file=sys.stderr)

    worker = TTSWorker(a.model, a.stt_model, load_stt=not a.no_stt)
    registry = Registry(a.runtime)

    Handler = build_handler(worker, registry)
    Handler._worker = worker
    Handler._registry = registry

    class QuietHTTPServer(ThreadingHTTPServer):
        """CONVERSATION FIX: streaming clients drop connections mid-stream on
        barge-in/restart, and the stdlib handler thread prints a full traceback
        per benign peer reset (ConnectionResetError spam). Real handler
        exceptions still surface."""

        daemon_threads = True

        def handle_error(self, request, client_address):
            exc = sys.exc_info()[1]
            if isinstance(exc, (ConnectionResetError, BrokenPipeError,
                                ConnectionAbortedError, TimeoutError)):
                return
            import traceback
            traceback.print_exc(limit=5)

    httpd = QuietHTTPServer((a.host, a.port), Handler)
    actual_port = httpd.server_address[1]

    if a.runtime:
        try:
            os.makedirs(a.runtime, exist_ok=True)
            with open(os.path.join(a.runtime, "port.txt"), "w") as f:
                f.write(str(actual_port))
        except Exception as exc:  # noqa: BLE001
            print(f"[tts-server] could not write port file: {exc}", file=sys.stderr)

    print(
        f"[tts-server] listening on {a.host}:{actual_port} "
        f"ready={worker.ready} sample_rate={worker.sample_rate} "
        f"stt={worker.stt_model_loaded}", flush=True
    )

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    _main()