"""Accepted information, not number of check-slot replies, ends optional screening."""
from __future__ import annotations

import copy

import pytest

from packages.contracts.enums import SlotStatus
from packages.dialogue_engine.coverage import coverage_met, covered_domains
from packages.dialogue_engine.events import CallStarted
from packages.dialogue_engine.scenario_runner import ScenarioRunner

pytestmark = pytest.mark.dialogue_engine


@pytest.fixture(autouse=True)
def flags(monkeypatch):
    for name, value in {
        "IMVERA_DIALOGUE_ENGINE": "1", "IMVERA_COVERAGE_LADDER": "1",
        "IMVERA_ACTION_POLICY_MODE": "off", "IMVERA_LLM_INTERPRET": "0",
        "IMVERA_MISSION_LLM_INTERPRET": "0",
    }.items():
        monkeypatch.setenv(name, value)


@pytest.mark.parametrize("texts", [
    ["Мне хорошо. Сегодня поела, таблетки уже приняла."],
    ["Мне хорошо. Сегодня не ела. Таблетки не принимаю."],
    ["Хорошо.", "Поела.", "Нет."],
])
def test_sufficient_facts_yield_an_invitation_without_optional_mood_sleep_questions(texts):
    runner = ScenarioRunner(call_id="information-sufficient")
    runner.run([CallStarted()])
    for text in texts:
        result = runner.run([text])
    assert {"wellbeing", "nutrition", "medication"} <= covered_domains(runner.state)
    assert coverage_met(runner.state)
    assert result.speak_effects[-1].intent == "important_to_share"
    assert runner.state.slots["mood"] == SlotStatus.OPEN
    assert runner.state.slots["sleep"] == SlotStatus.OPEN
    assert not runner.state.call_closed


def test_early_invitation_keeps_an_engaged_story_and_then_yields_to_summary():
    runner = ScenarioRunner(call_id="sufficient-story")
    result = runner.run([CallStarted(),
                        "Мне хорошо. Сегодня поела, таблетки уже приняла."])
    assert result.speak_effects[-1].intent == "important_to_share"
    facts = copy.deepcopy(runner.state.coverage_records)
    for text in [
        "Вчера дочь приехала, мы смотрели фотографии.",
        "Долго сидели и вспоминали дачу.",
        "А потом пили чай и смеялись.",
        "Она рассказала про поездку к морю.",
        "Обсуждали фотографии с нашей прошлой поездки.",
        "Вспоминали, как гуляли по набережной вместе.",
        "Потом вспоминали нашу дачу и летние вечера.",
        "Рассматривали старые фотографии из поездки.",
    ]:
        result = runner.run([text])
        assert not runner.state.call_closed
        assert runner.state.important_to_share_resolved
        assert runner.state.coverage_records == facts
        assert result.speak_effects and all(not e.marks_question for e in result.speak_effects)
    result = runner.run(["Нет, ничего."])
    assert result.speak_effects[-1].intent == "summary"
    assert not runner.state.call_closed


def test_sufficient_optional_coverage_does_not_discharge_an_explicit_required_goal():
    runner = ScenarioRunner(call_id="required-sleep")
    runner.state.required_background_goals = {"sleep"}
    runner.run([CallStarted(), "Мне хорошо. Сегодня поела, таблетки уже приняла."])
    assert coverage_met(runner.state)
    assert runner.state.background_goal_needs_attention("sleep")
    result = runner.run(["Нет, ничего."])
    assert not runner.state.call_closed
    assert any(e.slot == "sleep" and e.marks_question for e in result.speak_effects)


@pytest.mark.parametrize("report", [
    "Дочь сегодня поела, таблетки уже приняла.",
    "Вчера поела, таблетки приняла.",
    "Может быть, сегодня поела, таблетки уже приняла.",
])
def test_unaccepted_routine_reports_do_not_remove_the_remaining_information_need(report):
    runner = ScenarioRunner(call_id="unaccepted-coverage")
    result = runner.run([CallStarted(), "Мне хорошо. " + report])
    assert not coverage_met(runner.state)
    assert "nutrition" not in covered_domains(runner.state)
    assert result.speak_effects[-1].intent != "important_to_share"


@pytest.mark.parametrize("text,domain", [
    ("Не помню.", "nutrition"), ("Не хочу отвечать.", "nutrition"),
])
def test_unknown_or_refusal_is_not_a_known_domain(text, domain):
    runner = ScenarioRunner(call_id="sufficient-disposition")
    runner.run([CallStarted(), "Хорошо.", text])
    assert domain not in covered_domains(runner.state)
    assert not coverage_met(runner.state)


@pytest.mark.parametrize("text,intent", [
    ("Мне сейчас трудно дышать.", "urgent_close"),
    ("До свидания.", "goodbye_final"),
])
def test_earlier_optional_completion_does_not_delay_safety_or_stop(text, intent):
    runner = ScenarioRunner(call_id="sufficient-control")
    runner.run([CallStarted(), "Мне хорошо. Сегодня поела, таблетки уже приняла."])
    result = runner.run([text])
    assert result.speak_effects[-1].intent == intent
    assert runner.state.call_closed


def test_short_preset_remains_the_existing_short_path(monkeypatch):
    monkeypatch.setenv("IMVERA_COVERAGE_LADDER", "0")
    runner = ScenarioRunner(call_id="short-unchanged")
    result = runner.run([CallStarted(), "Хорошо."])
    assert result.speak_effects[-1].intent == "important_to_share"
    assert not runner.state.coverage_asked_domains
