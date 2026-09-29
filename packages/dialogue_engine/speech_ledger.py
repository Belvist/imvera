"""Per-call speech ledger — the systematic end of verbatim repeats.

Every Vera surface funnels through ``_emit_speak``; the ledger records the
normalized text there. Record-only by design: a verbatim re-ask after a
non-answer is legitimate (exhaustion-close accounting depends on it), so
the ledger never diverts — repeats are fixed at the decision layer per
site (e.g. topic skip-on-repeat), and ``tests/test_speech_discipline.py``
fails the build on repeats and content-free standalone acks found in
banks and live flows.

Normalization is exact (lowercase, punctuation/whitespace collapsed) — no
fuzzy matching, so a rephrased question always passes.
"""

from __future__ import annotations

import re
import unicodedata

_MAX_ENTRIES = 60

# Content-free as a WHOLE response. Listener signals containing
# «слушаю»/«слышу» are whitelisted separately (backchannel, not an answer).
BANNED_STANDALONE = frozenset(
    {
        "поняла вас",
        "поняла",
        "понятно",
        "ясно",
        "хорошо",
        "ладно",
        "записала",
        "ага",
        "угу",
        "да",
        "нет",
    }
)

_LISTENER_RE = re.compile(r"слушаю|слышу", re.I)


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", (text or "").lower())
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def record(spoken: list[str], text: str) -> list[str]:
    """Append a normalized surface, capped. Pure: returns the new list."""
    norm = normalize(text)
    if not norm:
        return spoken
    out = [*spoken, norm]
    return out[-_MAX_ENTRIES:]


def is_verbatim_repeat(spoken: list[str], text: str) -> bool:
    norm = normalize(text)
    return bool(norm) and norm in spoken


def is_banned_standalone(text: str) -> bool:
    """A whole Vera turn with no content (not a listener backchannel)."""
    norm = normalize(text)
    if not norm or _LISTENER_RE.search(norm):
        return False
    return norm in BANNED_STANDALONE
