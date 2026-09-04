"""Tests for on-disk call journal (date/time + dialogue trace)."""
from __future__ import annotations

import json
import os
import tempfile
import unittest

from core.call_journal import record_call_end, record_call_start, record_turn


class CallJournalTests(unittest.TestCase):
    def test_start_turn_end_writes_trace_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            cdir = record_call_start(
                tmp, "abc123", caller_id="+79001234567",
                greeting="Здравствуйте!")
            self.assertTrue(os.path.isdir(cdir))
            self.assertTrue(os.path.isfile(os.path.join(cdir, "call_meta.json")))
            self.assertTrue(os.path.isfile(os.path.join(cdir, "dialogue.txt")))
            self.assertTrue(os.path.isfile(os.path.join(tmp, "LATEST_CALL.txt")))
            record_turn(tmp, "abc123", 1, "user", "", input_reason="low_conf")
            record_turn(tmp, "abc123", 2, "assistant", "Повторите, пожалуйста.")
            record_call_end(tmp, "abc123", status="ok")
            with open(os.path.join(cdir, "dialogue.txt"), encoding="utf-8") as f:
                body = f.read()
            self.assertIn("MSK", body)
            self.assertIn("Абонент: (пусто: low_conf)", body)
            self.assertIn("конец звонка", body)
            with open(os.path.join(tmp, "calls_journal.jsonl"),
                      encoding="utf-8") as f:
                lines = f.readlines()
            self.assertGreaterEqual(len(lines), 3)
            self.assertEqual(json.loads(lines[0])["event"], "call_start")


if __name__ == "__main__":
    unittest.main()
