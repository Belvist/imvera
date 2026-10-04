"""Ordinary narrative recall is literal scoped evidence, not a clinical fact."""
import pytest

from packages.dialogue_engine.events import CallStarted
from packages.dialogue_engine.mission_flow import answer_user_question_text
from packages.dialogue_engine.scenario_runner import ScenarioRunner

pytestmark = pytest.mark.dialogue_engine
STORY = "Вчера дочь приезжала, мы смотрели старые фотографии."
OTHER = "Потом вспоминали нашу деревню и соседей."


def conversation(monkeypatch):
    monkeypatch.setenv("IMVERA_ACTION_POLICY_MODE", "off")
    monkeypatch.setenv("IMVERA_COVERAGE_LADDER", "1")
    runner = ScenarioRunner(call_id="personal-recall")
    runner.run([CallStarted(), STORY, OTHER])
    return runner


@pytest.mark.parametrize("question,quote", [
    ("А что я рассказывала про дочь?", STORY),
    ("А про деревню что я говорила?", OTHER),
    ("Что я говорила про фотографии?", STORY),
    ("Что я рассказывала о дочери?", STORY),
    ("Что я рассказывала про дочь в этом разговоре?", STORY),
    ("А что я рассказала?", OTHER),
])
def test_return_to_previous_topic_quotes_accepted_statement(monkeypatch, question, quote):
    runner = conversation(monkeypatch)
    before = dict(runner.state.slot_values)
    out = runner.run([question])
    reply = out.speak_effects[-1]
    assert f"«{quote}»" in reply.text
    assert reply.intent == "answer_user_question" and not reply.marks_question
    assert runner.state.slot_values == before == {}
    assert runner.state.thread_last_statement == OTHER
    assert runner.state.delivered_question is None


@pytest.mark.parametrize("question", [
    "Что я рассказывала про сына?", "Что я вчера рассказывала про дочь?",
    "Что я говорила в прошлом разговоре про дочь?", "Что я говорила про сон?",
])
def test_missing_previous_call_and_medical_context_abstain(monkeypatch, question):
    runner = conversation(monkeypatch)
    answer = answer_user_question_text(question, state=runner.state)
    assert "нет подтверждённого ответа" in answer
    assert STORY not in answer and OTHER not in answer


@pytest.mark.parametrize("feedback", ["Да.", "Нормально.", "Я вас слушаю."])
def test_feedback_is_not_recalled_as_personal_content(monkeypatch, feedback):
    runner = conversation(monkeypatch)
    runner.run([feedback])
    out = runner.run(["Что я рассказывала про дочь?"])
    assert STORY in out.speak_effects[-1].text
    assert all(item.text != feedback for item in runner.state.thread_statements)


def test_context_is_bounded_source_scoped_and_survives_state_roundtrip(monkeypatch):
    from packages.dialogue_engine.state import EngineState

    runner = conversation(monkeypatch)
    for i in range(10):
        runner.run([f"Потом рассматривали старые фотографии, снимок номер {i}."])
    entries = runner.state.thread_statements
    assert len(entries) == 6
    assert all(item.call_id == runner.state.call_id and item.utterance_id for item in entries)
    assert len({item.utterance_id for item in entries}) == len(entries)
    assert all(len(item.text) <= 200 for item in entries)
    restored = EngineState.model_validate_json(runner.state.model_dump_json())
    assert restored.thread_statements == entries
    restored.call_id = "foreign-call"
    assert "нет подтверждённого ответа" in answer_user_question_text(
        "Что я рассказывала про фотографии?", state=restored,
    )


def test_recall_is_read_only_and_does_not_export_into_prior_call_memory(monkeypatch):
    runner = conversation(monkeypatch)
    before = runner.state.model_dump(mode="json")
    answer = answer_user_question_text("Что я говорила про дочь?", state=runner.state)
    assert STORY in answer
    assert runner.state.model_dump(mode="json") == before
    assert not runner.state.prior_call_context
    assert all(not getattr(obs, "goal_id", None) for obs in runner.state.observations.values())


