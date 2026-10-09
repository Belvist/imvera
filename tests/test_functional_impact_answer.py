"""Functional questions have one grounded answer owner and meaning."""

import pytest

from packages.dialogue_engine.engine import DialogueEngine

pytestmark = pytest.mark.dialogue_engine


def deliver(engine):
    result = []
    while (speech := engine.pop_speak_effect()) is not None:
        result.append(speech)
        engine.on_playout_completed(speech.generation, speech.question_id)
    return result


@pytest.fixture
def engine(monkeypatch):
    for key, value in {
        "IMVERA_DIALOGUE_ENGINE": "1",
        "IMVERA_COVERAGE_LADDER": "0",
        "IMVERA_ACTION_POLICY_MODE": "policy",
        "IMVERA_ACTION_POLICY_CUTOVER_ENABLED": "1",
        "IMVERA_LLM_INTERPRET": "0",
        "IMVERA_MISSION_LLM_INTERPRET": "0",
    }.items():
        monkeypatch.setenv(key, value)
    engine = DialogueEngine(call_id="functional-answer")
    engine.start()
    deliver(engine)
    text = "Голова болит со вчера, сейчас ещё болит, терпимо."
    engine.on_user_turn("u1", text, rich_turn=engine.build_rich_turn(text, utterance_id="u1"))
    deliver(engine)
    assert len(engine.state.issue_episodes) == 1
    assert engine.state.pending_episode_attribute == "functional_impact"
    return engine


def test_selected_need_is_realized_as_a_functional_question(engine):
    text = engine.state.delivered_question.text
    assert "обычными делами" in text
    assert "про головная боль" not in text


@pytest.mark.parametrize(
    "text", ["Могу делать обычные дела.", "Мне трудно встать.", "Не мешает, справляюсь сама.",
             "Да.", "Нет."]
)
def test_grounded_functional_answer_closes_only_its_need(engine, text):
    engine.on_user_turn("u2", text, rich_turn=engine.build_rich_turn(text, utterance_id="u2"))
    speech = deliver(engine)
    ep = next(iter(engine.state.issue_episodes.values()))
    assert ep.known_attributes.get("functional_impact")
    assert ep.known_attributes["functional_impact"] in text
    assert ep.known_attributes["onset"] == "вчера"
    assert ep.known_attributes["severity"] == "терпимо"
    assert not any("functional_impact" in s.intent for s in speech)


@pytest.mark.parametrize(
    "text",
    [
        "Дочь может делать обычные дела.",
        "Если я могу ходить, то справлюсь.",
        "Вчера могла делать обычные дела.",
        "Смотрела интересный фильм.",
        "Ага.",
        "Угу.",
    ],
)
def test_noncurrent_noncaller_or_unrelated_reply_is_not_functional_answer(engine, text):
    engine.on_user_turn("u2", text, rich_turn=engine.build_rich_turn(text, utterance_id="u2"))
    deliver(engine)
    ep = next(iter(engine.state.issue_episodes.values()))
    assert "functional_impact" not in ep.known_attributes


def test_bare_polarity_cannot_answer_an_unheard_functional_question(engine):
    engine = DialogueEngine(call_id="functional-cancelled")
    engine.start()
    deliver(engine)
    text = "Голова болит со вчера, сейчас ещё болит, терпимо."
    engine.on_user_turn("u1", text, rich_turn=engine.build_rich_turn(text, utterance_id="u1"))
    speech = engine.pop_speak_effect()
    assert speech is not None
    engine.on_playout_started(speech.generation, speech.question_id)
    engine.on_playout_cancelled(speech.generation, speech.question_id)
    assert engine.state.delivered_question.question_id != speech.question_id
    engine.on_user_turn("u2", "Да.", rich_turn=engine.build_rich_turn("Да.", utterance_id="u2"))
    deliver(engine)
    ep = next(iter(engine.state.issue_episodes.values()))
    assert "functional_impact" not in ep.known_attributes
