"""Urgent safety: emergency verbs hijack any dialogue state (live fs-41e2a57b).

«Сердце болит, я падаю, теряю сознание» must route to urgent_close —
never probe, never partial_unresolved_close.
"""

from __future__ import annotations

import pytest

from packages.dialogue_engine.check_path import is_urgent_concern
from packages.dialogue_engine.effects import EndCallEffect, SpeakEffect
from packages.dialogue_engine.events import CallStarted
from packages.dialogue_engine.scenario_runner import ScenarioRunner

pytestmark = pytest.mark.dialogue_engine


@pytest.mark.parametrize(
    "text",
    [
        "Сердце болит, я падаю, мне плохо, теряю сознание.",
        "Сейчас, я же говорю, я сейчас умру, я задыхаюсь уже.",
        "Упал и не могу встать.",
        "Вызовите скорую.",
        "Сердце давит.",
    ],
)
def test_emergency_verbs_are_urgent(text: str) -> None:
    assert is_urgent_concern(text)


@pytest.mark.parametrize(
    "text",
    [
        "Голова болит.",
        "С утра.",
        "Терпимая.",
        "Давление померила вчера.",
    ],
)
def test_ordinary_pain_is_not_urgent(text: str) -> None:
    assert not is_urgent_concern(text)


def _intents(r: ScenarioRunner) -> list[str]:
    return [e.intent for e in r.effects if isinstance(e, SpeakEffect)]


def test_emergency_mid_probing_goes_urgent_close() -> None:
    r = ScenarioRunner(call_id="urgent-mid", elder_display_name="Тест")
    r.run([CallStarted(), "Живот болит."])
    result = r.run(["Сердце болит, я падаю, мне плохо, теряю сознание."])
    intents = _intents(r)
    assert "urgent_close" in intents
    assert "partial_unresolved_close" not in intents
    assert result.state.call_closed
    assert result.state.closing_reason == "urgent"
    assert any(isinstance(e, EndCallEffect) for e in result.effects)


def test_skoraya_request_goes_urgent_close() -> None:
    r = ScenarioRunner(call_id="urgent-skoraya", elder_display_name="Тест")
    r.run([CallStarted(), "Голова болит.", "С утра."])
    result = r.run(["Вызовите скорую."])
    assert "urgent_close" in _intents(r)
    assert "partial_unresolved_close" not in _intents(r)
    assert result.state.call_closed
