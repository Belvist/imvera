#!/usr/bin/env python3
"""MossVoice Qwen3-TTS 12Hz 0.6B Base host service.

Runs on the Mac (Apple Silicon) next to FreeSWITCH. Wraps
``Qwen/Qwen3-TTS-12Hz-0.6B-Base`` via ``qwen-tts`` / Transformers
and exposes ``POST /synthesize`` + ``POST /stream`` so
``CloudTTSAdapter`` works unchanged.

Endpoints
---------
GET  /ready               -> {"ready": bool}
POST /synthesize          {"text": str, "voice_id": str}
                            -> {"wav_b64": str, "latency_ms": int}
POST /stream              {"text": str, "voice_id": str,
                            "stream_id": str}
                            -> {"frames": [{"i": n,
                                            "wav_b64": str,
                                            "done": bool}]}

Run:
    python3 voice_runtime/qwen3_tts_host.py [--port 9711]

Install (once):
    pip install qwen-tts
    huggingface-cli download Qwen/Qwen3-TTS-12Hz-0.6B-Base
"""
import argparse
import base64
import json
import os
import struct
import time
import wave
from io import BytesIO
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST = "127.0.0.1"
DEFAULT_PORT = 9711
MODEL_ID = "Qwen/Qwen3-TTS-12Hz-0.6B-Base"
MAX_BODY = 50 * 1024 * 1024
PCM_RATE = 22050
PCM_WIDTH = 2

import numpy as np

_model = None
_ready = False
_ready_error = None


def _load():
    global _model, _ready, _ready_error
    if _model is not None or _ready_error is not None:
        return
    try:
        from qwen_tts import Qwen3TTS
        print("[qwen3-tts] loading %s ..." % MODEL_ID,
              flush=True)
        _model = Qwen3TTS()
        _ready = True
        print("[qwen3-tts] ready", flush=True)
    except ImportError:
        _ready_error = ("qwen-tts not installed: "
                         "pip install qwen-tts")
        print("[qwen3-tts] %s" % _ready_error, flush=True)
    except Exception as e:
        _ready_error = str(e)
        print("[qwen3-tts] load failed: %s" % e,
              flush=True)


def _synthesize(text, voice_id):
    if _model is None:
        raise RuntimeError("model not loaded")
    t0 = time.time()
    audio = _model.generate(text, voice_id=voice_id)
    latency_ms = int((time.time() - t0) * 1000)
    if isinstance(audio, list):
        samples = audio
    elif hasattr(audio, "numpy"):
        samples = audio.numpy()
    else:
        samples = audio
    if samples.dtype != np.int16:
        if samples.dtype == np.float32:
            samples = (samples * 32767).astype(np.int16)
        else:
            samples = samples.astype(np.int16)
    buf = BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(PCM_WIDTH)
        w.setframerate(PCM_RATE)
        w.writeframes(samples.tobytes())
    wav_bytes = buf.getvalue()
    return base64.b64encode(wav_bytes).decode("ascii"), \
        latency_ms


def _stream_frames(text, voice_id):
    """Yield frame dicts for a synthesis."""
    wav_b64, latency_ms = _synthesize(text, voice_id)
    # Split into ~20ms frames (~882 samples at 22050 Hz).
    raw = base64.b64decode(wav_b64)
    n_frames = max(1, len(raw) // (PCM_RATE * PCM_WIDTH))
    chunk_size = max(1, len(raw) // n_frames)
    i = 0
    while i < len(raw):
        chunk = raw[i:i + chunk_size]
        yield {"i": i // chunk_size,
               "wav_b64": base64.b64encode(chunk).decode("ascii"),
               "done": False}
        i += chunk_size
    yield {"done": True}


class _Handler(BaseHTTPRequestHandler):
    server_version = "MossQwen3TTS/0.1"

    def log_message(self, *args):
        pass

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type",
                          "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > MAX_BODY:
            return None
        return self.rfile.read(length)

    def do_GET(self):
        if self.path == "/ready":
            self._json(200, {"ready": _ready,
                             "error": (str(_ready_error)
                                       if _ready_error else None)})
            return
        self._json(404, {"error": "not found"})

    def do_POST(self):
        if self.path == "/synthesize":
            body = self._read_body()
            if body is None:
                self._json(413, {"error": "body too large"})
                return
            try:
                req = json.loads(body)
            except ValueError as e:
                self._json(400, {"error": str(e)})
                return
            text = req.get("text", "")
            voice_id = req.get("voice_id", "vera")
            try:
                wav_b64, latency_ms = \
                    _synthesize(text, voice_id)
            except Exception as e:
                self._json(500, {"error": str(e)[:200]})
                return
            self._json(200, {"wav_b64": wav_b64,
                             "latency_ms": latency_ms})
            return
        if self.path == "/stream":
            body = self._read_body()
            if body is None:
                self._json(413, {"error": "body too large"})
                return
            try:
                req = json.loads(body)
            except ValueError as e:
                self._json(400, {"error": str(e)})
                return
            text = req.get("text", "")
            voice_id = req.get("voice_id", "vera")
            stream_id = req.get("stream_id", "")
            try:
                frames = list(
                    _stream_frames(text, voice_id))
            except Exception as e:
                self._json(500, {"error": str(e)[:200]})
                return
            self._json(200, {"frames": frames})
            return
        self._json(404, {"error": "not found"})


def main():
    global args
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--host", default=HOST)
    args = p.parse_args()
    _load()
    srv = ThreadingHTTPServer((args.host, args.port), _Handler)
    print("MossQwen3TTS listening on %s:%d (%s)"
          % (args.host, args.port, MODEL_ID), flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()