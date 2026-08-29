#!/usr/bin/env python3
"""MossVoice LLM daemon — answer-generation service (сервис 2 из 3).

Loads ONE Qwen3 model once and serves chat completion requests over
HTTP. Kept fully separate from the voice and telephony services so each can
be scaled, restarted and failed independently.

Backends (chosen via MOSS_LLM_BACKEND: auto|mlx|transformers):
  * mlx (default on Apple Silicon — fastest);
  * transformers (Docker/Linux deployment where Metal is unavailable).

HTTP (127.0.0.1:<port>):
    GET  /health       readiness + capacity metrics
    POST /chat         {"messages": [{"role","content"}, ...]} -> {"ok", "text"}
    POST /chat_stream  token streaming (REALTIME FIX, Stage 5):
                       same body as /chat; the response is a length-prefixed
                       JSON frame stream — {"delta": "..."} per token burst,
                       then {"done": true, "text": "<full reply>"}.
    POST /shutdown     graceful exit (loopback only)

Load handling:
  * exactly one generation at a time (a single model instance in RAM);
  * a bounded FIFO wait-queue; overflowing requests get HTTP 503 +
    Retry-After instead of queueing forever;
  * oversized request bodies are rejected before touching the queue.
"""
import argparse
import json
import os
import sys
import threading
import time

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DEFAULT_LLM_MODEL = os.environ.get(
    "MOSS_LLM_MODEL", "mlx-community/Qwen3-1.7B-8bit")

MAX_BODY_BYTES = 2 * 1024 * 1024


class BusyError(Exception):
    pass


class SingleFlight:
    """One in-flight generation + bounded wait-queue (same pattern the TTS
    daemon uses): the hardware serialises the real compute, the HTTP layer
    admits clients up to the queue and answers 503 beyond it."""

    def __init__(self, queue_size=4, reserve_timeout=45.0):
        self.queue_size = queue_size
        self.reserve_timeout = reserve_timeout
        self._cond = threading.Condition()
        self.in_flight = 0
        self.queued = 0
        self.accepted = 0
        self.rejected = 0

    def acquire(self):
        if not self._reserve():
            raise BusyError("server is busy")
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
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
            # notify_all: a timed-out waiter may consume a plain notify()
            # without taking the slot, leaving the queue asleep up to
            # reserve_timeout while capacity is free.
            self._cond.notify_all()

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


class _MLXBackend:
    def __init__(self):
        import mlx_lm

        self._mlx_lm = mlx_lm

    def load(self, model_id, **kw):
        return self._mlx_lm.load(model_id)

    def chat(self, model, tok, messages, max_tokens, temp):
        from mlx_lm.sample_utils import make_sampler

        prompt = tok.apply_chat_template(
            messages, add_generation_prompt=True, enable_thinking=False)
        return self._mlx_lm.generate(
            model, tok, prompt=prompt, max_tokens=max_tokens, verbose=False,
            sampler=make_sampler(temp=temp))

    def chat_stream(self, model, tok, messages, max_tokens, temp):
        """Yield text DELTAS as tokens are generated (REALTIME FIX).

        mlx's stream_generate detokeniser already segments output, so each
        response.text is the new fragment only — no cumulative diffing needed.
        """
        from mlx_lm import stream_generate
        from mlx_lm.sample_utils import make_sampler

        prompt = tok.apply_chat_template(
            messages, add_generation_prompt=True, enable_thinking=False)
        for resp in stream_generate(
                model, tok, prompt=prompt, max_tokens=max_tokens,
                sampler=make_sampler(temp=temp)):
            if resp.text:
                yield resp.text


