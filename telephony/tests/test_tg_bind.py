"""Tests for Telegram bind tokens (E6)."""
import os
import unittest

from core import tg_bind


class TgBindTests(unittest.TestCase):
    def setUp(self):
        os.environ["MOSS_JWT_SECRET"] = "test-secret-for-bind"

    def test_mint_verify_roundtrip(self):
        tok = tg_bind.mint_bind_token("hh-1", ttl_sec=60)
        self.assertEqual(tg_bind.verify_bind_token(tok), "hh-1")

    def test_tamper_fails(self):
        tok = tg_bind.mint_bind_token("hh-1", ttl_sec=60)
        bad = tok[:-1] + ("0" if tok[-1] != "0" else "1")
        self.assertIsNone(tg_bind.verify_bind_token(bad))

    def test_parse_start(self):
        self.assertEqual(
            tg_bind.parse_start_payload("/start bind_abc.def"), "abc.def")
        self.assertIsNone(tg_bind.parse_start_payload("/start hello"))


if __name__ == "__main__":
    unittest.main()
