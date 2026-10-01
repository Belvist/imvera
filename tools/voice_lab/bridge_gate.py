"""Offline surface-validation experiment (retired from live SDK, ADR-025).

Historical Cut 1 validator for surface experiments. It compares a candidate
bridge to source evidence; it never speaks, mutates state or loads a model.
Production SDK delivery does not import this module or generate bridges.
"""

from __future__ import annotations

import re

MAX_BRIDGE_WORDS = 25

# The bridge must not ask (the question's job), promise, or verdict.
_QUESTION_MARK = "?"
_PROMISES = re.compile(r"(вызову|приеду|гарантирую|обещаю|позвоню\s+врачу)", re.I)
_VERDICTS = re.compile(r"(зел[её]н|красн|ж[её]лт|статус\s+звонка)", re.I)
_ASK_VERBS = re.compile(r"(скажите|расскажите|ответьте|повторите|вспомните)", re.I)
# The bridge is one acknowledgment, not a second move (measured Qwen failure:
# «…тяжело. Нужно проверить, как вы чувствуетесь» — adds an obligation move).
_EXTRA_MOVE = re.compile(
    r"(нужно|надо|давайте|следует|стоит|будем|сейчас)\s+"
    r"(проверить|узнать|уточнить|выяснить|разобраться|посмотреть)",
    re.I,
)
_CYRILLIC = re.compile(r"[а-яёА-ЯЁ]")

_STOPWORDS = frozenset(
    {
        "и", "в", "во", "не", "что", "он", "на", "я", "с", "со", "как", "а", "то",
        "все", "она", "так", "его", "но", "да", "ты", "к", "у", "же", "вы",
        "за", "бы", "по", "только", "ее", "мне", "было", "вот", "от", "меня",
        "еще", "ещё", "нет", "о", "из", "ему", "теперь", "когда", "даже", "ну",
        "вдруг", "ли", "если", "уже", "или", "ни", "быть", "был", "него", "до",
        "вас", "нибудь", "опять", "это", "понимаю", "поняла", "понятно", "хорошо",
        "ага", "угу", "да", "нет",
    }
)


def _content_words(text: str) -> set[str]:
    words = re.findall(r"[а-яёa-z]+", text.lower())
    return {w for w in words if w not in _STOPWORDS and len(w) > 2}


def validate_bridge(
    candidate: str,
    *,
    original_bridge: str,
    user_text: str,
    last_vera_line: str = "",
) -> tuple[bool, str]:
    """Return (ok, reason). `ok` True only when the candidate may be spoken."""
    text = (candidate or "").strip().rstrip(".!?…")
    if not text:
        return False, "empty"
    if not _CYRILLIC.search(text):
        return False, "not_russian"
    if _QUESTION_MARK in candidate:
        return False, "has_question_mark"
    if len(text.split()) > MAX_BRIDGE_WORDS:
        return False, "too_long"
    if _PROMISES.search(text):
        return False, "promise"
    if _VERDICTS.search(text):
        return False, "verdict"
    if _ASK_VERBS.search(text):
        return False, "ask_verb"
    if _EXTRA_MOVE.search(text):
        return False, "extra_move"
    # Grounding: the bridge must share at least one content word with what the
    # person just said or with the deterministic bridge it replaces. Measured
    # failure it rejects: «Нужно проверить, как вы чувствуетесь» for
    # user «Сильно болит» + bridge «Понимаю, сильная боль — это тяжело».
    anchor = _content_words(user_text) | _content_words(original_bridge)
    if anchor and not (_content_words(text) & anchor):
        return False, "ungrounded"
    if last_vera_line:
        prev = last_vera_line.strip().rstrip(".!?…").lower()
        if prev and prev == text.lower():
            return False, "parrot"
    return True, "ok"