def test_unscoped_recall_does_not_replace_recent_clinical_content_with_old_story(monkeypatch):
    runner = conversation(monkeypatch)
    runner.run(["Голова болит со вчера."])
    answer = answer_user_question_text("А что я рассказала?", state=runner.state)
    assert "нет подтверждённого ответа" in answer
    assert STORY not in answer and OTHER not in answer


def test_evicted_topic_is_not_invented_from_newer_context(monkeypatch):
    runner = conversation(monkeypatch)
    for i in range(8):
        runner.run([f"Потом смотрели старые фотографии, снимок номер {i}."])
    answer = answer_user_question_text("Что я говорила про дочь?", state=runner.state)
    assert "нет подтверждённого ответа" in answer
    assert STORY not in answer


def test_explicit_correction_invalidates_narrative_context(monkeypatch):
    from packages.dialogue_engine.events import User
    from packages.dialogue_engine.turn_understanding import RichUserTurn

    runner = conversation(monkeypatch)
    runner.run([User(text="Я ошиблась.", rich_turn=RichUserTurn(
        utterance_id="u-3", raw_text="Я ошиблась.", correction=True,
        dialogue_act="correction", control="none", answers_pending_question=False,
        needs_clarification=False,
    ))])
    assert not runner.state.thread_statements
    assert "нет подтверждённого ответа" in answer_user_question_text(
        "Что я говорила про дочь?", state=runner.state,
    )


def test_unknown_and_protocol_refusal_do_not_become_story_records(monkeypatch):
    runner = conversation(monkeypatch)
    before = tuple(runner.state.thread_statements)
    runner.run(["Не помню."])
    assert tuple(runner.state.thread_statements) == before
    runner.run(["Не хочу отвечать про еду, но хочу поговорить."])
    assert tuple(runner.state.thread_statements) == before


def test_legacy_state_without_narrative_ring_deserializes(monkeypatch):
    from packages.dialogue_engine.state import EngineState

    runner = conversation(monkeypatch)
    payload = runner.state.model_dump(mode="json")
    payload.pop("thread_statements")
    restored = EngineState.model_validate(payload)
    assert restored.thread_statements == []
    assert "нет подтверждённого ответа" in answer_user_question_text(
        "Что я говорила про дочь?", state=restored,
    )


def test_personal_question_suspends_clinical_need_without_satisfying_it(monkeypatch):
    runner = conversation(monkeypatch)
    runner.run(["Голова болит."])
    question = runner.state.delivered_question
    assert question is not None and question.episode_id
    pending = runner.state.pending_episode_attribute
    slots = dict(runner.state.slot_values)
    out = runner.run(["Что я рассказывала про дочь?"])
    assert STORY in out.speak_effects[-1].text
    assert runner.state.slot_values == slots
    suspended = runner.state.suspended_obligation
    assert suspended and suspended.episode_id == question.episode_id
    assert suspended.attribute == pending


def test_excerpt_remains_literal_and_does_not_split_a_word(monkeypatch):
    runner = conversation(monkeypatch)
    text = "Вспоминали деревню и соседей, " + "обсуждали фотографии " * 12
    runner.run([text])
    record = runner.state.thread_statements[-1]
    assert len(record.text) <= 200 and record.text in text
    assert record.text.split()[-1] in text.split()
    assert record.utterance_id == runner.state.thread_last_utterance_id


@pytest.mark.parametrize("damage", ["missing_source", "foreign_call", "empty_quote"])
def test_damaged_context_cannot_ground_an_answer(monkeypatch, damage):
    runner = conversation(monkeypatch)
    first = runner.state.thread_statements[0]
    changes = {"missing_source": {"utterance_id": ""},
               "foreign_call": {"call_id": "different"},
               "empty_quote": {"text": ""}}
    runner.state.thread_statements[0] = first.model_copy(update=changes[damage])
    assert "нет подтверждённого ответа" in answer_user_question_text(
        "Что я рассказывала про дочь?", state=runner.state,
    )
