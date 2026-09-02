#!/usr/bin/env python3
"""MossVoice Qwen3-TTS 12Hz 0.6B Base host service.

Runs on the Mac (Apple Silicon) next to FreeSWITCH. Wraps
``Qwen/Qwen3-TTS-12Hz-0.6B-Base`` via ``qwen-tts`` and exposes
``POST /synthesize`` + ``POST /stream`` so ``CloudTTSAdapter``
works unchanged.

Endpoints
---------
GET  /ready               -> {"ready": bool}
POST /synthesize          {"text": str, "voice_id": str}
                            -> {"wav_b64": str, "latency_ms": int}
POST /stream              {"text": str, "voice_id": str}
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
import numpy as np
import time
import wave
from io import BytesIO
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST = "127.0.0.1"
DEFAULT_PORT = 9711
MODEL_ID = "Qwen/Qwen3-TTS-12Hz-0.6B-Base"
MAX_BODY = 50 * 1024 * 1024
PCM_RATE = 24000
PCM_WIDTH = 2
REF_AUDIO_PATH = "/tmp/mossvoice/ref_vera.wav"

_model = None
_ref_audio = None
_ref_sr = None
_ready = False
_ready_error = None


def _np_to_wav_b64(samples, rate=PCM_RATE):
    arr = np.asarray(samples, dtype=np.int16)
    buf = BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(PCM_WIDTH)
        w.setframerate(rate)
        w.writeframes(arr.tobytes())
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _load():
    global _model, _ref_audio, _ref_sr, _ready, _ready_error
    if _model is not None or _ready_error is not None:
        return
    try:
        import wave as _w
        from qwen_tts import Qwen3TTSModel
        print("[qwen3-tts] loading %s (cpu, float32) ..."
              % MODEL_ID, flush=True)
        _model = Qwen3TTSModel.from_pretrained(MODEL_ID)
        print("[qwen3-tts] on cpu", flush=True)
        if os.path.exists(REF_AUDIO_PATH):
            with _w.open(REF_AUDIO_PATH, "rb") as wf:
                raw = wf.readframes(wf.getnframes())
                _ref_sr = wf.getframerate()
            _ref_audio = np.frombuffer(
                raw, dtype=np.int16).astype(np.float32) / 32768.0
            print("[qwen3-tts] ref audio: %s (%dHz)"
                  % (REF_AUDIO_PATH, _ref_sr), flush=True)
        else:
            _ref_audio = np.zeros(16000, dtype=np.float32)
            _ref_sr = 16000
            print("[qwen3-tts] no ref audio, using silence",
                  flush=True)
        _ready = True
        print("[qwen3-tts] ready", flush=True)
    except ImportError:
        _ready_error = "qwen-tts not installed: pip install qwen-tts"
        print("[qwen3-tts] %s" % _ready_error, flush=True)
    except Exception as e:
        _ready_error = str(e)
        print("[qwen3-tts] load failed: %s" % e,
              flush=True)


def _synthesize(text, voice_id):
    if _model is None:
        raise RuntimeError("model not loaded")
    t0 = time.time()
    audios, sr = _model.generate_voice_clone(
        text=[text], language=["russian"],
        ref_audio=(_ref_audio, _ref_sr),
        ref_text="Здравствуйте, я Вера. Как ваши дела?",
        non_streaming_mode=True)
    latency_ms = int((time.time() - t0) * 1000)
    samples = audios[0]
    if isinstance(samples, np.ndarray):
        if samples.dtype == np.float32:
            samples = (samples * 32767).astype(np.int16)
        else:
            samples = samples.astype(np.int16)
    else:
        samples = np.asarray(samples, dtype=np.int16)
    wav_b64 = _np_to_wav_b64(samples, sr)
    return wav_b64, latency_ms


def _stream_frames(text, voice_id):
    wav_b64, _ = _synthesize(text, voice_id)
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
                wav_b64, latency_ms = _synthesize(text, voice_id)
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
            try:
                frames = list(_stream_frames(text, voice_id))
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