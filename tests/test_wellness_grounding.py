"""Wellness grounding end-to-end (reporter table, pilot path).

One coherent segment: answer → recorded state → justified next action.
- substantive general assessment without complaint → concern probe
- garbage / "не знаю" / other-person-only → slot stays OPEN (re-ask)
- positive → routine ladder; mixed subjects stay separated
"""

from __future__ import annotations

import pytest

from packages.contracts.enums import SlotStatus
from packages.dialogue_engine.events import CallStarted
from packages.dialogue_engine.mission import daily_check_mission
from packages.dialogue_engine.mission_seed import apply_mission_to_state
from packages.dialogue_engine.scenario_runner import ScenarioRunner

pytestmark = pytest.mark.dialogue_engine


@pytest.fixture(autouse=True)
def _pilot_ladder(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMVERA_COVERAGE_LADDER", "1")


def _run(text: str):
    r = ScenarioRunner(call_id="well", elder_display_name="Тест")
    apply_mission_to_state(r.state, daily_check_mission())
    r.run([CallStarted()])
    res = r.run([text])
    return r, [e.intent for e in res.speak_effects]


@pytest.mark.parametrize(
    "text",
    [
        "по состоянию мне более-менее",
        "мне так себе",
        "плохо",
        "ни шатко ни валко",
        "кое-как",
        "помаленьку",
    ],
)
def test_substantive_nonpositive_probes_concern(text: str) -> None:
    r, intents = _run(text)
    assert intents == ["probe_concern"]
    assert r.state.slots["wellness"] == SlotStatus.FILLED
    assert r.state.slot_records["wellness"].polarity in ("negative", "uncertain")


@pytest.mark.parametrize("text", ["абракадабра", "не знаю", "у мужа плохо"])
def test_nonsubstantive_keeps_slot_open(text: str) -> None:
    r, intents = _run(text)
    assert r.state.slots["wellness"] == SlotStatus.OPEN
    assert "wellness" not in r.state.slot_records
    assert "background_nutrition" not in intents
    assert "background_medication" not in intents


def test_positive_allows_ladder() -> None:
    r, intents = _run("хорошо")
    assert intents == ["background_nutrition"]
    assert r.state.slot_records["wellness"].polarity == "positive"


def test_mixed_subjects_split() -> None:
    r, intents = _run("у мужа плохо, а у меня более-менее")
    assert intents == ["probe_concern"]
    rec = r.state.slot_records["wellness"]
    assert "муж" not in rec.value.lower()
    assert "мужа" not in rec.source_text.lower()
