"""Terminal close must hang up — frozen contract (ADR-014).

Regression for: Vera says «До свидания» but call never ends / summary loops.

Frozen close path: summary → user farewell → goodbye_final → exactly one
EndCall. Summary alone never hangs up (that was reverted: hangup-on-summary
broke the corpus goodbye_final gates).
"""

from __future__ import annotations

import pytest

from packages.dialogue_engine.effects import EndCallEffect, SpeakEffect
from packages.dialogue_engine.events import CallStarted
from packages.dialogue_engine.scenario_runner import ScenarioRunner

pytestmark = pytest.mark.dialogue_engine


def _summaries(effects: list) -> list[SpeakEffect]:
    return [e for e in effects if isinstance(e, SpeakEffect) and e.intent == "summary"]


def _end_calls(effects: list) -> list[EndCallEffect]:
    return [e for e in effects if isinstance(e, EndCallEffect)]


def _goodbyes(effects: list) -> list[SpeakEffect]:
    return [e for e in effects if isinstance(e, SpeakEffect) and e.intent == "goodbye_final"]


def test_happy_path_goodbye_hangs_up_once() -> None:
    r = ScenarioRunner(call_id="hangup-happy", elder_display_name="Егор")
    result = r.run([CallStarted(), "Нормально.", "Нет.", "До свидания."])
    assert len(_goodbyes(result.effects)) == 1
    ends = _end_calls(result.effects)
    assert len(ends) == 1
    assert ends[0].reason == "goodbye"
    assert result.state.call_closed is True
    assert result.state.goodbye_confirmed is True


def test_after_goodbye_further_user_turns_are_ignored() -> None:
    r = ScenarioRunner(call_id="hangup-ignore", elder_display_name="Егор")
    r.run([CallStarted(), "Нормально.", "Нет.", "До свидания."])
    assert r.state.call_closed
    before = len(r.effects)
    r.run(["Нет.", "Алло.", "До свидания."])
    assert len(r.effects) == before
    assert len(_goodbyes(r.effects)) == 1
    assert len(_end_calls(r.effects)) == 1


def test_headache_resolve_then_farewell_hangs_up() -> None:
    r = ScenarioRunner(call_id="hangup-headache", elder_display_name="Егор")
    result = r.run(
        [
            CallStarted(),
            "Голова болит с утра.",
            "Сейчас уже полегче.",
            "Нет.",
            "До свидания.",
        ]
    )
    assert result.state.call_closed
    assert len(_summaries(result.effects)) == 1
    assert len(_goodbyes(result.effects)) == 1
    assert len(_end_calls(result.effects)) == 1


def test_partial_close_also_hangs_up() -> None:
    """Vague answers must still terminate the call (warm summary or partial close)."""
    r = ScenarioRunner(call_id="hangup-partial", elder_display_name="Егор")
    result = r.run([CallStarted(), "Ну так.", "Не знаю.", "До свидания."])
    speaks = [e for e in result.effects if isinstance(e, SpeakEffect)]
    intents = [e.intent for e in speaks]
    terminal = [
        e
        for e in speaks
        if e.intent in {"partial_unresolved_close", "summary"}
    ]
    assert terminal, intents
    assert result.state.call_closed
    assert _end_calls(result.effects), "terminal speak must EndCall after playout"
