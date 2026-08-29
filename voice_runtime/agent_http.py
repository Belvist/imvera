"""Thin HTTP client for the telephony agent (call_agent.py :9400).

The VoiceRuntime reuses the legacy agent's HTTP contract unchanged:
  * POST /calls                          -> create isolated call session
  * POST /say                            -> TTS a line, get wav_path
  * POST /calls/<id>/turn_stream         -> STT+LLM+TTS chunked reply (bg)
  * POST /calls/<id>/stream-cancel       -> barge-in: cancel + generation++
  * POST /calls/<id>/end                 -> finalize (state kept for TTL)
  * GET  /calls                          -> list (used by the loopback test)

`turn_stream` is posted in a background thread exactly like the Lua path and
the runtime consumes the reply only through the segment_dir / done.json
contract — the chunked frame stream is not parsed on the hot path.

CONTRACT FIX (2026-08-29, FIXES_PLAN P2): the server answers /turn_stream as
`application/octet-stream` with length-prefixed JSON frames inside an HTTP
chunked body. Treating it as one JSON document (the old `_json`) made EVERY
successful turn log as "bad JSON FAIL" and made real HTTP rejections
(429 busy / 404 / timeout) indistinguishable — a wedged `streaming` flag on
the session. `_stream_post` now:
  * reads the chunked body as opaque bytes (no JSON parse on the hot path),
  * distinguishes 200 (success) from 4xx/5xx (AgentError with the server's
    error body) and from a mid-stream disconnect.
"""
import json
import os
import threading
import urllib.error
import urllib.request

AGENT_HOST = os.environ.get("MOSS_AGENT_HOST", "127.0.0.1")
AGENT_PORT = int(os.environ.get("MOSS_AGENT_PORT", "9400"))


class AgentError(RuntimeError):
    pass


class AgentClient:
    def __init__(self, host=AGENT_HOST, port=AGENT_PORT, timeout=30):
        self.base = "http://%s:%d" % (host, port)
        self.timeout = timeout

    def _request(self, method, path, body=None, timeout=None):
        data = None
        headers = {}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self.base + path, data=data,
                                     headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=timeout or self.timeout) as r:
            return r.read().decode("utf-8", errors="replace")

    def _json(self, method, path, body=None, timeout=None):
        try:
            text = self._request(method, path, body, timeout)
        except Exception as e:  # noqa: BLE001
            raise AgentError("%s %s: %s" % (method, path, e))
        try:
            return json.loads(text)
        except ValueError:
            raise AgentError("bad JSON from %s: %r" % (path, text[:120]))

    def _stream_post(self, path, body, timeout=None):
        """POST returning a length-prefixed JSON frame stream (200).

        Reads the whole body (HTTP chunking is unwrapped by http.client);
        does NOT parse frames on the hot path — only the HTTP status decides
        success. 4xx/5xx carry the server's `{"ok": false, "error": ...}`
        body; a mid-stream disconnect surfaces as an AgentError."""
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(self.base + path, data=data,
                                     headers={"Content-Type":
                                              "application/json"},
                                     method="POST")
        try:
            with urllib.request.urlopen(
                    req, timeout=timeout or self.timeout) as r:
                status = r.getcode()
                if status != 200:
                    raise AgentError("turn_stream HTTP %d: %s"
                                     % (status, r.read().decode(
                                         "utf-8", errors="replace")[:200]))
                r.read()  # drain; success == 200
        except urllib.error.HTTPError as e:
            raise AgentError("turn_stream HTTP %d: %s"
                             % (e.code, e.read().decode(
                                 "utf-8", errors="replace")[:200]))
        except Exception as e:  # noqa: BLE001
            raise AgentError("turn_stream %s: %s" % (path, e))

    # ---- endpoints ------------------------------------------------------
    def create_call(self, payload=None):
        obj = self._json("POST", "/calls", payload or {})
        call_id = obj.get("call_id") or ""
        return call_id if call_id.strip() else None

    def list_calls(self):
        return self._json("GET", "/calls", None) or []

    def say(self, text):
        obj = self._json("POST", "/say", {"text": text})
        return obj.get("wav_path")

    def stream_cancel(self, call_id):
        return self._json("POST", "/calls/%s/stream-cancel" % call_id, {},
                          timeout=10)

    def end_call(self, call_id):
        return self._json("POST", "/calls/%s/end" % call_id, {}, timeout=10)

    def health(self, timeout=4):
        try:
            obj = self._json("GET", "/ready", None, timeout=timeout)
            return bool(obj.get("ready"))
        except AgentError:
            return False

    def turn_stream(self, call_id, audio_paths, segment_dir, on_done,
                    timeout=60):
        """Post a streaming turn in background (never blocks the VAD loop)."""
        def run():
            try:
                self._stream_post(
                    "/calls/%s/turn_stream" % call_id,
                    {"audio": audio_paths, "segment_dir": segment_dir},
                    timeout=timeout)
                on_done(True, "")
            except AgentError as e:
                on_done(False, str(e))
        threading.Thread(target=run, name="turn-%s" % call_id[-6:],
                         daemon=True).start()