class _TransformersBackend:
    """CPU/GPU (non-Metal) backend used inside Docker. Slower than MLX, so
    the Docker profile is aimed at smaller models."""

    def __init__(self):
        import torch
        import transformers

        self._torch = torch
        self._transformers = transformers

    def load(self, model_id, **kw):
        tok = self._transformers.AutoTokenizer.from_pretrained(model_id)
        # NOTE: no device_map="cpu" — accelerate's per-layer hooks make CPU
        # inference ~10x slower; a plain load keeps everything on CPU and
        # lets torch use native GEMM kernels. bfloat16 halves memory vs fp32
        # with no accuracy loss on Qwen3 (and avoids fp16 overflow on CPU).
        model = self._transformers.AutoModelForCausalLM.from_pretrained(
            model_id, torch_dtype=self._torch.bfloat16).to("cpu").eval()
        return model, tok

    def _inputs(self, tok, messages):
        try:
            return tok.apply_chat_template(
                messages, add_generation_prompt=True,
                enable_thinking=False, return_dict=True,
                return_tensors="pt")
        except Exception:  # noqa: BLE001
            return tok.apply_chat_template(
                messages, add_generation_prompt=True, return_dict=True,
                return_tensors="pt")

    def chat(self, model, tok, messages, max_tokens, temp):
        inputs = self._inputs(tok, messages)
        out = model.generate(
            **inputs.to(model.device), max_new_tokens=max_tokens,
            do_sample=temp > 0, temperature=max(temp, 0.01))
        new_tokens = out[0][inputs["input_ids"].shape[-1]:]
        return tok.decode(new_tokens, skip_special_tokens=True)

    def chat_stream(self, model, tok, messages, max_tokens, temp):
        """Token-by-token deltas via generate(streamer). Tokens accumulate and
        are decoded cumulatively (single tokens decode unreliable for spaces),
        so each yielded delta is exactly the new visible text."""
        import queue as _queue

        out_q = _queue.Queue()

        class _DeltaStreamer:
            def put(self, value):
                out_q.put(("tok", value))

            def end(self):
                out_q.put(("end", None))

        streamer = _DeltaStreamer()
        inputs = self._inputs(tok, messages)
        gen = threading.Thread(
            target=lambda: model.generate(
                **inputs.to(model.device), max_new_tokens=max_tokens,
                do_sample=temp > 0, temperature=max(temp, 0.01),
                streamer=streamer),
            daemon=True)
        gen.start()
        ids = []
        prev = ""
        while True:
            kind, payload = out_q.get()
            if kind == "end":
                break
            piece = payload
            if hasattr(piece, "flatten"):
                piece = piece.flatten().tolist()
            ids.extend(int(t) for t in piece)
            text = tok.decode(ids, skip_special_tokens=True)
            delta = text[len(prev):]
            if delta:
                prev = text
                yield delta
        gen.join(timeout=10)


def make_backend(kind):
    if kind in ("mlx", "auto"):
        try:
            return _MLXBackend()
        except Exception as exc:  # noqa: BLE001
            if kind == "mlx":
                raise
            print(f"[llm-server] mlx unavailable ({exc}); "
                  "falling back to transformers", flush=True)
    return _TransformersBackend()


