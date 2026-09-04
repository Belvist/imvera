"""Delivery channels and unroutable-incident regressions."""

import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.delivery import SmsChannel, VoiceChannel  # noqa: E402
from core.incidents import IncidentEngine  # noqa: E402
from adapters.esl import originate_status  # noqa: E402


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, _size=None):
        return json.dumps(self.payload).encode("utf-8")


class _Opener:
    def __init__(self, payload):
        self.payload = payload
        self.request = None

    def open(self, request, timeout=None):
        self.request = request
        return _Response(self.payload)


class DeliveryChannelTests(unittest.TestCase):
    def test_sms_provider_is_real_and_uses_bearer_auth(self):
        opener = _Opener({"ok": True, "message_id": "m-1"})
        env = {
            "MOSS_SMS_PROVIDER": "generic",
            "MOSS_SMS_PROVIDER_URL": "https://sms.example.test/send",
            "MOSS_SMS_PROVIDER_KEY": "secret-key",
            "MOSS_SMS_PROVIDER_USER": "IMVERA",
        }
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch("core.delivery.urllib.request.build_opener",
                           return_value=opener):
            ok, detail = SmsChannel().send("+7 (900) 123-45-67", "Тревога")

        self.assertTrue(ok)
        self.assertEqual(detail, "sms:generic:ok:m-1")
        self.assertEqual(
            opener.request.get_header("Authorization"), "Bearer secret-key")
        self.assertEqual(
            json.loads(opener.request.data)["to"], "+79001234567")

    def test_provider_http_is_rejected_by_default(self):
        env = {
            "MOSS_CALL_PROVIDER": "generic",
            "MOSS_CALL_PROVIDER_URL": "http://provider.example.test/call",
            "MOSS_CALL_PROVIDER_KEY": "secret-key",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            ok, detail = VoiceChannel().send("+79001234567", "Call")

        self.assertFalse(ok)
        self.assertIn("ValueError", detail)

    def test_missing_provider_key_fails_before_network(self):
        env = {
            "MOSS_CALL_PROVIDER": "generic",
            "MOSS_CALL_PROVIDER_URL": "https://provider.example.test/call",
        }
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch("core.delivery.urllib.request.build_opener") as open_:
            ok, detail = VoiceChannel().send("+79001234567", "Call")

        self.assertFalse(ok)
        self.assertIn("ValueError", detail)
        open_.assert_not_called()

    def test_esl_failure_uses_message_not_error_key(self):
        env = {"MOSS_CALL_VIA_ESL": "1"}
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch("adapters.esl.originate_to_number",
                           return_value={"ok": False, "uuid": None,
                                         "message": "USER_NOT_REGISTERED"}):
            ok, detail = VoiceChannel().send("+79001234567", "Call")
        self.assertFalse(ok)
        self.assertEqual(detail, "call:esl:USER_NOT_REGISTERED")

    def test_esl_success_includes_uuid(self):
        env = {"MOSS_CALL_VIA_ESL": "1"}
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch("adapters.esl.originate_to_number",
                           return_value={"ok": True, "uuid": "abc-123",
                                         "message": "Call originated"}):
            ok, detail = VoiceChannel().send("+79001234567", "Call")
        self.assertTrue(ok)
        self.assertEqual(detail, "call:esl:ok:abc-123")


class EslOriginateStatusTests(unittest.TestCase):
    def test_failure_prefers_message_over_missing_error(self):
        ok, detail = originate_status(
            {"ok": False, "uuid": None, "message": "USER_NOT_REGISTERED"})
        self.assertFalse(ok)
        self.assertEqual(detail, "USER_NOT_REGISTERED")

    def test_failure_falls_back_to_error_key(self):
        ok, detail = originate_status({"ok": False, "error": "legacy"})
        self.assertFalse(ok)
        self.assertEqual(detail, "legacy")


class _Router:
    def channel_names(self):
        return ["push", "sms", "call"]


class _PG:
    def __init__(self):
        self.actions = []
        self.audits = []
        self.bumped = []

    def get_incident_by_call(self, call_id):
        return None

    def open_incident(self, *args, **kwargs):
        return None

    def queue_action(self, incident_id, channel, contact, order):
        self.actions.append((channel, contact, order))

    def audit(self, action, actor, entity, entity_id, detail):
        self.audits.append(action)

    def next_queued_action(self, incident_id):
        return None

    def bump_escalation(self, incident_id):
        self.bumped.append(incident_id)


class IncidentRoutingTests(unittest.TestCase):
    def test_no_contacts_never_creates_fake_unset_action(self):
        pg = _PG()
        with mock.patch.dict(os.environ, {}, clear=True):
            incident_id = IncidentEngine(pg, _Router()).maybe_open(
                "call-1", "alert")

        self.assertTrue(incident_id.startswith("inc-"))
        self.assertEqual(pg.actions, [])
        self.assertEqual(pg.bumped, [incident_id])
        self.assertIn("incident.notify.unroutable", pg.audits)


if __name__ == "__main__":
    unittest.main()
