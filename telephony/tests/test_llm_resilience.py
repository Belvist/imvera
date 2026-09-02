"""Regression tests for LLM circuit-breaker and partial-stream semantics."""

import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from adapters.cloud import CloudLLMWithFallback  # noqa: E402
from adapters.llm import LLMClient  # noqa: E402


class _LocalLLM:
    def __init__(self):
        self.stream_calls = 0

    def chat_stream(self, messages, **kwargs):
        self.stream_calls += 1
        yield "local fallback"

    def ready(self):
        return True


class _PartialProvider:
    def chat_stream(self, messages, **kwargs):
        yield "partial cloud"
        raise ConnectionError("stream interrupted")


class CloudFallbackTests(unittest.TestCase):
    def test_partial_cloud_stream_never_replays_local_answer(self):
        local = _LocalLLM()
        llm = CloudLLMWithFallback(_PartialProvider(), local)

        chunks = list(llm.chat_stream([{"role": "user", "content": "test"}]))

        self.assertEqual(chunks, ["partial cloud"])
        self.assertEqual(local.stream_calls, 0)


class _JSONResponse:
    status = 200

    def read(self, _size=None):
        return json.dumps({
            "choices": [{"message": {"content": "Всё хорошо."}}]
        }).encode("utf-8")


class _SSEStreamResponse:
    status = 200

    def __init__(self):
        self._chunks = [
            ('data: {"choices":[{"delta":{"content":"Хорошо."}}]}\n'
             "data: [DONE]\n").encode("utf-8"),
            b"",
        ]

    def read1(self, _size=None):
        return self._chunks.pop(0)


class _Connection:
    response_factory = _JSONResponse

    def __init__(self, *args, **kwargs):
        self.closed = False

    def request(self, *args, **kwargs):
        return None

    def getresponse(self):
        return self.response_factory()

    def close(self):
        self.closed = True


class LLMCircuitBreakerTests(unittest.TestCase):
    def setUp(self):
        self.client = LLMClient()
        self.client._remote_failures = 2
        self.client._remote_down_until = 0.0

    def test_openai_success_resets_failure_counter(self):
        with mock.patch("adapters.llm.http.client.HTTPConnection", _Connection):
            out = self.client._chat_openai([], 20, 0.2, 1)

        self.assertEqual(out, "Всё хорошо.")
        self.assertEqual(self.client._remote_failures, 0)
        self.assertEqual(self.client._remote_down_until, 0.0)

    def test_openai_stream_done_resets_failure_counter(self):
        class _StreamConnection(_Connection):
            response_factory = _SSEStreamResponse

        with mock.patch("adapters.llm.http.client.HTTPConnection",
                        _StreamConnection):
            chunks = list(self.client._chat_openai_stream([], 20, 0.2, 1))

        self.assertEqual(chunks, ["Хорошо."])
        self.assertEqual(self.client._remote_failures, 0)
        self.assertEqual(self.client._remote_down_until, 0.0)


if __name__ == "__main__":
    unittest.main()
