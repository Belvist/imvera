"""A generic/quoted/conditional medical question is not a speaker report."""

from __future__ import annotations

import pytest

from packages.dialogue_engine.engine import DialogueEngine
from packages.dialogue_engine.events import CallStarted
from packages.dialogue_engine.scenario_runner import ScenarioRunner
from packages.dialogue_engine.state import CheckPath

pytestmark = pytest.mark.dialogue_engine


@pytest.mark.parametrize("text", [
    "Почему болит голова?",
    "А почему болит спина?",
    "Почему плохо?",
    "Почему у дочери болит голова?",
    "Что делать, если болит голова?",
    "Что делать, если у меня болит голова?",
    "Если у меня болит голова, что делать?",
    "Что означает фраза «у меня болит голова»?",
    'Что означает фраза "голова болит"?',
])
def test_nonassertive_question_creates_no_clinical_evidence(text):
    engine = DialogueEngine(call_id="question-no-fact")
    before = engine.state.model_dump(mode="json")
    turn = engine.build_rich_turn(text, utterance_id="generic-question")
    assert turn.user_question and turn.dialogue_act == "question"
    assert not turn.answers_pending_question and not turn.needs_clarification
    assert not turn.goal_facts and not turn.goal_answers
    assert not turn.issue_mentions and not turn.observations
    assert engine.state.model_dump(mode="json") == before


@pytest.mark.parametrize("text", ["Почему болит голова?", "А почему болит спина?", "Почему плохо?"])
def test_generic_causal_question_gets_honest_answer_without_health_state(text):
    runner = ScenarioRunner(call_id="question-no-episode")
    runner.run([CallStarted()])
    question = runner.state.delivered_question
    result = runner.run([text])
    assert "нет надёжного ответа" in result.speak_effects[-1].text
    assert not runner.state.slot_values and not runner.state.slot_records
    assert not runner.state.issue_episodes and not runner.state.observations
    assert question is not None
    assert runner.state.suspended_obligation is not None
    assert not result.speak_effects[-1].marks_question


@pytest.mark.parametrize("text", [
    "Голова болит, почему?",
    "У меня болит голова, почему?",
    "Почему у меня болит голова?",
    "У меня голова болит, что делать?",
    "Голова болит. Что вы умеете?",
    "Ой, поел нормально? Вот у меня что-то голова болит и руки ноют.",
])
def test_actual_report_survives_neighbouring_question(text):
    engine = DialogueEngine(call_id="question-with-report")
    turn = engine.build_rich_turn(text, utterance_id="personal-report")
    assert turn.issue_mentions and turn.observations
    assert any(f.field == "wellness" and f.value == "negative" for f in turn.goal_facts)
    runner = ScenarioRunner(call_id="question-with-episode")
    runner.run([CallStarted()])
    result = runner.run([text])
    assert runner.state.issue_episodes and runner.state.active_episode_id
    assert runner.state.delivered_question is not None
    assert runner.state.delivered_question.episode_id == runner.state.active_episode_id
    assert result.speak_effects[-1].marks_question


def test_generic_and_real_same_predicate_have_distinct_evidence_owners():
    text = "Почему болит голова? А у меня сейчас спина болит."
    engine = DialogueEngine(call_id="question-then-back-report")
    turn = engine.build_rich_turn(text, utterance_id="two-subjects")
    assert {mention.body_site for mention in turn.issue_mentions} == {"спина"}
    assert all(obs.body_site == "спина" for obs in turn.observations)
    mention = turn.issue_mentions[0]
    assert mention.evidence.start == text.rindex("болит")
    assert text[mention.evidence.start:mention.evidence.end] == mention.evidence.quote
    assert all("голова" not in fact.evidence.quote for fact in turn.goal_facts)
    runner = ScenarioRunner(call_id="question-then-back-state")
    runner.run([CallStarted(), text])
    assert {episode.body_site for episode in runner.state.issue_episodes.values()} == {"спина"}


def test_quoted_report_cannot_supply_speaker_or_symptom_evidence():
    text = "Что означает «у меня болит голова»? А у меня сейчас спина болит."
    turn = DialogueEngine(call_id="quoted-self").build_rich_turn(text, utterance_id="quote")
    assert {mention.body_site for mention in turn.issue_mentions} == {"спина"}
    assert all(obs.body_site == "спина" for obs in turn.observations)


def test_explicit_stop_keeps_control_without_accepting_following_generic_symptom():
    text = "Не звоните больше. Почему болит голова?"
    turn = DialogueEngine(call_id="stop-question").build_rich_turn(text, utterance_id="stop")
    assert turn.control == "stop_call"
    assert not turn.goal_facts and not turn.issue_mentions and not turn.observations
    runner = ScenarioRunner(call_id="stop-question-state")
    runner.run([CallStarted()])
    result = runner.run([text])
    assert result.speak_effects[-1].intent == "goodbye_final"
    assert not runner.state.issue_episodes


def test_actual_help_request_keeps_urgent_authority():
    text = "Голова болит, помогите вызвать скорую?"
    turn = DialogueEngine(call_id="urgent-question").build_rich_turn(text, utterance_id="urgent")
    assert turn.issue_mentions and turn.goal_facts
    runner = ScenarioRunner(call_id="urgent-question-state")
    runner.run([CallStarted()])
    result = runner.run([text])
    assert runner.state.check_path == CheckPath.URGENT
    assert result.speak_effects[-1].intent == "urgent_close"
