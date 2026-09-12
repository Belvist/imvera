"""Terminal close must hang up — MVP NORMAL_CLOSE parity.

Regression for: Vera says «До свидания» but call never ends / summary loops.
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


def test_happy_path_summary_hangs_up_once() -> None:
    r = ScenarioRunner(call_id="hangup-happy", elder_display_name="Егор")
    result = r.run([CallStarted(), "Нормально.", "Нет."])
    summaries = _summaries(result.effects)
    ends = _end_calls(result.effects)
    assert len(summaries) == 1, [e.intent for e in result.effects if isinstance(e, SpeakEffect)]
    assert len(ends) == 1
    assert ends[0].reason in {"complete", "summary"}
    assert result.state.call_closed is True
    assert result.state.summary_spoken is True


def test_after_summary_further_user_turns_are_ignored() -> None:
    r = ScenarioRunner(call_id="hangup-ignore", elder_display_name="Егор")
    r.run([CallStarted(), "Нормально.", "Нет."])
    assert r.state.call_closed
    before = len(r.effects)
    r.run(["Нет.", "Алло.", "До свидания."])
    assert len(r.effects) == before
    assert len(_summaries(r.effects)) == 1
    assert len(_end_calls(r.effects)) == 1


def test_headache_resolve_then_decline_hangs_up() -> None:
    r = ScenarioRunner(call_id="hangup-headache", elder_display_name="Егор")
    result = r.run(
        [
            CallStarted(),
            "Голова болит с утра.",
            "Сейчас уже полегче.",
            "Нет.",
        ]
    )
    assert result.state.call_closed
    assert len(_summaries(result.effects)) == 1
    assert len(_end_calls(result.effects)) == 1


def test_partial_close_also_hangs_up() -> None:
    """Vague answers must still terminate the call (warm summary or partial close)."""
    r = ScenarioRunner(call_id="hangup-partial", elder_display_name="Егор")
    result = r.run([CallStarted(), "Ну так.", "Не знаю.", "Ага.", "Алло."])
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
