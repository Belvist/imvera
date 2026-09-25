"""Safety detector matrix: both detectors, guards, no divergence.

P0 audit: consciousness was invisible, negation triggered RED, cardiac
fragmented, husband's fall gave RED, yesterday's fall gave RED, imperatives
diverged. Every row asserts ENGINE (check_path) and LEGACY (safety.rules)
together — one fix lands in both via packages/safety/patterns.py.
"""

from __future__ import annotations

import pytest

from packages.dialogue_engine.check_path import is_urgent_action, is_urgent_state
from packages.safety.rules import match_deterministic_signals

pytestmark = pytest.mark.dialogue_engine


def engine_red(text: str) -> bool:
    return bool(is_urgent_action(text) or is_urgent_state(text))


def legacy_red(text: str) -> bool:
    from packages.safety.rules import signal_to_risk_level

    return any(
        signal_to_risk_level(s) == "RED"
        for s in match_deterministic_signals(text)
    )


URGENT_BOTH = [
    "упала",
    "упал",
    "помогите",
    "спасите",
    "вызовите скорую",
    "вызывайте скорую",
    "кровь идёт",
    "задыхаюсь",
    "не могу дышать",
    "инфаркт",
    "потеряла сознание",
    "теряю сознание",
    "без сознания",
    "сердце болит",
    "сердце давит",
    "боль в груди",
    "давление 200",
    "упала, вызовите скорую",
    "упала вчера, лежу не могу встать",
]

NOT_URGENT_BOTH = [
    "я не упала",
    "не падала",
    "не надо скорую",
    "муж упал",
    "у мужа упала",
    "соседка упала",
    "упала вчера",
    "упала вчера, сейчас всё хорошо",
    "сердце ноет от тоски",
    "давление поднялось",
    "пьёт таблетки от давления",
    "хорошо себя чувствую",
    "голова болит",
    "поела, всё вкусно",
]


@pytest.mark.parametrize("text", URGENT_BOTH)
def test_urgent_detected_by_both(text: str) -> None:
    assert engine_red(text), f"engine miss: {text!r}"
    assert legacy_red(text), f"legacy miss: {text!r}"


@pytest.mark.parametrize("text", NOT_URGENT_BOTH)
def test_not_urgent_in_either(text: str) -> None:
    assert not engine_red(text), f"engine false RED: {text!r}"
    assert not legacy_red(text), f"legacy false RED: {text!r}"
