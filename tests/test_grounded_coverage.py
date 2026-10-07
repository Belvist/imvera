"""Routine coverage follows accepted personal evidence, not narrative keywords."""
from __future__ import annotations

import pytest

from packages.dialogue_engine.coverage import content_exchanges, coverage_met, covered_domains
from packages.dialogue_engine.events import CallStarted
from packages.dialogue_engine.scenario_runner import ScenarioRunner

pytestmark = pytest.mark.dialogue_engine


@pytest.fixture(autouse=True)
def live_flags(monkeypatch):
    for name, value in {
        "IMVERA_DIALOGUE_ENGINE": "1", "IMVERA_COVERAGE_LADDER": "1",
        "IMVERA_ACTION_POLICY_MODE": "off", "IMVERA_LLM_INTERPRET": "0",
        "IMVERA_MISSION_LLM_INTERPRET": "0",
    }.items():
        monkeypatch.setenv(name, value)


def exchange(text):
    runner = ScenarioRunner(call_id="grounded-coverage")
    out = runner.run([CallStarted(), text])
    return runner, out


@pytest.mark.parametrize("text, absent", [
    ("Мне хорошо. Сахар сегодня высокий.", {"nutrition"}),
    ("Я чувствую себя хорошо. Дочь приехала. Плохо спала.", {"sleep"}),
    ("Мне хорошо. Дочь приготовила суп, плохо спала.", {"nutrition", "sleep"}),
])
def test_clinical_words_and_family_story_are_not_personal_routine_answers(text, absent):
    runner, _ = exchange(text)
    assert not covered_domains(runner.state).intersection(absent)
    assert runner.state.issue_episodes  # Keep the source reports.


def test_an_asked_medication_question_is_not_an_answer():
    runner, _ = exchange("Мне хорошо.")
    before = covered_domains(runner.state)
    runner.state.medication_asked = True
    runner.state.coverage_asked_domains.add("medication")
    assert covered_domains(runner.state) == before
    assert "medication" not in covered_domains(runner.state)


@pytest.mark.parametrize("text", [
    "Мне хорошо. Сегодня поела, таблетки уже приняла.",
    "Мне хорошо. Сегодня не ела. Таблетки не принимаю.",
])
def test_volunteered_answers_need_no_food_or_medication_rescreen(text):
    runner, out = exchange(text)
    assert {"wellbeing", "nutrition", "medication"} <= covered_domains(runner.state)
    assert runner.state.coverage_records["medication"].source_turn_id == "u-1"
    assert runner.state.coverage_records["medication"].source_text in text
    assert not any(s.intent.startswith("background_medication")
                   or s.intent == "background_nutrition" for s in out.speak_effects)


@pytest.mark.parametrize("meds", [
    "Дочь таблетки уже приняла.",
    "Дочь приехала. Таблетки уже приняла.",
    "Дочь сказала: «Я таблетки уже приняла».",
    "Вчера таблетки приняла.",
    "Если таблетки приняла, то всё хорошо.",
    "Таблетки уже приняла?",
    "Может быть, таблетки уже приняла.",
])
def test_noncurrent_or_unowned_medication_report_does_not_complete_personal_coverage(meds):
    runner, _ = exchange("Мне хорошо. " + meds)
    assert "medication" not in runner.state.coverage_records
    assert "medication" not in covered_domains(runner.state)


def test_owned_medication_return_survives_a_foreign_story():
    runner, _ = exchange("Мне хорошо. Дочь таблетки уже приняла. Я таблетки не принимаю.")
    record = runner.state.coverage_records["medication"]
    assert "Я таблетки не принимаю" in record.source_text
    assert "Дочь" not in record.source_text
    assert "medication" in covered_domains(runner.state)


def test_reported_medication_nonintake_never_becomes_positive_adherence():
    text = "Мне хорошо. Таблетки сегодня не приняла."
    runner, _ = exchange(text)
    record = runner.state.coverage_records["medication"]
    assert record.source_text in text and "не приняла" in record.value
    assert record.polarity is None


