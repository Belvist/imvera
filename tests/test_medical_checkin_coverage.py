"""Full care check-in retains every domain, without re-asking accepted facts."""
from __future__ import annotations

import pytest

from packages.dialogue_engine.coverage import DOMAINS, coverage_met, covered_domains
from packages.dialogue_engine.events import CallStarted
from packages.dialogue_engine.scenario_runner import ScenarioRunner

pytestmark = pytest.mark.dialogue_engine

FULL_REPORT = ("Мне хорошо. Сегодня поела. Таблетки не принимаю. "
               "Настроение хорошее. Выспалась.")


@pytest.fixture(autouse=True)
def full_mode(monkeypatch):
    for key, value in {"IMVERA_DIALOGUE_ENGINE": "1", "IMVERA_COVERAGE_LADDER": "1",
                       "IMVERA_ACTION_POLICY_MODE": "off", "IMVERA_LLM_INTERPRET": "0",
                       "IMVERA_MISSION_LLM_INTERPRET": "0"}.items():
        monkeypatch.setenv(key, value)


@pytest.mark.parametrize("report", [
    "Мне хорошо. Сегодня поела, таблетки уже приняла.",
    "Мне хорошо. Настроение хорошее. Выспалась.",
])
def test_three_topics_do_not_complete_full_medical_coverage(report):
    runner = ScenarioRunner(call_id="three-is-not-full")
    result = runner.run([CallStarted(), report])
    assert len(covered_domains(runner.state)) == 3
    assert not coverage_met(runner.state)
    assert result.speak_effects[-1].marks_question
    assert result.speak_effects[-1].intent.startswith("background_")
    assert not runner.state.important_to_share_asked
    assert not runner.state.call_closed


def test_full_report_closes_every_domain_without_five_separate_questions():
    runner = ScenarioRunner(call_id="all-in-one")
    result = runner.run([CallStarted(), FULL_REPORT])
    assert covered_domains(runner.state) == set(DOMAINS)
    assert coverage_met(runner.state)
    assert not runner.state.coverage_asked_domains
    assert result.speak_effects[-1].intent == "important_to_share"


def test_separate_answers_cover_every_domain_before_the_invitation():
    runner = ScenarioRunner(call_id="full-separate")
    runner.run([CallStarted()])
    replies = ["Хорошо.", "Поела.", "Нет.", "Нормальное.", "Выспалась."]
    expected = ["background_nutrition", "background_medication", "background_mood",
                "background_sleep", "important_to_share"]
    for reply, intent in zip(replies, expected, strict=True):
        result = runner.run([reply])
        assert result.speak_effects[-1].intent == intent
        assert not runner.state.call_closed
    assert covered_domains(runner.state) == set(DOMAINS)


@pytest.mark.parametrize("disposition", ["Не помню.", "Не хочу отвечать."])
def test_unavailable_answer_is_not_fabricated_or_repeated_and_other_domains_still_checked(
    disposition,
):
    runner = ScenarioRunner(call_id="full-disposition")
    runner.run([CallStarted(), "Хорошо.", disposition])
    assert "nutrition" not in covered_domains(runner.state)
    assert not coverage_met(runner.state)
    result = runner.run(["Нет.", "Нормальное.", "Выспалась."])
    assert result.speak_effects[-1].intent == "important_to_share"
    assert not coverage_met(runner.state)  # unknown/refused != known
    assert not runner.state.call_closed
    intents = [s.intent for s in runner.effects if getattr(s, "marks_question", False)]
    assert intents.count("background_nutrition") == 1
    assert "background_mood" in intents and "background_sleep" in intents


def test_a_personal_story_can_pause_the_check_then_resume_remaining_topics():
    runner = ScenarioRunner(call_id="full-thread-return")
    runner.run([CallStarted(), "Мне хорошо. Сегодня поела, таблетки уже приняла."])
    result = runner.run(["Вчера дочь приехала, мы смотрели фотографии."])
    assert result.speak_effects[-1].intent == "thread_invite"
    assert not runner.state.call_closed
    result = runner.run(["Нет, больше ничего."])
    assert result.speak_effects[-1].intent in {"background_mood", "background_sleep"}
    assert not runner.state.call_closed


@pytest.mark.parametrize("control,intent", [
    ("До свидания.", "goodbye_final"), ("Мне сейчас трудно дышать.", "urgent_close"),
])
def test_medical_topic_completeness_does_not_block_stop_or_emergency(control, intent):
    runner = ScenarioRunner(call_id="full-control")
    runner.run([CallStarted(), "Хорошо."])
    result = runner.run([control])
    assert result.speak_effects[-1].intent == intent
    assert runner.state.call_closed


def test_short_preset_does_not_silently_become_full(monkeypatch):
    monkeypatch.setenv("IMVERA_COVERAGE_LADDER", "0")
    runner = ScenarioRunner(call_id="short-no-cutover")
    result = runner.run([CallStarted(), "Хорошо."])
    assert result.speak_effects[-1].intent == "important_to_share"