class LLMWorker:
    def __init__(self, model_id, max_tokens_cap=512):
        self.model_id = model_id
        self.max_tokens_cap = max_tokens_cap
        self._model = None
        self._tok = None
        self._lock = threading.Lock()
        self._backend = None
        self.backend_name = None
        self.ready = False
        self.error = None
        self.stats = {"chat": 0, "errors": 0, "total_ms": 0.0}
        self.slot = SingleFlight()

    def load(self):
        """Load the model in the background: HTTP serves immediately with
        ready=false so the health endpoint and upstream clients never wait on
        the (slowest) import; /chat answers 503 until loading finishes."""
        def _load():
            try:
                kind = os.environ.get("MOSS_LLM_BACKEND", "auto")
                self._backend = make_backend(kind)
                self.backend_name = self._backend.__class__.__name__
                model, tok = self._backend.load(self.model_id)
                self._model, self._tok = model, tok
                self.ready = True
                print(f"[llm-server] model ready ({self.model_id}) "
                      f"backend={self.backend_name}", flush=True)
            except Exception as exc:  # noqa: BLE001
                self.ready = False
                self.error = str(exc)
                print(f"[llm-server] model load failed: {exc}", flush=True)

        threading.Thread(target=_load, daemon=True).start()

    def chat(self, messages, max_tokens=100, temp=0.65):
        """Run one chat completion. Returns text or raises."""
        if not self.ready or self._model is None:
            raise RuntimeError(self.error or "model not ready")
        max_tokens = min(int(max_tokens or 100), self.max_tokens_cap)
        with self._lock:
            from time import time as _t

            start = _t()
            out = self._backend.chat(
                self._model, self._tok, messages, max_tokens, temp)
        self.stats["chat"] += 1
        self.stats["total_ms"] += (time.time() - start) * 1000
        return out

    def chat_stream(self, messages, max_tokens=100, temp=0.65):
        """Yield text deltas as the model generates them. Raises if not ready
        or the backend lacks streaming (caller falls back to chat())."""
        if not self.ready or self._model is None:
            raise RuntimeError(self.error or "model not ready")
        streamer = getattr(self._backend, "chat_stream", None)
        if streamer is None:
            raise RuntimeError("backend does not support streaming")
        max_tokens = min(int(max_tokens or 100), self.max_tokens_cap)
        # The model lock is held for the WHOLE generation: streaming a reply
        # still occupies the single GPU/CPU, so capacity stays 1 — we only
        # change WHEN the first text reaches the caller.
        with self._lock:
            yield from streamer(
                self._model, self._tok, messages, max_tokens, temp)
        self.stats["chat"] += 1


