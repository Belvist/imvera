"""LLM client (Qwen3 via mlx_lm) for VERA's live replies.

Prefers the dedicated answer-generation daemon (llm_server.py, port 9500)
over HTTP; falls back to loading the model in-process; any failure returns
None so the dialogue layer degrades to scripted phrases. The call never
stalls when the LLM is unavailable.
"""

import http.client
import json
import os
import re
import threading
import time
import urllib.parse
import urllib.request

from core.dialogue import VERA_LLM_ID, VERA_LLM_URL, _clean_llm


class LLMClient:
    """Qwen3 via mlx_lm for VERA's live replies.

    Lazily loaded ONE copy for the whole daemon (singleton), serialised with a
    lock because several calls may talk concurrently. Any failure returns None —
    the caller falls back to the scripted canned phrase, so the call never
    stalls when the LLM is unavailable.
    """

    _instance = None
    _instance_lock = threading.Lock()

    @classmethod
    def get(cls):
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self):
        self._model = None
        self._tok = None
        self._gen_lock = threading.Lock()
        self._loaded = False
        self._failed = False
        # Circuit breaker for the remote llm-server: after 3 consecutive
        # failures we stop probing it for 60 s and fall back to in-process.
        self._remote_failures = 0
        self._remote_down_until = 0.0
        # How long to wait at boot for the llm-server to finish loading
        # before loading a second model copy in-process.
        self._remote_wait = float(os.environ.get("MOSS_LLM_BOOT_WAIT", "60"))
        # "openai" = the remote speaks the OpenAI /v1/chat/completions
        # protocol (llama.cpp llama-server in Docker); "native" (default) =
        # our llm_server.py daemon with /chat + length-prefixed /chat_stream.
        self._openai = (
            os.environ.get("MOSS_LLM_PROTOCOL", "").strip().lower() == "openai"
        )
        # ARCHITECTURE 2026-08-27: the orchestrator must NEVER load a heavy
        # model into its own process. An incident that downs the llm-server is
        # exactly when loading several GB of MLX weights in-process would OOM
        # or CPU-thrash the live voice process. In-process generation is now
        # DISABLED by default: the cascade is only remote/cloud -> scripted.
        # It can be re-enabled for staging debug only via
        # MOSS_LLM_ALLOW_IN_PROCESS=1 (never in production).
        self._allow_in_process = (
            os.environ.get("MOSS_LLM_ALLOW_IN_PROCESS", "").strip().lower()
            in ("1", "true", "yes")
        )

    def _ensure(self):
        return self._ensure_local()

    def _ensure_local(self):
        # ARCHITECTURE 2026-08-27: by default the orchestrator never loads a
        # model in-process. Only staging with MOSS_LLM_ALLOW_IN_PROCESS=1 opts
        # back in; production keeps the realtime process light and answers with
        # the scripted fallback when the remote/cloud LLM is unavailable.
        if not self._allow_in_process:
            self._failed = True
            return False
        if self._loaded or self._failed:
            return self._loaded
        with self._gen_lock:
            if self._loaded or self._failed:
                return self._loaded
            try:
                from mlx_lm import load as mlx_load
                self._model, self._tok = mlx_load(VERA_LLM_ID)
                self._loaded = True
                print(f"[call-agent] LLM ready in-process ({VERA_LLM_ID})", flush=True)
            except Exception as e:  # noqa: BLE001
                print(f"[call-agent] LLM unavailable ({e}); scripted replies "
                      "only", flush=True)
                self._failed = True
                self._model = None
        return self._loaded

    def remote_ready(self, timeout=3.0):
        """Wait for the dedicated answer-generation daemon.

        If the daemon answers /health (even while its model is still loading)
        we wait up to ``wait_up`` for ready=True instead of loading a SECOND
        copy of the model in-process (RAM). If the daemon does not answer at
        all we give up fast; in-process loading is staging-only
        (MOSS_LLM_ALLOW_IN_PROCESS=1), otherwise replies fall back to the
        scripted phrase.
        """
        deadline = time.time() + self._remote_wait
        while time.time() < deadline:
            reachable = False
            try:
                req = urllib.request.Request(VERA_LLM_URL.strip("/") + "/health")
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    obj = json.loads(r.read().decode())
                reachable = True
                # Native llm_server reports {"ready": true}; llama.cpp
                # llama-server reports {"status": "ok"} — both mean "up".
                if obj.get("ready") or obj.get("status") == "ok":
                    self._remote_failures = 0
                    self._remote_down_until = 0.0
                    return True
            except Exception:  # noqa: BLE001
                if not reachable:
                    # daemon absent — don't stall startup for 60 s on it
                    time.sleep(0.3)
                    return False
            time.sleep(1.0)
        return False

    def ready(self):
        """Prefer the separate llm-server. The model is loaded in-process
        only when staging opted in via MOSS_LLM_ALLOW_IN_PROCESS=1, so
        startup stays fast when the service is already up."""
        if self.remote_ready():
            return True
        return self._ensure_local()

    def _chat_remote(self, messages, max_tokens, temp, timeout):
        if time.time() < self._remote_down_until:
            return None
        try:
            req = urllib.request.Request(
                VERA_LLM_URL.strip("/") + "/chat",
                data=json.dumps({"messages": messages, "max_tokens": max_tokens,
                                 "temp": temp}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as r:
                obj = json.loads(r.read().decode())
        except Exception as e:  # noqa: BLE001
            self._remote_failures += 1
            if self._remote_failures >= 3:
                self._remote_down_until = time.time() + 60
            print(f"[call-agent] llm-server unreachable ({e})", flush=True)
            return None
        if obj.get("ok") and obj.get("text"):
            self._remote_failures = 0
            self._remote_down_until = 0.0
            return obj["text"]
        self._remote_failures += 1
        return None

    @staticmethod
    def _finish_chat(out):
        """Shared post-processing for any LLM backend: clean, reject
        empty/refusal-ish output. Returns the final string or None."""
        if not out:
            return None
        cleaned = _clean_llm(out)
        if not cleaned or len(cleaned) < 4:
            return None
        low = cleaned.lower()
        if any(x in low for x in ("as an ai", "к сожалению, я не могу",
                                  "i cannot", "я не могу помочь")):
            return None
        return cleaned

    def chat(self, messages, max_tokens=100, temp=0.65, timeout=15):
        """Generate a reply for chat-style ``messages``. Returns cleaned text
        or None on any failure/timeout. Tries the remote/cloud LLM first;
        in-process generation is a staging-only tier
        (MOSS_LLM_ALLOW_IN_PROCESS=1) and the scripted fallback is the final
        safety net."""
        if self._openai:
            out = self._chat_openai(messages, max_tokens, temp, timeout)
            if out is None:
                out = self._chat_local(messages, max_tokens, temp, timeout)
            return self._finish_chat(out)
        out = self._chat_remote(messages, max_tokens, temp, min(timeout, 30))
        if out is None:
            out = self._chat_local(messages, max_tokens, temp, timeout)
        return self._finish_chat(out)

    def _chat_openai(self, messages, max_tokens=100, temp=0.65, timeout=15):
        """OpenAI-compatible non-streaming chat (llama.cpp llama-server)."""
        if time.time() < self._remote_down_until:
            return None
        conn = None
        try:
            parts = urllib.parse.urlsplit(VERA_LLM_URL.strip("/"))
            conn = http.client.HTTPConnection(
                parts.hostname or "127.0.0.1", parts.port or 9500,
                timeout=timeout)
            body = {"model": "local", "messages": messages,
                    "max_tokens": max_tokens, "temperature": temp,
                    "stream": False,
                    # Qwen3 on llama.cpp ignores enable_thinking alone:
                    # it burns the whole budget on </think> reasoning tokens and
                    # returns empty content -> ~9 s silence then scripted
                    # fallback.  thinking:false + stop at double-newline
                    # forces real content.
                    "thinking": False,
                    "stop": ["\n\n"],
                    "chat_template_kwargs": {"enable_thinking": False}}
            conn.request("POST", (parts.path or "") + "/v1/chat/completions",
                         body=json.dumps(body).encode(),
                         headers={"Content-Type": "application/json"})
            resp = conn.getresponse()
            if resp.status != 200:
                resp.read(256)
                raise ConnectionError(f"HTTP {resp.status}")
            data = json.loads(resp.read().decode())
            out = data["choices"][0]["message"]["content"]
            if not out:
                rc = data["choices"][0]["message"].get("reasoning_content", "")
                rc = re.sub(r"^</think>\s*", "", rc).strip()
                if rc:
                    out = rc
            self._remote_failures = 0
            self._remote_down_until = 0.0
            return out
        except Exception as e:  # noqa: BLE001
            self._remote_failures += 1
            if self._remote_failures >= 3:
                self._remote_down_until = time.time() + 60
            print(f"[call-agent] openai-llm unreachable ({e})", flush=True)
            return None
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:  # noqa: BLE001
                    pass

    def _chat_local(self, messages, max_tokens=100, temp=0.65, timeout=15):
        """Original in-process generation (fallback when llm-server is down)."""
        if not self._ensure_local():
            return None
        from mlx_lm import generate
        from mlx_lm.sample_utils import make_sampler
        prompt = None
        try:
            prompt = self._tok.apply_chat_template(
                messages, add_generation_prompt=True, enable_thinking=False)
        except Exception:  # noqa: BLE001
            return None
        t0 = time.time()
        with self._gen_lock:
            try:
                out = generate(self._model, self._tok, prompt=prompt,
                               max_tokens=max_tokens, verbose=False,
                               sampler=make_sampler(temp=temp))
            except Exception as e:  # noqa: BLE001
                print(f"[call-agent] LLM error: {e}", flush=True)
                return None
        if time.time() - t0 > timeout:
            return None
        return out

    # ---- token streaming (REALTIME FIX, Stage 5) ----------------------------
    # The reply is generated as DELTAS so the dialogue engine can send the
    # first complete sentence to TTS while the rest is still being generated:
    #   remote llm-server /chat_stream  ->  (staging only, opt-in) in-process
    #   mlx stream  ->  empty stream -> the caller uses its scripted phrase.
    def chat_stream(self, messages, max_tokens=100, temp=0.65, timeout=15):
        """Yield text deltas. Never raises: a failed backend silently moves
        to the next fallback tier; an empty stream means the caller uses its
        canned fallback phrase."""
        if self._openai:
            gen = self._chat_openai_stream(
                messages, max_tokens, temp, min(timeout, 30))
            if gen is not None:
                yielded = False
                try:
                    for d in gen:
                        if d:
                            yielded = True
                            yield d
                    return
                except Exception as e:  # noqa: BLE001
                    self._remote_failures += 1
                    if self._remote_failures >= 3:
                        self._remote_down_until = time.time() + 60
                    print(f"[call-agent] openai-llm stream error ({e}); "
                          "scripted fallback", flush=True)
                    if yielded:
                        # PARTIAL-STREAM GUARD: deltas already reached the
                        # caller/TTS; regenerating locally would replay the
                        # whole answer right after its truncated beginning.
                        return
            for d in self._chat_stream_local(
                    messages, max_tokens, temp, timeout):
                if d:
                    yield d
            return
        gen = self._chat_stream_remote(
            messages, max_tokens, temp, min(timeout, 30))
        if gen is not None:
            yielded = False
            try:
                for d in gen:
                    if d:
                        yielded = True
                        yield d
                return
            except Exception as e:  # noqa: BLE001
                self._remote_failures += 1
                if self._remote_failures >= 3:
                    self._remote_down_until = time.time() + 60
                print(f"[call-agent] llm-server stream error ({e}); "
                      "scripted fallback", flush=True)
                if yielded:
                    # PARTIAL-STREAM GUARD: see the openai branch above.
                    return
        for d in self._chat_stream_local(messages, max_tokens, temp, timeout):
            if d:
                yield d

    def _chat_openai_stream(self, messages, max_tokens, temp, timeout):
        """OpenAI-compatible SSE streaming (llama.cpp llama-server).
        Returns a delta-generator, or None when the daemon is absent /
        circuit-open / rejects us."""
        if time.time() < self._remote_down_until:
            return None
        try:
            parts = urllib.parse.urlsplit(VERA_LLM_URL.strip("/"))
            conn = http.client.HTTPConnection(
                parts.hostname or "127.0.0.1", parts.port or 9500,
                timeout=timeout)
            body = {"model": "local", "messages": messages,
                    "max_tokens": max_tokens, "temperature": temp,
                    "stream": True,
                    # Qwen3 on llama.cpp: see non-streaming fix above.
                    "thinking": False,
                    "stop": ["\n\n"],
                    "chat_template_kwargs": {"enable_thinking": False}}
            conn.request("POST", (parts.path or "") + "/v1/chat/completions",
                         body=json.dumps(body).encode(),
                         headers={"Content-Type": "application/json"})
            resp = conn.getresponse()
            if resp.status != 200:
                resp.read(256)
                conn.close()
                raise ConnectionError(f"HTTP {resp.status}")
        except Exception as e:  # noqa: BLE001
            self._remote_failures += 1
            if self._remote_failures >= 3:
                self._remote_down_until = time.time() + 60
            print(f"[call-agent] openai-llm /v1/chat/completions "
                  f"unreachable ({e})", flush=True)
            return None

        def _frames():
            buf = b""
            try:
                while True:
                    chunk = resp.read1(65536)
                    if not chunk:
                        break
                    buf += chunk
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        line = line.strip()
                        if not line or not line.startswith(b"data:"):
                            continue
                        payload = line[5:].strip()
                        if payload == b"[DONE]":
                            self._remote_failures = 0
                            self._remote_down_until = 0.0
                            return
                        try:
                            obj = json.loads(payload)
                        except json.JSONDecodeError:
                            continue
                        try:
                            delta = obj["choices"][0]["delta"].get("content")
                        except Exception:  # noqa: BLE001
                            delta = None
                        if delta:
                            delta = delta.replace("</think>", "")
                            if delta.strip():
                                yield delta
                # A successful OpenAI stream is explicitly terminated by
                # [DONE]. EOF without it is a truncated transport, not a
                # complete answer.
                raise ConnectionError("openai stream ended before [DONE]")
            finally:
                try:
                    conn.close()
                except Exception:  # noqa: BLE001
                    pass

        return _frames()

    def _chat_stream_remote(self, messages, max_tokens, temp, timeout):
        """Connect EAGERLY to /chat_stream; return a delta-generator, or None
        when the daemon is absent / circuit-open / rejects us."""
        if time.time() < self._remote_down_until:
            return None
        try:
            parts = urllib.parse.urlsplit(VERA_LLM_URL.strip("/"))
            conn = http.client.HTTPConnection(
                parts.hostname or "127.0.0.1", parts.port or 9500,
                timeout=timeout)
            body = json.dumps({"messages": messages,
                               "max_tokens": max_tokens,
                               "temp": temp}).encode()
            conn.request("POST", parts.path + "/chat_stream"
                         if parts.path else "/chat_stream",
                         body=body,
                         headers={"Content-Type": "application/json"})
            resp = conn.getresponse()
            if resp.status != 200:
                resp.read(256)
                conn.close()
                raise ConnectionError(f"HTTP {resp.status}")
        except Exception as e:  # noqa: BLE001
            self._remote_failures += 1
            if self._remote_failures >= 3:
                self._remote_down_until = time.time() + 60
            print(f"[call-agent] llm-server /chat_stream unreachable ({e})",
                  flush=True)
            return None

        def _frames():
            buf = b""
            try:
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
                        if frame.get("done"):
                            self._remote_failures = 0
                            self._remote_down_until = 0.0
                            return
                        if frame.get("error"):
                            raise RuntimeError(frame["error"])
                        if frame.get("delta"):
                            yield frame["delta"]
            finally:
                # LEAK FIX: a barge-in closes the consumer mid-yield
                # (GeneratorExit) — without finally the socket stayed open
                # until GC. Mirrors _chat_openai_stream.
                try:
                    conn.close()
                except Exception:  # noqa: BLE001
                    pass

        return _frames()

    def _chat_stream_local(self, messages, max_tokens=100, temp=0.65,
                           timeout=15):
        """In-process mlx streaming; batch generation as the last resort."""
        if not self._ensure_local():
            out = self._chat_local(messages, max_tokens, temp, timeout)
            if out:
                yield out
            return
        from mlx_lm import stream_generate
        from mlx_lm.sample_utils import make_sampler
        try:
            prompt = self._tok.apply_chat_template(
                messages, add_generation_prompt=True, enable_thinking=False)
        except Exception:  # noqa: BLE001
            out = self._chat_local(messages, max_tokens, temp, timeout)
            if out:
                yield out
            return
        with self._gen_lock:
            try:
                for resp in stream_generate(
                        self._model, self._tok, prompt=prompt,
                        max_tokens=max_tokens,
                        sampler=make_sampler(temp=temp)):
                    if resp.text:
                        yield resp.text
            except Exception as e:  # noqa: BLE001
                print(f"[call-agent] LLM stream error: {e}", flush=True)