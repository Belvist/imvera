"""Critical-concern ladder — WHAT hurts before any verdict (user directive).

- «очень плохо»/«плохо» without a complaint → concern probe first, never
  the routine ladder (meds/food) and never an instant close.
- bare red state («умираю» without a site) → probe → options → urgent with
  concern explicitly marked unspecified (asked twice, never assumed).
- red state WITH a site («сердце болит, умираю») or red action
  («падаю», «задыхаюсь») → immediate urgent, no clarification.
- movie/news context defuses (no symptom) — normal flow resumes, and later
  closes must NOT escalate on the withdrawn cry.
"""

from __future__ import annotations

import pytest

from packages.dialogue_engine.effects import SpeakEffect
from packages.dialogue_engine.events import CallStarted
from packages.dialogue_engine.scenario_runner import ScenarioRunner


@pytest.fixture(autouse=True)
def _pilot_ladder(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMVERA_COVERAGE_LADDER", "1")


def run(turns: list) -> tuple[ScenarioRunner, list[str]]:
    r = ScenarioRunner(call_id="crit", elder_display_name="Тест")
    intents: list[str] = []
    for t in turns:
        res = r.run([t])
        for e in res.speak_effects:
            assert isinstance(e, SpeakEffect)
            intents.append(e.intent)
    return r, intents


def test_bad_probes_concern_before_ladder():
    _, intents = run([CallStarted(), "Плохо.", "Голова болит."])
    assert intents[1] == "probe_concern"
    assert "background_medication" not in intents[:2]
    assert "background_nutrition" not in intents[:2]


def test_bare_dying_clarifies_then_unspecified_urgent():
    r, intents = run([CallStarted(), "Я умираю.", "Не знаю.", "Не могу сказать."])
    assert intents[1] == "probe_concern"
    assert intents[2] == "probe_concern_options"
    assert intents[3] == "urgent_close"
    assert r.state.closing_reason == "urgent"
    assert r.state.observations.get("concern_status") == "unspecified"


def test_dying_with_site_closes_at_once():
    r, intents = run([CallStarted(), "Сердце болит, я умираю."])
    assert intents[1] == "urgent_close"
    assert r.state.call_closed


def test_falling_closes_at_once():
    r, intents = run([CallStarted(), "Я падаю, мне плохо."])
    assert intents[1] == "urgent_close"


def test_movie_defuses():
    r, intents = run(
        [CallStarted(), "Я умираю.", "Да в фильме там убили, переживаю.",
         "Нормально.", "Пока."]
    )
    assert intents[1] == "probe_concern"
    assert "urgent_close" not in intents
    assert r.state.observations.get("concern_status", "").startswith("defused")
    assert r.state.call_closed


def test_concern_answer_opens_episode_not_ladder():
    _, intents = run(
        [CallStarted(), "Мне очень плохо.", "Голова болит.", "С утра.", "Терпимо."]
    )
    assert intents[1] == "probe_concern"
    assert any("headache" in i or "episode" in i for i in intents)
