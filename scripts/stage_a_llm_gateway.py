#!/usr/bin/env python3
"""Stage A LLM gateway — canonical /health on :9500, proxies OpenAI API to llama-server.

run_llm_host.sh starts llama-server on an internal port and this gateway on the
public port so Golden Path and telephony share one honest identity contract.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

DEFAULT_MODEL_ID = os.environ.get("MOSS_LLM_MODEL_ID", "Qwen3-4B-Q4_K_M")
DEFAULT_REVISION = os.environ.get("MOSS_LLM_REVISION", "main")
DEFAULT_BACKEND = os.environ.get("MOSS_LLM_BACKEND", "llama.cpp")
DEFAULT_PROTOCOL = os.environ.get("MOSS_LLM_PROTOCOL", "openai")
DEFAULT_DEVICE = os.environ.get("MOSS_LLM_DEVICE", "metal")


class GatewayState:
    def __init__(self, internal_base: str) -> None:
        self.internal_base = internal_base.rstrip("/")
        self.model_id = DEFAULT_MODEL_ID
        self.revision = DEFAULT_REVISION
        self.backend = DEFAULT_BACKEND
        self.protocol = DEFAULT_PROTOCOL
        self.device = DEFAULT_DEVICE
        self._lock = threading.Lock()
        self._llama_proc: subprocess.Popen[Any] | None = None

    def set_llama_proc(self, proc: subprocess.Popen[Any]) -> None:
        with self._lock:
            self._llama_proc = proc

    def llama_alive(self) -> bool:
        with self._lock:
            proc = self._llama_proc
        return proc is not None and proc.poll() is None

    def internal_ready(self) -> bool:
        try:
            with urllib.request.urlopen(
                f"{self.internal_base}/health", timeout=2.0
            ) as resp:
                obj = json.loads(resp.read().decode())
            return bool(obj.get("status") == "ok" or obj.get("ready"))
        except (OSError, json.JSONDecodeError, urllib.error.URLError):
            return False

    def openai_models_ok(self) -> bool:
        try:
            with urllib.request.urlopen(
                f"{self.internal_base}/v1/models", timeout=3.0
            ) as resp:
                return resp.status == 200
        except (OSError, urllib.error.URLError):
            return False

    def canonical_health(self) -> dict[str, Any]:
        ready = (
            self.llama_alive()
            and self.internal_ready()
            and self.openai_models_ok()
        )
        return {
            "service": "mossvoice-llm",
            "protocol_version": 1,
            "ready": ready,
            "model_id": self.model_id,
            "revision": self.revision,
            "backend": self.backend,
            "protocol": self.protocol,
            "device": self.device,
            "thinking": False,
            "generation_profile": os.environ.get(
                "MOSS_LLM_GENERATION_PROFILE", "vera_deterministic"
            ),
            "gateway": "stage_a",
            "internal_url": self.internal_base,
        }


def build_handler(state: GatewayState):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *_args: Any) -> None:
            return

        def _json(self, obj: dict[str, Any], status: int = 200) -> None:
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _proxy(self) -> None:
            target = state.internal_base + self.path
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length > 0 else None
            req = urllib.request.Request(
                target,
                data=body,
                method=self.command,
            )
            for key, value in self.headers.items():
                if key.lower() in ("host", "content-length"):
                    continue
                req.add_header(key, value)
            try:
                with urllib.request.urlopen(req, timeout=120.0) as upstream:
                    payload = upstream.read()
                    self.send_response(upstream.status)
                    for key, value in upstream.headers.items():
                        if key.lower() in ("transfer-encoding", "connection"):
                            continue
                        self.send_header(key, value)
                    self.end_headers()
                    self.wfile.write(payload)
            except urllib.error.HTTPError as exc:
                payload = exc.read()
                self.send_response(exc.code)
                self.send_header("Content-Type", exc.headers.get("Content-Type", "application/json"))
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            except OSError as exc:
                self._json({"error": str(exc)}, 502)

        def do_GET(self) -> None:
            path = self.path.split("?")[0]
            if path in ("/health", "/healthz"):
                self._json(state.canonical_health())
                return
            self._proxy()

        def do_POST(self) -> None:
            self._proxy()

    return Handler


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage A LLM gateway")
    parser.add_argument("--host", default=os.environ.get("MOSS_LLM_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("MOSS_LLM_PORT", "9500")))
    parser.add_argument(
        "--internal-port",
        type=int,
        default=int(os.environ.get("MOSS_LLM_INTERNAL_PORT", "9501")),
    )
    parser.add_argument(
        "--llama-cmd",
        nargs=argparse.REMAINDER,
        help="Command to start llama-server (everything after this flag)",
    )
    args = parser.parse_args()

    if not args.llama_cmd:
        print("stage_a_llm_gateway: --llama-cmd required", file=sys.stderr)
        return 2

    internal_base = f"http://127.0.0.1:{args.internal_port}"
    state = GatewayState(internal_base)

    proc = subprocess.Popen(args.llama_cmd)
    state.set_llama_proc(proc)

    def _shutdown(*_sig: Any) -> None:
        if proc.poll() is None:
            proc.send_signal(signal.SIGTERM)
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    httpd = ThreadingHTTPServer((args.host, args.port), build_handler(state))
    print(
        f"[llm-gateway] public http://{args.host}:{args.port} "
        f"→ internal {internal_base} model={state.model_id}",
        flush=True,
    )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        if proc.poll() is None:
            proc.terminate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
