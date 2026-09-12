"""Dialogue quality: few right questions — headache, multi-issue, good path."""

from __future__ import annotations

import pytest

from packages.dialogue_engine.events import CallStarted
from packages.dialogue_engine.scenario_runner import ScenarioRunner

pytestmark = pytest.mark.dialogue_engine


def _runner() -> ScenarioRunner:
    return ScenarioRunner(call_id="q-quality", elder_display_name="Егор")


def _vera(r: ScenarioRunner) -> list[tuple[str, str]]:
    return [
        (e.intent, e.text)
        for e in r.effects
        if getattr(e, "text", None) and e.intent != "opening_wellness"
    ]


def test_active_headache_no_double_current_ask() -> None:
    """«Голова болит» → когда → severity → associated; never compound «а сейчас»."""
    r = _runner()
    r.run(
        [
            CallStarted(),
            "Голова болит.",
            "С утра.",
            "Терпимая.",
            "Ничего больше.",
            "Нет.",
        ]
    )
    intents = [i for i, _ in _vera(r)]
    assert "episode_compound_temporal_current" not in intents
    assert intents.count("episode_headache_current") == 0
    assert "episode_headache_duration" in intents or any(
        "давно" in t.lower() or "когда" in t.lower() for _, t in _vera(r)
    )
    assert "episode_headache_severity" in intents
    assert "episode_headache_associated" in intents
    ep = next(iter(r.state.issue_episodes.values()))
    assert ep.known_attributes.get("current") == "active"
    assert ep.status == "resolved" or r.state.call_closed or r.state.important_to_share_asked


def test_past_morning_headache_asks_trend_once() -> None:
    r = _runner()
    r.run(
        [
            CallStarted(),
            "Хорошо, на утро голова болела.",
            "Сейчас уже полегче.",
            "Нет.",
        ]
    )
    vera = _vera(r)
    currents = [t for i, t in vera if i == "episode_headache_current"]
    assert len(currents) == 1
    assert "а сейчас" in currents[0].lower()
    assert "episode_headache_severity" not in [i for i, _ in vera]
    assert any(i == "important_to_share" for i, _ in vera)
    assert "важн" in next(t for i, t in vera if i == "important_to_share").lower()


def test_multi_problem_finishes_head_then_sleep_pack_not_dumb_onset() -> None:
    """Head + sleep: finish head pack; sleep uses pattern — never dumb «как давно сон»."""
    r = _runner()
    r.run(
        [
            CallStarted(),
            "Голова болит и плохо спал.",
            "С утра.",
            "Терпимая.",
            "Только это.",
        ]
    )
    vera = _vera(r)
    texts = " ".join(t.lower() for _, t in vera)
    assert "как давно плохой сон" not in texts
    assert "как давно это продолжается" not in texts
    assert any(
        i
        in (
            "important_to_share",
            "episode_sleep_pattern",
            "episode_sleep_daytime_impact",
            "episode_headache_associated",
        )
        for i, _ in vera
    )
    head = next(ep for ep in r.state.issue_episodes.values() if "голов" in ep.primary_label)
    assert head.status == "resolved" or "associated" in head.known_attributes
    sleep = next(
        ep for ep in r.state.issue_episodes.values() if ep.kind == "sleep_problem"
    )
    assert sleep.known_attributes.get("quality") == "poor"


def test_good_scenario_few_turns() -> None:
    """Всё хорошо → important (MVP wording) → close; no issue spam."""
    r = _runner()
    r.run([CallStarted(), "Нормально, всё хорошо.", "Нет."])
    vera = _vera(r)
    intents = [i for i, _ in vera]
    assert intents[0] == "important_to_share"
    assert "важн" in vera[0][1].lower()
    assert "summary" in intents
    assert not any(i.startswith("episode_") for i in intents)


def test_good_simple_normaльно() -> None:
    r = _runner()
    r.run([CallStarted(), "Нормально.", "Нет."])
    intents = [i for i, _ in _vera(r)]
    assert "important_to_share" in intents
    assert "summary" in intents
    assert not any("severity" in i for i in intents)