def build_handler(worker):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        timeout = 30

        def log_message(self, *args):
            pass

        def _json(self, obj, status=200):
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _busy(self):
            self.send_response(503)
            self.send_header("Content-Type", "application/json")
            self.send_header("Retry-After", "1")
            body = b'{"ok":false,"error":"server is busy"}'
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _body(self):
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = 0
            if length <= 0:
                return b""
            if length > MAX_BODY_BYTES:
                raise ValueError("body too large")
            return self.rfile.read(length)

        def do_GET(self):
            path = self.path.split("?")[0]
            if path in ("/health", "/healthz"):
                self._json({
                    # read.md rev-3 G4: identity contract — the supervisor
                    # refuses to adopt a port whose /health does not answer
                    # this service name + protocol_version.
                    "service": "mossvoice-llm",
                    "protocol_version": 1,
                    "ok": True,
                    "ready": worker.ready,
                    "model": worker.model_id,
                    "backend": worker.backend_name,
                    "error": worker.error,
                    "metrics": worker.slot.metrics(),
                    "stats": worker.stats,
                })
            else:
                self._json({"ok": False, "error": "not found"}, 404)

        def do_POST(self):
            path = self.path.split("?")[0]
            if path == "/chat":
                self._handle_chat()
            elif path == "/chat_stream":
                self._handle_chat_stream()
            elif path == "/shutdown":
                self._handle_shutdown()
            else:
                self._json({"ok": False, "error": "not found"}, 404)

        def _chat_payload(self):
            """Parse+validate a /chat[-style] body. Returns (messages,
            max_tokens, temp) or raises ValueError."""
            payload = json.loads(self._body().decode("utf-8") or "{}")
            messages = payload.get("messages")
            if not messages or not isinstance(messages, list) or not all(
                    isinstance(m, dict) and m.get("role")
                    and m.get("content") is not None
                    for m in messages):
                raise ValueError("messages: list of {role, content} required")
            return (messages, payload.get("max_tokens") or 100,
                    payload.get("temp") or 0.65)

        def _handle_chat(self):
            try:
                messages, max_tokens, temp = self._chat_payload()
            except ValueError as exc:
                self._json({"ok": False, "error": str(exc)}, 400)
                return
            except Exception as exc:  # noqa: BLE001
                self._json({"ok": False, "error": f"bad request: {exc}"}, 400)
                return
            try:
                with worker.slot.acquire():
                    text = worker.chat(messages, max_tokens=max_tokens, temp=temp)
                self._json({"ok": True, "text": text})
            except BusyError:
                self._busy()
            except Exception as exc:  # noqa: BLE001
                worker.stats["errors"] += 1
                self._json({"ok": False, "error": str(exc)}, 500)

        def _handle_chat_stream(self):
            """Token streaming endpoint (REALTIME FIX, Stage 5).

            Response body: a sequence of length-prefixed JSON frames
            (4-byte big-endian length + payload), the same wire format as
            tts_server /stream and call_agent /turn_stream:
                {"delta": "..."}                     per token burst
                {"done": true, "text": "<full>"}     final frame
            On failure before the first frame: single {"error": ...} frame.
            """
            try:
                messages, max_tokens, temp = self._chat_payload()
            except ValueError as exc:
                self._json({"ok": False, "error": str(exc)}, 400)
                return
            except Exception as exc:  # noqa: BLE001
                self._json({"ok": False, "error": f"bad request: {exc}"}, 400)
                return

            # Streaming holds the slot for the full generation (capacity=1),
            # but the RESPONSE starts immediately with 200 + chunked transfer
            # so the caller gets the first tokens while we still generate.
            try:
                slot = worker.slot.acquire()
            except BusyError:
                self._busy()
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()

            def write_frame(obj):
                payload = json.dumps(obj, ensure_ascii=False).encode("utf-8")
                frame = len(payload).to_bytes(4, "big") + payload
                try:
                    self.wfile.write(b"%X\r\n" % len(frame))
                    self.wfile.write(frame)
                    self.wfile.write(b"\r\n")
                    self.wfile.flush()
                    return True
                except Exception:  # noqa: BLE001  client went away
                    return False

            full = []
            try:
                for delta in worker.chat_stream(
                        messages, max_tokens=max_tokens, temp=temp):
                    full.append(delta)
                    if not write_frame({"delta": delta}):
                        return
                write_frame({"done": True, "text": "".join(full), "ok": True})
            except Exception as exc:  # noqa: BLE001
                worker.stats["errors"] += 1
                write_frame({"error": str(exc), "done": True,
                             "text": "".join(full)})
            finally:
                try:
                    self.wfile.write(b"0\r\n\r\n")
                    self.wfile.flush()
                except Exception:  # noqa: BLE001
                    pass
                slot.__exit__(None, None, None)

        def _handle_shutdown(self):
            peer = self.client_address[0] if self.client_address else ""
            if peer not in ("127.0.0.1", "::1", "localhost"):
                self._json({"ok": False, "error": "forbidden"}, 403)
                return
            self._json({"ok": True, "shutting_down": True})
            threading.Thread(target=self.server.shutdown, daemon=True).start()

    return Handler


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=int(os.environ.get("MOSS_LLM_PORT", "9500")))
    ap.add_argument("--host", default=os.environ.get("MOSS_LLM_HOST", "127.0.0.1"),
                    help="bind address; loopback by default, 0.0.0.0 inside "
                         "the Docker network (set MOSS_LLM_HOST=0.0.0.0)")
    ap.add_argument("--model", default=DEFAULT_LLM_MODEL)
    ap.add_argument("--queue-size", type=int,
                    default=int(os.environ.get("MOSS_LLM_QUEUE", "4")))
    ap.add_argument("--max-tokens-cap", type=int, default=512)
    args = ap.parse_args()

    worker = LLMWorker(args.model, max_tokens_cap=args.max_tokens_cap)
    worker.slot = SingleFlight(queue_size=args.queue_size)
    worker.load()

    class QuietHTTPServer(ThreadingHTTPServer):
        daemon_threads = True

        def handle_error(self, request, client_address):
            exc = sys.exc_info()[1]
            if isinstance(exc, (ConnectionResetError, BrokenPipeError,
                                ConnectionAbortedError, TimeoutError)):
                return
            import traceback

            traceback.print_exc(limit=5)

    httpd = QuietHTTPServer((args.host, args.port), build_handler(worker))
    print(f"[llm-server] listening on {args.host}:{args.port} ready={worker.ready}",
          flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
