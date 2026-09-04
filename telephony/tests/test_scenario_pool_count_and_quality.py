"""Scenario pool quality — ≥100 unique lines, orthography guards."""
from __future__ import annotations

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from conversation_system.reply.pools import all_unique_spoken_lines, pool_counts

_FORBIDDEN_PROMISE = re.compile(
    r"\b(позвоню|вызову|отправлю|организую|закажу)\b", re.I
)
_LATIN = re.compile(r"[A-Za-z]")
_OLD_BRAND_SPELLING = re.compile(r"вэра", re.I)
_PLURAL_SINGULAR_MISMATCH = re.compile(
    r"\b(родные|близкие|родственники)\s+получит\b", re.I
)
_INCOMPLETE_SYMPTOM_Q = re.compile(
    r"(всё ещё\?|так же\?)$"
)
_QUESTION_STARTERS = re.compile(
    r"^(как|что|где|когда|чем|есть ли|была ли|был ли|чувствуете ли|"
    r"расскажите|принимали ли|стало ли|сильно ли)\b",
    re.I
)


class ScenarioPoolQualityTests(unittest.TestCase):
    def test_at_least_100_unique_lines(self):
        lines = all_unique_spoken_lines()
        counts = pool_counts()
        self.assertGreaterEqual(len(lines), 100, counts)
        self.assertGreaterEqual(counts["unique_total"], 100)

    def test_no_forbidden_promise_phrases(self):
        for line in all_unique_spoken_lines():
            self.assertIsNone(
                _FORBIDDEN_PROMISE.search(line),
                msg=f"promise leak: {line!r}",
            )

    def test_at_most_one_question_mark(self):
        for line in all_unique_spoken_lines():
            self.assertLessEqual(
                line.count("?"),
                1,
                msg=f"multiple questions: {line!r}",
            )

    def test_no_latin_letters(self):
        for line in all_unique_spoken_lines():
            self.assertFalse(
                _LATIN.search(line),
                msg=f"latin in pool: {line!r}",
            )

    def test_brand_spelling_imvera(self):
        """Spoken pools must use Имвера, never the old «вэра» spelling."""
        for line in all_unique_spoken_lines():
            self.assertIsNone(
                _OLD_BRAND_SPELLING.search(line),
                msg=f"old brand spelling: {line!r}",
            )
            if "имвера" in line.lower():
                self.assertIn(
                    "Имвера",
                    line,
                    msg=f"brand must be capitalized Имвера: {line!r}",
                )

    def test_all_pools_grammar(self):
        """Basic Russian grammar guards on scripted spoken lines."""
        for line in all_unique_spoken_lines():
            low = line.lower()
            self.assertIsNone(
                _PLURAL_SINGULAR_MISMATCH.search(low),
                msg=f"subject-verb mismatch: {line!r}",
            )
            self.assertIsNone(
                _INCOMPLETE_SYMPTOM_Q.search(low),
                msg=f"truncated question: {line!r}",
            )
            if _QUESTION_STARTERS.search(low) and "?" not in line:
                self.assertIn(
                    "ли",
                    low,
                    msg=f"question missing '?': {line!r}",
                )


if __name__ == "__main__":
    unittest.main()
