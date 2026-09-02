"""DTMF fallback for hard-of-hearing / low-confidence turns (ROADMAP E2)."""

from enum import Enum


DTMF_PROMPT = (
    "Если всё хорошо — нажмите 1, если нужна помощь — нажмите 2."
)

# Offer after this many consecutive empty / low_conf turns (inclusive).
DTMF_AFTER_EMPTY_TURNS = 2


class DtmfEvent(Enum):
    OK = "ok"
    HELP = "help"
    UNKNOWN = "unknown"


def interpret_dtmf(digit) -> DtmfEvent:
    """Map a single DTMF digit to a dialogue event.

    1 = wellbeing OK, 2 = help / danger signal. Other digits ignored.
    """
    raw = str(digit or "").strip()
    if not raw:
        return DtmfEvent.UNKNOWN
    # FreeSWITCH may pass "1", "DTMF 1", or "#1" — take the first digit char.
    for ch in raw:
        if ch.isdigit():
            if ch == "1":
                return DtmfEvent.OK
            if ch == "2":
                return DtmfEvent.HELP
            return DtmfEvent.UNKNOWN
    return DtmfEvent.UNKNOWN


def should_offer_dtmf(empty_turns: int) -> bool:
    return int(empty_turns or 0) >= DTMF_AFTER_EMPTY_TURNS
