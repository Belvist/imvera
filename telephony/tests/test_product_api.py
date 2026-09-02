"""Product API contract tests — OTP auth + IDOR (in-memory, no Postgres)."""

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402

from product.api import create_app  # noqa: E402
from product.auth import (  # noqa: E402
    AuthError,
    MemoryOtpStore,
    issue_token_pair,
    request_otp,
    verify_jwt,
    verify_otp,
)
from product.db import MemoryProductStore  # noqa: E402


class AuthUnitTests(unittest.TestCase):
    def setUp(self):
        self._env = mock.patch.dict(os.environ, {
            "MOSS_JWT_SECRET": "test-jwt-secret-32chars-minimum!",
            "MOSS_OTP_DEV_CODE": "424242",
        }, clear=False)
        self._env.start()

    def tearDown(self):
        self._env.stop()

    def test_otp_dev_code(self):
        store = MemoryOtpStore()
        request_otp(store, "79001234567")
        self.assertTrue(verify_otp(store, "79001234567", "424242"))

    def test_jwt_roundtrip(self):
        pair = issue_token_pair("usr-1", "79001234567")
        claims = verify_jwt(pair["access_token"], expected_typ="access")
        self.assertEqual(claims["sub"], "usr-1")

    def test_tampered_jwt(self):
        pair = issue_token_pair("usr-1", "79001234567")
        bad = pair["access_token"][:-4] + "xxxx"
        with self.assertRaises(AuthError):
            verify_jwt(bad)


