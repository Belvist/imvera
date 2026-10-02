"""Clock answers belong to the pending complaint, not medication or another person."""

from __future__ import annotations

import pytest

from packages.dialogue_engine.engine import DialogueEngine
from packages.dialogue_engine.issue_memory import extract_grounded_onset_value

pytestmark = pytest.mark.dialogue_engine


def _deliver(engine: DialogueEngine) -> None:
    while (effect := engine.pop_speak_effect()) is not None:
        engine.on_playout_completed(effect.generation, effect.question_id)


def _headache_with_pending_time() -> DialogueEngine:
    engine = DialogueEngine(call_id="clock-owner", elder_display_name="Тест")
    engine.start()
    _deliver(engine)
    text = "Голова болит."
    turn = engine.build_rich_turn(text, utterance_id="complaint")
    engine.on_user_turn("complaint", text, rich_turn=turn)
    _deliver(engine)
    assert engine.state.pending_episode_attribute in ("onset", "duration")
    return engine


@pytest.mark.parametrize("answer", [
    "Таблетки принимаю в 12 часов вечера.",
    "Таблетки принимаю вечером.",
    "Я не знаю, где-то в 12 часов вечера принимаю таблетки.",
    "Вечером буду дома.",
    "У мужа вечером началось.",
    "У мужа началось в 12 часов вечера.",
])
def test_another_activity_or_person_does_not_fill_clinical_time(answer: str) -> None:
    assert extract_grounded_onset_value(answer) is None
    engine = _headache_with_pending_time()
    episode = engine.state.issue_episodes[engine.state.active_episode_id]
    pending = engine.state.pending_episode_attribute
    turn = engine.build_rich_turn(answer, utterance_id="off-topic")
    engine.on_user_turn("off-topic", answer, rich_turn=turn)
    assert not episode.known_attributes.get("onset")
    assert not episode.known_attributes.get("duration")
    assert engine.state.pending_episode_attribute == pending
    assert len(engine.state.issue_episodes) == 1
    assert not any(observation.attribute in ("onset", "duration")
                   for observation in turn.observations)


@pytest.mark.parametrize("answer", [
    "Где-то 12 часов вечера.",
    "Я не знаю, где-то 12 часов вечера.",
    "Вечером.",
    "В 12 часов вечера.",
    "Где-то в 12.",
    "Началось вечером.",
    "У меня началось вечером.",
    "Двенадцать часов вечера.",
])
def test_a_real_clock_answer_fills_onset_and_never_a_duration(answer: str) -> None:
    assert extract_grounded_onset_value(answer)
    engine = _headache_with_pending_time()
    episode = engine.state.issue_episodes[engine.state.active_episode_id]
    turn = engine.build_rich_turn(answer, utterance_id="clock-answer")
    engine.on_user_turn("clock-answer", answer, rich_turn=turn)
    assert episode.known_attributes.get("onset")
    assert not episode.known_attributes.get("duration")
    assert engine.state.pending_episode_attribute not in ("onset", "duration")
    assert len(engine.state.issue_episodes) == 1
    assert not any(observation.attribute == "duration" for observation in turn.observations)


@pytest.mark.parametrize("answer,quantity", [
    ("Вечером. Уже два часа.", "два часа"),
    ("С 12 часов вечера уже три часа.", "три часа"),
])
def test_a_true_quantity_remains_duration_next_to_a_clock(
    answer: str, quantity: str,
) -> None:
    engine = _headache_with_pending_time()
    episode = engine.state.issue_episodes[engine.state.active_episode_id]
    turn = engine.build_rich_turn(answer, utterance_id="clock-and-duration")
    engine.on_user_turn("clock-and-duration", answer, rich_turn=turn)
    assert "вечер" in episode.known_attributes["onset"].lower()
    assert quantity in episode.known_attributes["duration"].lower()
    assert len(engine.state.issue_episodes) == 1


def test_bare_elapsed_hours_stay_a_duration() -> None:
    engine = _headache_with_pending_time()
    episode = engine.state.issue_episodes[engine.state.active_episode_id]
    answer = "12 часов."
    turn = engine.build_rich_turn(answer, utterance_id="duration-only")
    engine.on_user_turn("duration-only", answer, rich_turn=turn)
    assert "12 часов" in episode.known_attributes["duration"]
    assert len(engine.state.issue_episodes) == 1


@pytest.mark.parametrize("answer", ["С 10 утра", "С 12 часов вечера", "Со вчерашнего утра"])
def test_a_grounded_since_anchor_remains_a_literal_duration(answer: str) -> None:
    engine = _headache_with_pending_time()
    episode = engine.state.issue_episodes[engine.state.active_episode_id]
    current = episode.known_attributes.get("current")
    turn = engine.build_rich_turn(answer, utterance_id="since-anchor")
    engine.on_user_turn("since-anchor", answer, rich_turn=turn)
    assert episode.known_attributes["duration"] == answer
    assert episode.known_attributes.get("current") == current
    assert engine.state.pending_episode_attribute not in ("onset", "duration")
    assert len(engine.state.issue_episodes) == 1
