"""Onset grounding for event-anchored answers (live 2026-09-13: fs-87312170).

User: «Живот болит после того, как покушал» → Vera: «Когда это началось?» →
user: «после того как покушал (макароны)» → engine grounded NOTHING, repeated
the question, then gave up with partial_unresolved_close.

Frozen rule: a meal/event anchor IS a grounded temporal answer. The engine
must accept «после X» / «как X», not only «утром/вечером».
"""

from __future__ import annotations

import pytest

from packages.dialogue_engine.events import CallStarted
from packages.dialogue_engine.issue_memory import extract_grounded_onset_value
from packages.dialogue_engine.scenario_runner import ScenarioRunner

pytestmark = pytest.mark.dialogue_engine


@pytest.mark.parametrize(
    "text",
    [
        "После того как покушал.",
        "После того как покушал макароны.",
        "После еды.",
        "После обеда.",
        "После ужина.",
        "Как покушал, так и заболел.",
        "Двадцать минут назад.",
        "Минут двадцать назад.",
        "С полчаса.",
        "Со вчерашнего дня.",
        "С утра.",
        # Live fs-8a64bac9: «позавчера начала болеть» was re-asked.
        "Позавчера начала болеть.",
        "Позавчера.",
        "Позапозавчера началось.",
        "Не знаю, позавчера начала болеть голова из-за магнитной бури.",
    ],
)
def test_after_event_answers_ground_onset(text: str) -> None:
    assert extract_grounded_onset_value(text) is not None


@pytest.mark.parametrize(
    "text",
    [
        "Колю покушал когда?",
        "Поднял.",
        "Не знаю.",
        "Покушал.",  # bare meal verb without после/как stays ungrounded
        "Хорошо.",
        "Нет.",
    ],
)
def test_garbage_and_bare_verbs_do_not_ground_onset(text: str) -> None:
    assert extract_grounded_onset_value(text) is None


def test_abdominal_food_anchored_onset_fills_and_advances() -> None:
    """Live shape: belly ache after meal → onset probe → «после ...» fills
    onset, next question is NOT temporal, call does not partially close."""
    r = ScenarioRunner(call_id="onset-after-meal", elder_display_name="Тест")
    r.run([CallStarted(), "Живот болит после того, как покушал."])
    intents = [e.intent for e in r.effects if getattr(e, "intent", None)]
    assert any("onset" in i or "current" in i for i in intents)
    result = r.run(["После того как покушал макароны."])
    intents = [e.intent for e in result.effects if getattr(e, "intent", None)]
    assert "partial_unresolved_close" not in intents
    abdominal = next(
        ep
        for ep in result.state.issue_episodes.values()
        if (ep.body_site or "") == "живот" or "живот" in (ep.primary_label or "")
    )
    onset = abdominal.known_attributes.get("onset") or abdominal.known_attributes.get(
        "duration"
    )
    assert onset is not None and "покушал" in onset.lower()
    # Next probe moved on (severity/current), temporal is not repeated.
    assert not any(
        getattr(e, "intent", "") in {"episode_abdominal_onset", "episode_onset"}
        for e in result.effects
    )


def test_live_ghost_episode_never_steals_floor() -> None:
    """Live fs-8a64bac9 shape: two real complaints + bare «болеть» echo in a
    refusal must not spawn a site-less ghost episode that steals the floor
    («когда это началось» for nothing). Head onset lands."""
    r = ScenarioRunner(call_id="ghost-episode", elder_display_name="Тест")
    r.run(
        [
            CallStarted(),
            "То ли голова болит, то ли жопа болит.",
            "Не знаю, позавчера начала болеть голова из-за магнитной бури.",
            "Я же говорю, не знаю, вчера, наверное, что-то из-за магнитной бури.",
        ]
    )
    labels = [ep.primary_label for ep in r.state.issue_episodes.values()]
    assert labels, "real complaints must create episodes"
    for ep in r.state.issue_episodes.values():
        label = (ep.primary_label or "").strip().lower()
        if not (ep.body_site or "").strip():
            assert label not in {
                "болит",
                "болят",
                "боль",
                "болеть",
                "беспокоит",
                "беспокоить",
            }, f"ghost episode: {label!r}"
    head = next(
        ep
        for ep in r.state.issue_episodes.values()
        if (ep.body_site or "") == "голова" or "голов" in (ep.primary_label or "")
    )
    assert head.known_attributes.get("onset") == "позавчера"
