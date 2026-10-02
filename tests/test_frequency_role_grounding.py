"""Frequency is temporal evidence, never a symptom predicate or body noun."""

from __future__ import annotations

import pytest

from packages.dialogue_engine.engine import DialogueEngine
from packages.dialogue_engine.events import CallStarted
from packages.dialogue_engine.issue_mention_extract import extract_issue_mentions
from packages.dialogue_engine.scenario_runner import ScenarioRunner
from packages.dialogue_engine.semantic_kernel.kernel import interpret
from packages.dialogue_engine.semantic_kernel.types import SpanType

pytestmark = pytest.mark.dialogue_engine


@pytest.mark.parametrize("text", [
    "Я часто слушаю старые песни.",
    "Часто читаю книги.",
    "Мы часто разговаривали с дочерью.",
    "Часто пью чай.",
    "Я часто вспоминаю детство.",
    "Часто играю с внуком.",
    "Часто.",
])
def test_frequency_without_clinical_predicate_never_produces_issue(text):
    result = interpret(text, utterance_id="frequency-story")
    assert any(span.type == SpanType.TIME and span.normalized == "часто" for span in result.spans)
    assert not any(span.type == SpanType.ISSUE for span in result.spans)
    assert not result.observations
    turn = DialogueEngine(call_id="frequency-sdk").build_rich_turn(text, utterance_id="frequency")
    assert not turn.issue_mentions and not turn.observations
    assert not extract_issue_mentions(text)


@pytest.mark.parametrize("text", [
    "Голова часто болит.",
    "Спина часто ноет.",
    "Часто болит.",
    "Меня часто знобит.",
    "Руки часто дрожат.",
    "Пульс частит.",
])
def test_actual_clinical_predicate_survives_frequency_grammar_guard(text):
    result = interpret(text, utterance_id="frequency-symptom")
    issues = [span for span in result.spans if span.type == SpanType.ISSUE]
    assert issues and all(span.normalized != "часто" for span in issues)
    engine = DialogueEngine(call_id="frequency-clinical")
    turn = engine.build_rich_turn(text, utterance_id="clinical")
    assert turn.issue_mentions and turn.observations
    assert all(mention.body_site != "часто" for mention in turn.issue_mentions)
    assert all(mention.label.lower() != "часто" for mention in turn.issue_mentions)
    if "часто" in text.lower():
        assert any(observation.attribute == "onset" and observation.value.lower() == "часто"
                   for observation in turn.observations)


def test_music_story_after_user_question_does_not_invent_episode():
    runner = ScenarioRunner(call_id="frequency-after-question")
    runner.run([CallStarted(), "Внучка приезжала, хорошо посидели.", "Вы любите музыку?"])
    old_facts = dict(runner.state.slot_values)
    result = runner.run(["Я часто слушаю старые песни."])
    assert not runner.state.issue_episodes and runner.state.active_episode_id is None
    assert not runner.state.observations
    assert runner.state.slot_values == old_facts
    assert result.speak_effects


def test_bare_frequency_reply_updates_existing_clinical_context_without_new_symptom():
    runner = ScenarioRunner(call_id="frequency-answer")
    runner.run([CallStarted(), "Голова болит."])
    existing = set(runner.state.issue_episodes)
    pending_attribute = runner.state.pending_episode_attribute
    assert pending_attribute
    turn = DialogueEngine(call_id="frequency-no-new").build_rich_turn("Часто.", utterance_id="bare")
    assert not turn.issue_mentions
    runner.run(["Часто."])
    assert set(runner.state.issue_episodes) == existing
    assert all(episode.body_site != "часто" for episode in runner.state.issue_episodes.values())
    episode = runner.state.issue_episodes[runner.state.active_episode_id]
    assert episode.known_attributes[pending_attribute] == "Часто."


@pytest.mark.parametrize("text,body", [("Зук болит.", "зук"), ("Пах болит.", "пах")])
def test_unknown_and_short_elder_nouns_remain_valid_in_body_role(text, body):
    mentions = extract_issue_mentions(text)
    assert any(mention.body_site == body for mention in mentions)
