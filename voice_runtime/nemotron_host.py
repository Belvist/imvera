#!/usr/bin/env python3
"""MossVoice Nemotron 3.5 ASR Streaming host service.

Runs on the Mac (Apple Silicon) next to FreeSWITCH. Wraps
``nvidia/nemotron-3.5-asr-streaming-0.6b`` via Transformers and
exposes the same HTTP contract as ``voice_runtime/stt_host.py`` so
``CloudSTTAdapter`` / ``StreamingSTT`` work unchanged.

Endpoints
---------
GET  /ready               -> {"ready": bool}
POST /transcribe          multipart/form-data; file=turn.wav
                            -> {"text": str, "language": "ru",
                                "dur_s": float, "latency_ms": int}
POST /stream              multipart/form-data; file=chunk.wav
                            -> {"text": str, "final": bool}

Run:
    python3 voice_runtime/nemotron_host.py [--port 9710]

Install (once):
    pip install transformers accelerate soundfile numpy
    huggingface-cli download nvidia/nemotron-3.5-asr-streaming-0.6b
"""
import argparse
import io
import json
import os
import time
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST = "127.0.0.1"
DEFAULT_PORT = 9710
MODEL_ID = "nvidia/nemotron-3.5-asr-streaming-0.6b"
MAX_BODY = 50 * 1024 * 1024
BOUNDARY = b"mossnemotron"

_model = None
_processor = None
_warm = False
_warm_error = None


def _load():
    global _model, _processor, _warm, _warm_error
    if _model is not None or _warm_error is not None:
        return
    try:
        import transformers
        from transformers import Nemotron3_5AsrForRNNT, \
            Nemotron3_5AsrProcessor
        import torch  # noqa: F811
        print("[nemotron] loading %s ..." % MODEL_ID,
              flush=True)
        _processor = Nemotron3_5AsrProcessor.from_pretrained(
            MODEL_ID)
        _model = Nemotron3_5AsrForRNNT.from_pretrained(
            MODEL_ID, torch_dtype=torch.float16)
        device = "cuda" if torch.cuda.is_available() else "cpu"
        _model = _model.to(device)
        _model.eval()
        _warm = True
        print("[nemotron] ready on %s" % device, flush=True)
    except Exception as e:
        err = str(e)
        if "nemotron3_5_asr" in err or \
                "Unrecognized configuration class" in err:
            _warm_error = ("Nemotron ASR needs a Transformers "
                             "version that registers the "
                             "nemotron3_5_asr architecture. "
                             "Current: %s. Fix: pip install "
                             "transformers>=5.0 in a dedicated "
                             "env, or use NVIDIA's nemotron-asr "
                             "package." % transformers.__version__)
        else:
            _warm_error = err
        print("[nemotron] load failed: %s" % _warm_error,
              flush=True)


def _transcribe(wav_bytes):
    if _model is None:
        raise RuntimeError("model not loaded")
    with wave.open(io.BytesIO(wav_bytes), "rb") as w:
        rate = w.getframerate() or 16000
        frames = w.getnframes()
        raw = w.readframes(frames)
    import numpy as np
    samples = np.frombuffer(raw, dtype=np.int16).astype(
        np.float32) / 32768.0
    if rate != 16000:
        import librosa
        samples = librosa.resample(
            samples, orig_sr=rate, target_sr=16000)
        rate = 16000
    if _processor is None:
        raise RuntimeError("processor not loaded")
    inputs = _processor(samples, sampling_rate=rate,
                        return_tensors="pt")
    import torch  # noqa: F811
    device = next(_model.parameters()).device
    inputs = {
        k: v.to(device, dtype=torch.float16)
          if hasattr(v, "to") and v.is_floating_point() else
          v.to(device) if hasattr(v, "to") else v
        for k, v in inputs.items()}
    with torch.no_grad():
        generated = _model.generate(**inputs)
    text = _processor.batch_decode(
        generated.sequences, skip_special_tokens=True)[0]
    dur_s = float(len(samples)) / rate
    return {"text": text.strip(), "dur_s": round(dur_s, 3)}


class _Handler(BaseHTTPRequestHandler):
    server_version = "MossNemotron/0.1"

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

    def do_GET(self):
        if self.path == "/ready":
            self._json(200, {"ready": _warm,
                             "error": (str(_warm_error)
                                       if _warm_error else None)})
            return
        self._json(404, {"error": "not found"})

    def _read_multipart(self):
        ctype = self.headers.get("Content-Type", "")
        if not ctype.startswith("multipart/form-data"):
            return None
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > MAX_BODY:
            return None
        body = self.rfile.read(length)
        hdr_end = body.find(b"\r\n\r\n")
        if hdr_end < 0:
            return None
        data = body[hdr_end + 4:]
        end_marker = b"\r\n--" + BOUNDARY
        if data.endswith(end_marker):
            data = data[:-len(end_marker)]
        elif data.endswith(b"--" + BOUNDARY):
            data = data[:-len(b"--" + BOUNDARY)]
        return data

    def do_POST(self):
        if self.path == "/transcribe":
            data = self._read_multipart()
            if data is None:
                self._json(400, {"error": "multipart/form-data "
                                  "required"})
                return
            t0 = time.time()
            try:
                res = _transcribe(data)
            except Exception as e:
                self._json(500, {"error": str(e)[:200]})
                return
            res["latency_ms"] = int((time.time() - t0) * 1000)
            res["language"] = "ru"
            self._json(200, res)
            return
        if self.path == "/stream":
            data = self._read_multipart()
            if data is None:
                self._json(400, {"error": "multipart/form-data "
                                  "required"})
                return
            t0 = time.time()
            try:
                res = _transcribe(data)
            except Exception as e:
                self._json(500, {"error": str(e)[:200]})
                return
            res["latency_ms"] = int((time.time() - t0) * 1000)
            res["final"] = True
            self._json(200, res)
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
    print("MossNemotron listening on %s:%d (%s)"
          % (args.host, args.port, MODEL_ID), flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()