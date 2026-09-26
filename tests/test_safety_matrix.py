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
    "умираю",
    "ой, умираю, плохо умираю",
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


def test_safety_interrupt_on_explicit_request_closes_at_once() -> None:
    """Live fs-f93eb308: explicit request ("вызовите скорую") closes at
    once; descriptive matches clarify first with a specific echo."""
    from packages.dialogue_engine.engine import DialogueEngine
    from packages.dialogue_engine.events import SafetyInterrupt
    from packages.dialogue_engine.reducer import reduce

    engine = DialogueEngine(call_id="sic", elder_display_name="Тест")
    engine.start()
    state, effects = reduce(
        engine.state,
        SafetyInterrupt(
            level="RED",
            quote="Ой, вызовите скорую.",
            revision=engine.state.revision,
        ),
    )
    speaks = [e for e in effects if getattr(e, "kind", "") == "speak"]
    assert speaks, "explicit request must speak urgent close"

    engine2 = DialogueEngine(call_id="sic2", elder_display_name="Тест")
    engine2.start()
    state2, effects2 = reduce(
        engine2.state,
        SafetyInterrupt(
            level="RED", quote="Ой, сердце колет.", revision=engine2.state.revision
        ),
    )
    speaks2 = [e for e in effects2 if getattr(e, "kind", "") == "speak"]
    assert speaks2, "descriptive match must clarify, not stall"
    assert "сердце колет" in speaks2[0].text
    assert "Расскажите, что произошло" not in speaks2[0].text
