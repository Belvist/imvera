#!/usr/bin/env python3
"""MossVoice STT host service — Qwen3-ASR on Apple Silicon (MLX).

The telephony container runs whisper-small (CTranslate2/faster-whisper),
which is measurably weak on real Russian phone audio ("назрение" for
"настроение"). Qwen3-ASR-0.6B (Apache-2.0, commercial OK) is markedly more
accurate AND faster on this Mac (MLX/Metal, measured 0.2-1.8s/file vs
whisper-small's ~2-3s), but it is MLX-only — it cannot run inside the Linux
Docker container. So it lives here, as a host-side HTTP service next to
FreeSWITCH and the VoiceRuntime (the same host-side pattern).

Wire contract (one endpoint, same shape the telephony STT adapter expects):

    POST /transcribe                         multipart: file=*.wav
        -> {"text": str, "language": "ru", "dur_s": float, "latency_ms": int}
    200 on success, 400 on no/empty text, 503 during model warm-up, 500 on
    inference error. Plain JSON, no secrets, loopback-only.

Run: python3 voice_runtime/stt_host.py [--port 9705] [--model ...]
launchd: com.mossvoice.stt.plist (KeepAlive) — port 9705.
"""
import argparse
import json
import os
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST = "127.0.0.1"
DEFAULT_PORT = 9705
DEFAULT_MODEL = "mlx-community/Qwen3-ASR-0.6B-4bit"
MAX_BODY = 50 * 1024 * 1024

_model = None
_model_lock = threading.Lock()
_warm = False


def _load_model(model_id):
    """Load Qwen3-ASR once (thread-safe, lazy)."""
    global _model, _warm
    with _model_lock:
        if _model is not None:
            return _model
        from mlx_audio.stt import load
        _model = load(model_id)
        _warm = True
        return _model


def _transcribe(path, model_id, language="ru"):
    """Return {"text": ..., "latency_ms": ...}; raises on failure."""
    m = _load_model(model_id)
    # The MLX generate() is not guaranteed thread-safe across concurrent
    # calls on one instance — serialize inference behind the same lock.
    with _model_lock:
        t0 = time.time()
        # follow the mlx_audio generate signature (returns STTOutput)
        r = m.generate(path, language=language)
        txt = getattr(r, "text", "") or ""
        latency_ms = int((time.time() - t0) * 1000)
    return {"text": txt.strip(), "latency_ms": latency_ms}


class _Handler(BaseHTTPRequestHandler):
    server_version = "MossSTT/0.1"
    # mlx_audio logs banners on import; silence request logging noise.

    def log_message(self, *args):
        pass

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/ready":
            self._json(200, {"ready": _warm, "model": args.model})
            return
        self._json(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/transcribe":
            self._json(404, {"error": "not found"})
            return
        ctype = self.headers.get("Content-Type", "")
        name, params = self._multipart_params(ctype)
        if name != "multipart/form-data":
            self._json(415, {"error": "multipart/form-data required"})
            return
        boundary = params.get("boundary", "").encode("utf-8")
        body = self._read_body()
        if body is None:
            self._json(413, {"error": "body too large"})
            return
        part = self._extract_file(body, boundary)
        if part is None:
            self._json(400, {"error": "no file part"})
            return
        payload, fname = part
        suffix = ".wav" if fname.lower().endswith(".wav") else ".bin"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            f.write(payload)
            tmp = f.name
        try:
            res = _transcribe(tmp, args.model)
        except Exception as e:  # noqa: BLE001
            try:
                os.unlink(tmp)
            finally:
                pass
            self._json(500, {"error": str(e)[:200]})
            return
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass
        if not res.get("text"):
            self._json(400, {"error": "no speech recognized", **res})
            return
        # duration of recognized payload (approx: 16k mono -> /16000)
        dur_s = round(len(payload) / (16000 * 2), 2)
        self._json(200, {"text": res["text"], "language": "ru",
                         "dur_s": dur_s, "latency_ms": res["latency_ms"]})

    # ---- helpers -----------------------------------------------------
    def _read_body(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > MAX_BODY:
            return None
        return self.rfile.read(length)

    @staticmethod
    def _multipart_params(ctype):
        parts = ctype.split(";")
        name = parts[0].strip()
        params = {}
        for p in parts[1:]:
            if "=" in p:
                k, _, v = p.partition("=")
                params[k.strip()] = v.strip().strip('"')
        return name, params

    def _extract_file(self, body, boundary):
        """Return (payload_bytes, filename) of the first named file part."""
        if not boundary:
            return None
        delim = b"--" + boundary
        chunks = body.split(delim)
        for ch in chunks:
            if not ch or ch in (b"--", b"--\r\n"):
                continue
            # header block ends with blank line (\r\n\r\n)
            hdr_end = ch.find(b"\r\n\r\n")
            if hdr_end < 0:
                continue
            headers = ch[:hdr_end].decode("utf-8", errors="replace")
            if "filename=" not in headers:
                continue
            data = ch[hdr_end + 4:]
            if data.endswith(b"\r\n"):
                data = data[:-2]
            fname = ""
            marker = "filename=\""
            if marker in headers:
                rest = headers.split(marker, 1)[1]
                fname = rest.split('"', 1)[0]
            return data, fname
        return None


def main():
    global args
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--host", default=HOST)
    args = p.parse_args()
    srv = ThreadingHTTPServer((args.host, args.port), _Handler)
    # warm the model at boot so the first phone turn isn't slow
    try:
        t = threading.Thread(target=_load_model, args=(args.model,),
                             daemon=True)
        t.start()
    except Exception as e:  # noqa: BLE001
        print("warm-up failed:", e, file=sys.stderr, flush=True)
    print("MossSTT listening on %s:%d (%s)"
          % (args.host, args.port, args.model), flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()