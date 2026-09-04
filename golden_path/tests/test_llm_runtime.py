"""LLM runtime config, protocol probe, and identity contract tests."""
from __future__ import annotations

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from golden_path.llm import GoldenPathLLM, LLMRuntimeError, MockLLM, run_readiness_probe
from golden_path.llm_config import DEFAULT_MODEL_ID, DEFAULT_PROTOCOL, LLMRuntimeConfig, load_llm_config
from golden_path.llm_errors import TURN_FAILED_LLM_PROTOCOL, TURN_FAILED_LLM_UNAVAILABLE
from golden_path.llm_identity import identity_matches_config, normalize_model_id, parse_canonical_health


class _FakeLLMServer(ThreadingHTTPServer):
    allow_reuse_address = True


def _start_fake_server(handler_cls: type[BaseHTTPRequestHandler]) -> tuple[_FakeLLMServer, str]:
    server = _FakeLLMServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, f"http://{host}:{port}"


class LLMConfigTests(unittest.TestCase):
    def test_canonical_defaults(self) -> None:
        cfg = load_llm_config()
        self.assertEqual(cfg.model_id, DEFAULT_MODEL_ID)
        self.assertEqual(cfg.protocol, DEFAULT_PROTOCOL)
        self.assertEqual(cfg.base_url, "http://127.0.0.1:9500")


class LLMRuntimeFailFastTests(unittest.TestCase):
    def test_unreachable_endpoint_raises(self) -> None:
        llm = GoldenPathLLM(base_url="http://127.0.0.1:1")
        with self.assertRaises(LLMRuntimeError) as ctx:
            llm.require_ready()
        self.assertEqual(ctx.exception.code, TURN_FAILED_LLM_UNAVAILABLE)

    def test_mock_readiness_probe(self) -> None:
        report = run_readiness_probe(MockLLM(), calls=3, warmup_calls=0)
        self.assertEqual(report["calls"], 3)
        self.assertEqual(report["model_id"], "mock")

    def test_protocol_probe_rejects_models_404(self) -> None:
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args: object) -> None:
                return

            def _json(self, obj: dict, status: int = 200) -> None:
                body = json.dumps(obj).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:
                path = self.path.split("?")[0]
                if path == "/health":
                    self._json(
                        {
                            "ready": True,
                            "model_id": DEFAULT_MODEL_ID,
                            "revision": "main",
                            "backend": "llama.cpp",
                            "protocol": "openai",
                            "device": "metal",
                        }
                    )
                    return
                if path == "/v1/models":
                    self._json({"error": "not found"}, 404)
                    return
                self._json({"error": "missing"}, 404)

            def do_POST(self) -> None:
                self._json({"error": "not found"}, 404)

        server, base_url = _start_fake_server(Handler)
        try:
            llm = GoldenPathLLM(
                base_url=base_url,
                config=LLMRuntimeConfig(
                    model_id=DEFAULT_MODEL_ID,
                    revision="main",
                    backend="llama.cpp",
                    protocol="openai",
                    device="metal",
                    base_url=base_url,
                    timeout_s=5.0,
                ),
            )
            with self.assertRaises(LLMRuntimeError) as ctx:
                llm.require_ready()
            self.assertEqual(ctx.exception.code, TURN_FAILED_LLM_PROTOCOL)
            self.assertIn("/v1/models", ctx.exception.detail)
        finally:
            server.shutdown()

    def test_raw_llama_health_without_canonical_fields_fails(self) -> None:
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args: object) -> None:
                return

            def do_GET(self) -> None:
                body = json.dumps({"status": "ok"}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        server, base_url = _start_fake_server(Handler)
        try:
            llm = GoldenPathLLM(base_url=base_url)
            with self.assertRaises(LLMRuntimeError) as ctx:
                llm.require_ready()
            self.assertEqual(ctx.exception.code, TURN_FAILED_LLM_PROTOCOL)
            self.assertIn("canonical fields", ctx.exception.detail)
        finally:
            server.shutdown()


class LLMIdentityTests(unittest.TestCase):
    def test_parse_requires_all_fields(self) -> None:
        self.assertIsNone(parse_canonical_health({"ready": True, "status": "ok"}))
        identity = parse_canonical_health(
            {
                "ready": True,
                "model_id": "Qwen3-4B-Q4_K_M",
                "revision": "main",
                "backend": "llama.cpp",
                "protocol": "openai",
                "device": "metal",
            }
        )
        self.assertIsNotNone(identity)
        self.assertEqual(identity.model_id, "Qwen3-4B-Q4_K_M")

    def test_normalize_model_id(self) -> None:
        self.assertEqual(
            normalize_model_id("/data/models/llm/Qwen3-4B-Q4_K_M.gguf"),
            normalize_model_id("Qwen3-4B-Q4_K_M"),
        )

    def test_identity_mismatch_detected(self) -> None:
        identity = parse_canonical_health(
            {
                "ready": True,
                "model_id": "Qwen3-7B-8bit",
                "revision": "main",
                "backend": "mlx",
                "protocol": "native",
                "device": "metal",
            }
        )
        assert identity is not None
        cfg = load_llm_config(protocol="openai")
        mismatches = identity_matches_config(identity, cfg)
        self.assertTrue(any("protocol" in m for m in mismatches))
        self.assertTrue(any("model_id" in m for m in mismatches))


if __name__ == "__main__":
    unittest.main()
