"""Multi-symptom orientation — the product failure mode that kills demos.

Client: «голова + живот + тошнота» must stay steerable: no focus steal by
secondary symptoms mid-answer, «не знаю» must not hang up the call.
"""

from __future__ import annotations

import pytest

from packages.dialogue_engine.events import CallStarted
from packages.dialogue_engine.scenario_runner import ScenarioRunner

pytestmark = pytest.mark.dialogue_engine


def _runner() -> ScenarioRunner:
    return ScenarioRunner(call_id="multi-symptom", elder_display_name="Анна")


def _speak_intents(r: ScenarioRunner) -> list[str]:
    return [e.intent for e in r.effects if getattr(e, "intent", None)]


def test_multi_symptom_does_not_hang_on_ne_znayu() -> None:
    r = _runner()
    r.run(
        [
            CallStarted(),
            "У меня болит голова, живот болит и меня тошнит.",
            "С утра уже.",
            "Сильно.",
            "Да, тошнит.",
            "Живот ещё болит.",
            "Не знаю.",
        ]
    )
    intents = _speak_intents(r)
    assert "partial_unresolved_close" not in intents
    last = [e for e in r.effects if getattr(e, "text", None)][-1]
    assert "не получилось узнать" not in last.text.lower()


def test_nausea_mid_answer_does_not_steal_stomach_focus() -> None:
    r = _runner()
    r.run(
        [
            CallStarted(),
            "У меня болит голова, живот болит и меня тошнит.",
            "С утра уже.",
            "Сильно.",
        ]
    )
    # Frozen contract: mentioned nausea is acknowledged, not probed as a
    # mandatory associated step and never becomes a new primary episode.
    # Stomach focus is kept via the abdomen current question.
    assert "episode_headache_associated" not in _speak_intents(r)
    assert any(i.endswith("_current") for i in _speak_intents(r))
    r.run(["Да, тошнит."])
    assert "partial_unresolved_close" not in _speak_intents(r)
    nausea_primaries = [
        ep
        for ep in r.state.issue_episodes.values()
        if "тошн" in (ep.primary_label or "").lower()
    ]
    assert not nausea_primaries
    assert "important_to_share" in _speak_intents(r)


def test_multi_symptom_reaches_important_to_share_or_warm_close() -> None:
    r = _runner()
    r.run(
        [
            CallStarted(),
            "У меня болит голова, живот болит и меня тошнит.",
            "С утра.",
            "Терпимо.",
            "Ещё тошнит.",
            "Ещё болит.",
            "Не знаю.",
        ]
    )
    intents = _speak_intents(r)
    assert "partial_unresolved_close" not in intents
    # Frozen contract: no mandatory associated probe (needs an ADR).
    assert "episode_headache_associated" not in intents
    assert (
        "important_to_share" in intents
        or "summary" in intents
        or r.state.important_to_share_asked
        or r.state.summary_spoken
    )
    if "summary" in intents:
        assert "записала" in " ".join(
            e.text.lower() for e in r.effects if getattr(e, "text", None)
        )
