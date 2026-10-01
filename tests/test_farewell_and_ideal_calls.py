"""Farewell battery + ideal end-to-end calls.

Every farewell form must close the call with a single spoken goodbye.
Ideal calls run greeting → ... → summary (no farewell inside) →
goodbye_final, exactly once.
"""

from __future__ import annotations

import pytest

from packages.dialogue_engine.events import CallStarted
from packages.dialogue_engine.scenario_runner import ScenarioRunner

pytestmark = pytest.mark.dialogue_engine

FAREWELLS = [
    "До свидания.",
    "Всего доброго.",
    "Пока.",
    "Ладно, пока.",
    "Ну пока.",
    "Ну давай.",
    "Прощайте.",
    "До встречи.",
    "Закончим.",
    "Хватит.",
]


@pytest.mark.parametrize("farewell", FAREWELLS, ids=FAREWELLS)
def test_farewell_form_closes_with_single_goodbye(farewell: str) -> None:
    r = ScenarioRunner(call_id="fw", elder_display_name="Тест")
    result = r.run([CallStarted(), "Хорошо.", farewell])
    assert r.state.call_closed, farewell
    goodbyes = [
        e for e in result.speak_effects if e.intent == "goodbye_final"
    ]
    assert len(goodbyes) == 1, farewell
    assert "До свидания" in goodbyes[0].text, farewell


def test_poka_vsyo_after_summary_closes_once() -> None:
    # «Пока всё» after the summary is a natural end: one summary, then
    # one goodbye — never a hang without summary, never two goodbyes.
    r = ScenarioRunner(call_id="fw-decline", elder_display_name="Тест")
    result = r.run(
        [
            CallStarted(),
            "Голова болит.",
            "С утра.",
            "Терпимо.",
            "Нет.",
            "Пока всё.",
        ]
    )
    intents = [e.intent for e in result.speak_effects]
    assert intents.count("summary") == 1
    assert intents.count("goodbye_final") == 1
    assert intents.index("summary") < intents.index("goodbye_final")


def _summary_texts(result) -> list[str]:
    return [e.text for e in result.speak_effects if e.intent == "summary"]


@pytest.mark.parametrize(
    "flow",
    [
        ["Хорошо.", "Нет, ничего такого.", "До свидания."],
        ["Хорошо.", "Поела, таблетки приняла.", "Нет, ничего.", "До свидания."],
    ],
    ids=["short", "with-meds"],
)
def test_ideal_healthy_call(flow: list[str]) -> None:
    r = ScenarioRunner(call_id="ideal-good", elder_display_name="Анна")
    result = r.run([CallStarted(), *flow])
    assert r.state.call_closed
    summaries = _summary_texts(result)
    assert len(summaries) == 1
    assert "до свидания" not in summaries[0].lower()
    goodbyes = [e for e in result.speak_effects if e.intent == "goodbye_final"]
    assert len(goodbyes) == 1
    # no interrogation markers in a healthy call
    joined = " ".join(e.text for e in result.speak_effects).lower()
    assert "не расслышала" not in joined


def test_ideal_complaint_call_elder_words() -> None:
    r = ScenarioRunner(call_id="ideal-pain", elder_display_name="Анна")
    result = r.run(
        [
            CallStarted(),
            "Поясницу ломит.",
            "Со вчерашнего вечера.",
            "Терпимо.",
            "Нет, больше ничего.",
            "До свидания.",
        ]
    )
    assert r.state.call_closed
    assert r.state.issue_episodes, "episode must be on record"
    summaries = _summary_texts(result)
    assert len(summaries) == 1
    assert "поясниц" in summaries[0].lower()
    assert "до свидания" not in summaries[0].lower()
    goodbyes = [e for e in result.speak_effects if e.intent == "goodbye_final"]
    assert len(goodbyes) == 1
    joined = " ".join(e.text for e in result.speak_effects).lower()
    assert "не расслышала" not in joined