def test_other_person_episode_attributes_are_not_content_exchanges():
    runner, _ = exchange("Я чувствую себя хорошо. Дочь приехала. Плохо спала.")
    assert content_exchanges(runner.state) == 1


def test_a_foreign_sleep_story_does_not_promote_the_callers_sleep_question():
    from packages.dialogue_engine.coverage import scored_next_domain

    runner, _ = exchange("Мне хорошо.")
    runner.state.coverage_asked_domains.clear()
    assert scored_next_domain(runner.state, "Дочь приехала. Плохо спала.") == "nutrition"


def test_all_volunteered_check_slots_remain_covered():
    runner, _ = exchange("Мне хорошо. Настроение хорошее. Выспалась.")
    assert {"wellbeing", "mood", "sleep"} <= covered_domains(runner.state)
    assert coverage_met(runner.state)


@pytest.mark.parametrize("food", [
    "Дочь приехала. Поела.",
    "Дочь сказала: «Я сегодня поела».",
    "Вчера поела.",
    "Если поела, то всё хорошо.",
    "Может быть, поела.",
    "Сегодня буду есть.",
])
def test_noncurrent_or_unowned_food_is_not_the_callers_answer(food):
    runner, _ = exchange("Мне хорошо. " + food)
    assert "nutrition" not in runner.state.coverage_records
    assert "nutrition" not in covered_domains(runner.state)


def test_explicit_own_food_return_still_fills_the_record():
    runner, _ = exchange("Мне хорошо. Дочь приехала. Я сегодня поела.")
    assert "nutrition" in covered_domains(runner.state)
    assert "Я сегодня поела" in runner.state.coverage_records["nutrition"].source_text


@pytest.mark.parametrize("reply, value, polarity", [
    ("Да.", "eaten", "positive"), ("Нет.", "not_eaten", "negative"),
])
def test_heard_food_question_preserves_its_typed_answer(reply, value, polarity):
    runner, _ = exchange("Мне хорошо.")
    assert runner.state.delivered_question.slot == "background_nutrition"
    runner.run([reply])
    record = runner.state.coverage_records["nutrition"]
    assert (record.value, record.polarity, record.source_turn_id) == (value, polarity, "u-2")


@pytest.mark.parametrize("status, subject, current, expected", [
    ("confirmed", "speaker", True, True),
    ("confirmed", "speaker", False, False),
    ("candidate", "speaker", True, False),
    ("superseded", "speaker", True, False),
    ("rejected", "speaker", True, False),
    ("confirmed", "other_person", True, False),
    ("confirmed", "unknown", True, False),
])
def test_only_accepted_current_personal_mission_evidence_establishes_coverage(
    status, subject, current, expected,
):
    from packages.dialogue_engine.semantic_kernel.types import Observation, TemporalFrame
    from packages.dialogue_engine.state import EngineState

    state = EngineState(call_id="mission-coverage")
    state.observations["mission"] = Observation(
        observation_id="mission", goal_id="medication", attribute="medication",
        value="не принимаю", evidence="Я таблетки не принимаю", source_turn_id="u-1",
        status=status, subject=subject, temporal=TemporalFrame(current=current),
    )
    assert ("medication" in covered_domains(state)) is expected


@pytest.mark.parametrize("reply, disposition", [
    ("Не помню.", "unknown"), ("Не хочу отвечать.", "declined"),
])
def test_unknown_and_local_refusal_discharge_question_without_creating_a_food_fact(
    reply, disposition,
):
    runner, _ = exchange("Мне хорошо.")
    runner.run([reply])
    assert "nutrition" not in covered_domains(runner.state)
    assert runner.state.observations.get(f"coverage_nutrition_{disposition}")
    assert runner.state.pending_coverage_domain != "nutrition"
