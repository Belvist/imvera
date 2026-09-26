"""Step 4 guard: Vera speaks from banks, not new policy literals.

Collects every hardcoded Russian speech string passed as text= /
mandatory_question= / acknowledge= in reducer.py + conversation_policy.py
and pins the exact set. Adding a NEW hardcoded line fails this test —
put it in questions.py banks (PhraseSelect) instead. Fixing a branch by
adding a phrase in policy is the forbidden PR pattern (OPERATING_BRIEF).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.dialogue_engine

ROOT = Path(__file__).resolve().parents[1]
_FILES = [
    ROOT / "packages/dialogue_engine/reducer.py",
    ROOT / "packages/dialogue_engine/conversation_policy.py",
]
_KWARGS = {"text", "mandatory_question", "acknowledge"}

# Pinned 2026-09-27: singletons (mic/repair/ack) + plan texts already
# covered by behavior tests. Grow ONLY via questions.py banks.
PINNED_SPEECH = frozenset(
    {
        "Вас не слышно. Проверьте, пожалуйста, микрофон.",
        "Да, слышу. Повторите, пожалуйста.",
        "Не получается разобрать, я это запишу. Продолжим?",
        "Поняла вас. Спасибо, что рассказали.",
        "Поняла. Вы сегодня приняли лекарство, которое обычно должны принять?",
        "Расскажите подробнее, пожалуйста.",
        "Расскажите, пожалуйста, чуть подробнее.",
        "Скажите просто: хорошо, нормально или плохо?",
        "Скажите, что болит — голова, сердце, живот? Или что случилось?",
        "Хорошо, записала.",
    }
)


def _speech_literals() -> set[str]:
    found: set[str] = set()
    for path in _FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for kw in node.keywords:
                if kw.arg not in _KWARGS:
                    continue
                if isinstance(kw.value, ast.Constant) and isinstance(
                    kw.value.value, str
                ):
                    text = " ".join(kw.value.value.split())
                    if re.search(r"[А-Яа-яЁё]", text):
                        found.add(text)
    return found


def test_no_new_hardcoded_speech() -> None:
    live = _speech_literals()
    assert live == PINNED_SPEECH, (
        "new hardcoded Vera line outside questions.py banks: "
        f"{sorted(live ^ PINNED_SPEECH)}"
    )
