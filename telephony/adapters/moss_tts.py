"""MOSS TTS daemon client (talks to runtime/scripts/tts_server.py over HTTP)."""

import base64
import http.client
import json
import os
import urllib.request


class TTSClient:
    def __init__(self, ref_paths=None, reference_text="", port_file=None, port=None,
                 inference_steps=12, style_enabled=True, host=None):
        self.refs = ref_paths or []
        self.reference_text = reference_text
        self.port_file = port_file
        self._fixed_port = port
        # Docker: the TTS daemon lives on another host (the "voice" service).
        # Default is loopback so the all-in-one macOS deployment is unchanged.
        self.host = (host or os.environ.get("MOSS_TTS_HOST", "")
                     or "127.0.0.1")
        self.port = None
        self.inference_steps = inference_steps
        self.style_enabled = style_enabled

    def refresh(self):
        if self._fixed_port:
            self.port = self._fixed_port
            return
        if not self.port_file:
            self.port = None
            return
        try:
            with open(self.port_file) as f:
                self.port = int(f.read().strip())
        except Exception:
            self.port = None

    def health(self):
        self.refresh()
        if not self.port:
            return False, "TTS-демон не запущен (порт не найден)"
        try:
            req = urllib.request.Request(f"http://{self.host}:{self.port}/health")
            with urllib.request.urlopen(req, timeout=5) as r:
                obj = json.loads(r.read().decode())
            return bool(obj.get("ready")), str(obj.get("error") or "")
        except Exception as e:
            return False, str(e)

    def ready(self):
        ok, _ = self.health()
        return ok

    def generate(self, text):
        self.refresh()
        if not self.port:
            return None
        payload = {
            "text": text,
            "refs": self.refs,
            "reference_text": self.reference_text,
            "max_new_tokens": 2048,
            "cfg_value": 1.2,
            "inference_steps": self.inference_steps,
            "style_enabled": self.style_enabled,
        }
        try:
            req = urllib.request.Request(
                f"http://{self.host}:{self.port}/generate",
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=600) as r:
                obj = json.loads(r.read().decode())
        except Exception as e:
            print(f"[call-agent] TTS error: {e}", flush=True)
            return None
        if not obj.get("ok"):
            return None
        return base64.b64decode(obj["wav_b64"])

    def stream(self, text, cancel_event=None, stream_id=None):
        """Yield TTS frames (dicts with wav_b64) as they are produced.

        Reads the TTS daemon's /stream endpoint frame-by-frame using the
        length-prefixed wire format (4-byte big-endian length + JSON).
        ``cancel_event`` (threading.Event) aborts generation and stops yielding.
        ``stream_id`` (AUDIT FIX) is passed to the TTS daemon so a separate
        /stream-cancel call can abort generation *server-side* instead of the
        client just dropping the socket.
        """
        self.refresh()
        if not self.port:
            return
        payload = {
            "text": text,
            "refs": self.refs,
            "reference_text": self.reference_text,
            "max_new_tokens": 2048,
            "cfg_value": 1.2,
            "inference_steps": self.inference_steps,
            "style_enabled": self.style_enabled,
        }
        if stream_id:
            payload["stream_id"] = stream_id
        conn = None
        try:
            conn = http.client.HTTPConnection(self.host, self.port, timeout=600)
            conn.request(
                "POST", "/stream",
                body=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
            )
            resp = conn.getresponse()
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
                    frame_payload = buf[4:4 + n]
                    buf = buf[4 + n:]
                    frame = json.loads(frame_payload.decode("utf-8"))
                    yield frame
                    if frame.get("done"):
                        return
        except Exception as e:
            print(f"[call-agent] TTS stream error: {e}", flush=True)
        finally:
            if conn is not None:
                conn.close()

    def cancel_stream_by_id(self, stream_id):
        """Ask the TTS daemon to abort the generation for ``stream_id``.

        This is the server-side half of barge-in cancellation: it stops the
        model work, not just the delivery. Failures are logged and swallowed —
        the generation will finish either way, we only lose latency.
        """
        self.refresh()
        if not self.port or not stream_id:
            return
        try:
            req = urllib.request.Request(
                f"http://{self.host}:{self.port}/stream-cancel",
                data=json.dumps({"stream_id": stream_id}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as r:
                r.read()
        except Exception as e:  # noqa: BLE001
            print(f"[call-agent] TTS stream-cancel error: {e}", flush=True)