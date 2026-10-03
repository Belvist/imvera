"""Conservative sentence boundaries for opt-in batch TTS; text stays exact."""

from __future__ import annotations

import re

_ENDS = re.compile(r"[.!?…]+(?:[\"»”)]*)\s+")
_ABBREVIATIONS = frozenset({"табл", "млн", "млрд", "напр", "проф", "акад", "тел"})


def sentence_segments(text: str) -> list[str]:
    start = 0
    result = []
    for match in _ENDS.finditer(text):
        if match.group().startswith("."):
            previous = re.search(r"[\w.]+$", text[: match.start()])
            if previous is None:
                continue
            token = previous.group()
            if (
                len(token) <= 3
                or "." in token
                or token[-1].isdigit()
                or token.casefold() in _ABBREVIATIONS
            ):
                continue
        result.append(text[start : match.end()])
        start = match.end()
    if start < len(text):
        result.append(text[start:])
    return result or [text]