class ProductApiTests(unittest.TestCase):
    def setUp(self):
        self._env = mock.patch.dict(os.environ, {
            "MOSS_JWT_SECRET": "test-jwt-secret-32chars-minimum!",
            "MOSS_OTP_DEV_CODE": "424242",
            "MOSS_PG_URL": "",
            "MOSS_REDIS_URL": "",
        }, clear=False)
        self._env.start()
        os.environ.pop("MOSS_PG_URL", None)
        self.store = MemoryProductStore()
        self.otp = MemoryOtpStore()
        self.app = create_app(store=self.store, otp_store=self.otp)
        self.client = TestClient(self.app)

    def tearDown(self):
        self._env.stop()

    def _auth_headers(self, phone="+79001112233"):
        r = self.client.post("/api/v1/auth/otp/request",
                             json={"phone": phone})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json().get("ok"))
        self.assertNotIn("code", r.json())
        r = self.client.post("/api/v1/auth/otp/verify",
                             json={"phone": phone, "code": "424242"})
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertIn("access_token", body)
        self.assertIn("refresh_token", body)
        return {"Authorization": "Bearer " + body["access_token"]}

    def test_otp_happy_path_and_me(self):
        headers = self._auth_headers()
        r = self.client.get("/api/v1/me", headers=headers)
        self.assertEqual(r.status_code, 200)
        me = r.json()
        self.assertEqual(me["phone"], "79001112233")
        self.assertTrue(me["id"].startswith("user-"))

    def test_otp_rejects_bad_code(self):
        self.client.post("/api/v1/auth/otp/request",
                         json={"phone": "+79001112233"})
        r = self.client.post("/api/v1/auth/otp/verify",
                             json={"phone": "+79001112233", "code": "000000"})
        self.assertEqual(r.status_code, 401)

    def test_idor_rejects_foreign_household(self):
        h_a = self._auth_headers("+79001112233")
        h_b = self._auth_headers("+79004445566")

        r = self.client.post("/api/v1/households",
                             headers=h_a, json={"name": "Семья А"})
        self.assertEqual(r.status_code, 201, r.text)
        hh_a = r.json()["id"]

        r = self.client.post("/api/v1/households",
                             headers=h_b, json={"name": "Семья Б"})
        self.assertEqual(r.status_code, 201)
        hh_b = r.json()["id"]

        r = self.client.get(f"/api/v1/households/{hh_a}/elders", headers=h_b)
        self.assertEqual(r.status_code, 403, r.text)

        r = self.client.post(
            f"/api/v1/households/{hh_a}/elders",
            headers=h_a,
            json={"phone": "+79001234567", "display_name": "Мама"})
        self.assertEqual(r.status_code, 201, r.text)
        elder_id = r.json()["person_id"]

        r = self.client.post(
            f"/api/v1/households/{hh_a}/elders",
            headers=h_b,
            json={"phone": "+79007654321", "display_name": "Чужая"})
        self.assertEqual(r.status_code, 403)

        r = self.client.get(f"/api/v1/elders/{elder_id}/calls", headers=h_b)
        self.assertEqual(r.status_code, 403)
        r = self.client.get(f"/api/v1/elders/{elder_id}/consent", headers=h_b)
        self.assertEqual(r.status_code, 403)

        r = self.client.get(f"/api/v1/households/{hh_a}/elders", headers=h_a)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()["elders"]), 1)
        r = self.client.get(f"/api/v1/households/{hh_b}/elders", headers=h_b)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["elders"], [])

    def test_incident_ack_membership_guard(self):
        h_a = self._auth_headers("+79001112233")
        h_b = self._auth_headers("+79004445566")
        hh = self.client.post("/api/v1/households", headers=h_a,
                              json={"name": "Дом"}).json()["id"]
        self.store.seed_incident("inc-test1", household_id=hh, status="open")

        r = self.client.post("/api/v1/incidents/inc-test1/ack",
                             headers=h_b, json={"note": "смотрю"})
        self.assertEqual(r.status_code, 403)

        r = self.client.post("/api/v1/incidents/inc-test1/ack",
                             headers=h_a, json={"note": "Я проверю"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["status"], "checking")

    def test_schedule_and_question(self):
        headers = self._auth_headers()
        hh = self.client.post("/api/v1/households", headers=headers,
                              json={"name": "Дом"}).json()["id"]
        elder = self.client.post(
            f"/api/v1/households/{hh}/elders", headers=headers,
            json={"phone": "89001234567", "display_name": "Бабушка"}).json()
        eid = elder["person_id"]

        r = self.client.put(
            f"/api/v1/elders/{eid}/schedule", headers=headers,
            json={"window_start": "09:00", "window_end": "12:00",
                  "days_of_week": [1, 3, 5], "paused": False})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["window_start"], "09:00")
        self.assertEqual(r.json()["days_of_week"], [1, 3, 5])

        r = self.client.post(
            f"/api/v1/elders/{eid}/questions", headers=headers,
            json={"text": "Как спали ночью?", "author_label": "внук"})
        self.assertEqual(r.status_code, 201, r.text)
        self.assertEqual(r.json()["status"], "pending")

    def test_contacts_and_call_now(self):
        headers = self._auth_headers()
        hh = self.client.post("/api/v1/households", headers=headers,
                              json={"name": "Дом"}).json()["id"]
        elder = self.client.post(
            f"/api/v1/households/{hh}/elders", headers=headers,
            json={"phone": "89007654321", "display_name": "Дед"}).json()
        r = self.client.post(
            f"/api/v1/households/{hh}/contacts", headers=headers,
            json={"channel": "telegram", "address": "12345",
                  "escalate_order": 0})
        self.assertEqual(r.status_code, 201, r.text)
        r = self.client.get(f"/api/v1/households/{hh}/contacts",
                            headers=headers)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()["contacts"]), 1)
        r = self.client.post(
            f"/api/v1/elders/{elder['person_id']}/call-now", headers=headers)
        self.assertEqual(r.status_code, 201, r.text)
        self.assertEqual(r.json()["status"], "pending")

    def test_delete_me_exports_and_revokes(self):
        headers = self._auth_headers("+79009998877")
        r = self.client.delete("/api/v1/me", headers=headers)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["revoked"])
        self.assertIn("export", r.json())
        r = self.client.get("/api/v1/me", headers=headers)
        self.assertEqual(r.status_code, 401)

    def test_never_echoes_otp_in_request_response(self):
        r = self.client.post("/api/v1/auth/otp/request",
                             json={"phone": "+79001112233"})
        blob = r.text.lower()
        self.assertNotIn("424242", blob)
        self.assertNotIn("\"code\"", blob)


if __name__ == "__main__":
    unittest.main()
