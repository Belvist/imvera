"""HTTP boundary regressions: bounded bodies and fail-closed webhooks."""

import hashlib
import hmac
import http.client
import json
import os
import sys
import threading
import unittest
import urllib.error
import urllib.request
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.http import Handler, MAX_BODY_BYTES, QuietHTTPServer  # noqa: E402


class _Serve:
    def __init__(self):
        self.events = []

    def handle_provider_event(self, payload):
        self.events.append(payload)
        return {"accepted": True}


class HTTPSecurityTests(unittest.TestCase):
    def setUp(self):
        self.serve = _Serve()
        self.server = QuietHTTPServer(("127.0.0.1", 0), Handler)
        self.server.serve = self.serve
        self.thread = threading.Thread(
            target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = "http://127.0.0.1:%d" % self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def _post(self, body, headers=None):
        req = urllib.request.Request(
            self.base + "/webhook/provider", data=body, method="POST",
            headers={"Content-Type": "application/json", **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=3) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def test_webhook_is_unavailable_without_secret(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MOSS_WEBHOOK_SECRET", None)
            status, body = self._post(b'{"event_id":"evt-1"}')

        self.assertEqual(status, 503)
        self.assertEqual(body["error"], "webhook not configured")
        self.assertEqual(self.serve.events, [])

    def test_webhook_rejects_bad_signature(self):
        with mock.patch.dict(os.environ, {"MOSS_WEBHOOK_SECRET": "test-secret"}):
            status, _ = self._post(
                b'{"event_id":"evt-1"}',
                {"X-Moss-Signature": "0" * 64})

        self.assertEqual(status, 401)
        self.assertEqual(self.serve.events, [])

    def test_webhook_accepts_valid_raw_body_hmac(self):
        raw = b'{"event_id":"evt-1","status":"ok"}'
        signature = hmac.new(
            b"test-secret", raw, hashlib.sha256).hexdigest()
        with mock.patch.dict(os.environ, {"MOSS_WEBHOOK_SECRET": "test-secret"}):
            status, body = self._post(
                raw, {"X-Moss-Signature": signature})

        self.assertEqual(status, 200)
        self.assertTrue(body["accepted"])
        self.assertEqual(self.serve.events, [
            {"event_id": "evt-1", "status": "ok"}])

    def test_oversized_body_returns_413_without_reading_payload(self):
        conn = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_address[1], timeout=3)
        conn.putrequest("POST", "/webhook/provider")
        conn.putheader("Content-Type", "application/json")
        conn.putheader("Content-Length", str(MAX_BODY_BYTES + 1))
        conn.endheaders()
        response = conn.getresponse()
        body = json.loads(response.read())
        conn.close()

        self.assertEqual(response.status, 413)
        self.assertEqual(body["error"], "body too large")

    def test_malformed_json_returns_400(self):
        with mock.patch.dict(os.environ, {"MOSS_WEBHOOK_SECRET": "test-secret"}):
            raw = b"{not-json"
            signature = hmac.new(
                b"test-secret", raw, hashlib.sha256).hexdigest()
            status, body = self._post(
                raw, {"X-Moss-Signature": signature})

        self.assertEqual(status, 400)
        self.assertEqual(body["error"], "invalid JSON body")

    def test_internal_control_endpoint_requires_configured_token(self):
        req = urllib.request.Request(
            self.base + "/calls", data=b"{}", method="POST",
            headers={"Content-Type": "application/json"})
        with mock.patch.dict(
                os.environ, {"MOSS_INTERNAL_API_TOKEN": "internal-test-key"}):
            with self.assertRaises(urllib.error.HTTPError) as raised:
                urllib.request.urlopen(req, timeout=3)

        self.assertEqual(raised.exception.code, 401)
        self.assertEqual(json.loads(raised.exception.read())["error"],
                         "unauthorized")


if __name__ == "__main__":
    unittest.main()
