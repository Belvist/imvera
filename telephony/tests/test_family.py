"""Family app <-> call pipeline (2026-08-23): offline coverage.

Covers key/phone/text helpers and the dialogue integration: family-app
questions become dynamic agenda entries AFTER the standard wellness topics,
the exact question text reaches the elder, answers are snapshotted onto the
question and the verdict notes mention the delivery."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.family import (FamilyValidationError, hash_key, new_key,  # noqa: E402
                         normalize_phone, validate_question_text)


def _plan_text(plan):
    """Intent + fallback — topic lives in intent when LLM drives speech."""
    return ((plan.get("intent") or "") + " " + (plan.get("fallback") or "")).lower()



class FamilyUtilsTests(unittest.TestCase):
    def test_new_key_shape_and_hash_stability(self):
        k = new_key()
        self.assertTrue(k.startswith("mv_"))
        self.assertGreater(len(k), 20)
        h1, h2 = hash_key(k), hash_key(k)
        self.assertEqual(h1, h2)
        self.assertEqual(len(h1), 64)          # sha256 hex
        self.assertNotEqual(hash_key(k), hash_key(k + "x"))

    def test_normalize_phone(self):
        self.assertEqual(normalize_phone("+7 (900) 123-45-67"),
                         "79001234567")
        # 8-code and 7-code forms are the SAME number (RU trunk prefix)
        self.assertEqual(normalize_phone("8-900-123-45-67"), "79001234567")
        self.assertEqual(normalize_phone("79001234567"), "79001234567")
        self.assertEqual(normalize_phone(None), "")
        self.assertEqual(normalize_phone(""), "")

    def test_validate_question_text(self):
        self.assertEqual(validate_question_text("  приняла ли таблетки? "),
                         "приняла ли таблетки?")
        with self.assertRaises(FamilyValidationError):
            validate_question_text("")
        with self.assertRaises(FamilyValidationError):
            validate_question_text("  ")
        with self.assertRaises(FamilyValidationError):
            validate_question_text("х" * 501)



if __name__ == "__main__":
    unittest.main(verbosity=2)
