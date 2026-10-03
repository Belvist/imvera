"""Routine answers, stories and reflections keep their semantic owners."""

from __future__ import annotations

import pytest

from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.session import CallSession
from packages.dialogue_engine.context import SlotValue
from packages.dialogue_engine.coverage import nutrition_reply_record
from packages.dialogue_engine.realization import heard_topic, reaction_clause
from packages.dialogue_engine.state import EngineState
from packages.dialogue_engine.turn_understanding import RichUserTurn

pytestmark = pytest.mark.dialogue_engine


def turn(text: str) -> RichUserTurn:
    return RichUserTurn(utterance_id="u1", raw_text=text, dialogue_act="answer",
                        control="none", answers_pending_question=True,
                        needs_clarification=False)


@pytest.mark.parametrize("text,polarity", [
    ("Да, поела.", "positive"), ("Поел сегодня.", "positive"),
    ("Не поел.", "negative"), ("Пока не поела.", "negative"),
    ("Нет.", "negative"), ("Да.", "positive"),
    ("Утром не ел, но недавно поел.", "positive"),
])
def test_intake_polarity_has_attributable_current_evidence(text, polarity):
    record = nutrition_reply_record(turn(text), answering=True)
    assert record is not None and record.polarity == polarity
    assert record.confirmed and record.source_turn_id == "u1"
    assert record.source_text in text


@pytest.mark.parametrize("text", [
    "Дочь уже поела.", "Она поела.", "Вчера поела.", "Завтра поем.",
    "Потом поем.", "Кажется, поела.", "Не знаю, ел ли сегодня.",
    "Не хочу отвечать про еду, но хочу поговорить.", "А вы уже поели?",
    "Она сказала: «Я поела».", "Собираюсь поесть.", "Могу поесть позже.",
    "Не забыла поесть.", "Не очень хорошо ел.",
    "Если бы поела.", "Иван поел.", "Я знаю, что дочь поела.",
    "Во сне поела.",
    "Попила.", "Пила воду.",
])
def test_discussion_never_establishes_intake(text):
    assert nutrition_reply_record(turn(text), answering=True) is None


def test_bare_yes_outside_meal_question_does_not_establish_intake():
    assert nutrition_reply_record(turn("Да.")) is None


def test_replay_uses_canonical_question_understanding(monkeypatch):
    from tools.voice_lab.conversation_quality import replay_call

    monkeypatch.setenv("IMVERA_COVERAGE_LADDER", "1")
    pairs, intents = replay_call(["Чувствую себя хорошо.", "А какая погода сегодня?"],
                                 "canonical-replay")
    assert intents[-1] == "answer_user_question"
    assert "нет надёжного ответа" in pairs[-1][1]
    assert "Про погоду" not in pairs[-1][1]


@pytest.mark.parametrize("slot,text", [
    ("nutrition", "Не поел."), ("sleep", "Часа два поспала."),
    ("plans", "Планов никаких."),
])
def test_coverage_topic_without_polarity_has_no_positive_outcome(slot, text):
    state = EngineState(call_id="neutral")
    state.last_user_text = text
    state.last_answered_domain = slot
    reply = reaction_clause(state)
    assert "Хорошо, что поели" not in reply
    assert "выспались" not in reply and "планами непросто" not in reply


def test_old_record_cannot_colour_current_answer_even_when_named_in_plan():
    state = EngineState(call_id="stale")
    state.last_user_text = "Не помню."
    state.last_user_utterance_id = "u2"
    state.slot_records["nutrition"] = SlotValue(value="поел", source_text="Да, поел.",
                                               source_turn_id="u1", polarity="positive")
    assert reaction_clause(state, ("nutrition",)) == ""


@pytest.mark.parametrize("text", ["А какая погода сегодня?", "Когда придёт дочь?",
                                      "Кто готовит суп?"])
def test_question_is_not_a_topic_reflection(text):
    assert heard_topic(text) is None


@pytest.fixture(params=["off", "shadow"])
def session(monkeypatch, request):
    for name, value in {
        "IMVERA_DIALOGUE_ENGINE": "1", "IMVERA_COVERAGE_LADDER": "1",
        "IMVERA_LLM_INTERPRET": "0", "IMVERA_MISSION_LLM_INTERPRET": "0",
        "IMVERA_ACTION_POLICY_MODE": request.param,
    }.items():
        monkeypatch.setenv(name, value)
    s = CallSession(call_id="source-" + request.param, family_id="f",
                    elder_display_name="Тамара Юрьевна", store=InMemoryCallRecordStore())
    s.start()
    s.state.mandatory_checks.update(identity=True, consent=True, can_talk=True)
    s.state.greeted = True
    return s


def say(session, text):
    uid = f"u-{session.turn_id + 1}"
    rich = session._engine.build_rich_turn(text, utterance_id=uid)
    result = session.handle_user_text(text, utterance_id=uid, rich_turn=rich)
    session.mark_spoken_action(result.proposal.generation_id)
    return result.speak_effect


@pytest.mark.parametrize("answer", ["Не поел.", "Нет."])
def test_sdk_negative_meal_answer_is_not_congratulated(session, answer):
    say(session, "Чувствую себя хорошо.")
    assert session._engine.state.pending_coverage_domain == "nutrition"
    speech = say(session, answer)
    state = session._engine.state
    assert state.coverage_records["nutrition"].polarity == "negative"
    assert state.coverage_records["nutrition"].source_text in answer
    assert "Хорошо, что поели" not in speech.text
    assert state.pending_coverage_domain != "nutrition"


def test_sdk_volunteered_negative_intake_is_not_reasked(session):
    speech = say(session, "Чувствую себя хорошо, но сегодня ещё не поел.")
    state = session._engine.state
    assert state.coverage_records["nutrition"].polarity == "negative"
    assert speech.intent != "background_nutrition"
    assert "Хорошо, что поели" not in speech.text


def test_sdk_story_suspends_meal_question_and_returns_to_same_need(session):
    say(session, "Чувствую себя хорошо.")
    for text in ("Вчера дочь приезжала, смотрели старые фотографии.",
                 "Вспоминали, как вместе жили в деревне.",
                 "Потом ещё поговорили про наших старых соседей."):
        speech = say(session, text)
        state = session._engine.state
        assert speech.intent in {"thread_invite", "thread_listening_ack"}
        assert not speech.marks_question and not state.call_closed
        assert "coverage_nutrition" not in state.observations
        assert "nutrition" not in state.coverage_records
        assert state.pending_coverage_domain == "nutrition"
    speech = say(session, "Больше нечего добавить.")
    assert speech.intent == "background_nutrition" and speech.marks_question
    assert session._engine.state.pending_coverage_domain == "nutrition"
    stats = session._engine.state.action_policy_router_stats
    assert stats["conversation_policy_authoritative"] >= 3


def test_sdk_answer_and_story_keep_both_owners(session):
    say(session, "Чувствую себя хорошо.")
    speech = say(session, "Да, поела. А вчера дочь приезжала, мы смотрели старые фотографии.")
    state = session._engine.state
    assert state.coverage_records["nutrition"].polarity == "positive"
    assert state.observations["coverage_nutrition"] in state.last_user_text
    assert "дочь" in state.thread_last_statement
    assert speech.intent == "thread_invite" and not speech.marks_question
    say(session, "Потом вспоминали нашу деревню и соседей.")
    returned = say(session, "Больше нечего добавить.")
    assert returned.intent != "background_nutrition"
    assert not state.call_closed


def test_sdk_local_refusal_does_not_create_meal_fact_or_stop_consent(session):
    say(session, "Чувствую себя хорошо.")
    speech = say(session, "Не хочу отвечать про еду, но хочу поговорить.")
    state = session._engine.state
    assert "coverage_nutrition" not in state.observations
    assert "nutrition" not in state.coverage_records
    assert "coverage_nutrition_declined" in state.observations
    assert speech.intent == "thread_invite" and not state.call_closed
    assert "Хорошо, что поели" not in speech.text


@pytest.mark.parametrize("domain", ["nutrition", "medication"])
def test_sdk_not_recalled_discharges_question_without_an_answer(session, domain):
    say(session, "Чувствую себя хорошо.")
    if domain == "medication":
        say(session, "Да, поела.")
    speech = say(session, "Не помню.")
    state = session._engine.state
    assert f"coverage_{domain}" not in state.observations
    assert f"coverage_{domain}_unknown" in state.observations
    assert domain not in state.coverage_records
    assert state.pending_coverage_domain != domain
    assert speech.intent != f"background_{domain}"


def test_sdk_explicit_stop_still_closes(session):
    say(session, "Чувствую себя хорошо.")
    speech = say(session, "Спасибо, не хочу больше разговаривать.")
    assert session._engine.state.call_closed
    assert not speech.intent.startswith("thread_") and not speech.marks_question


def test_unheard_meal_question_cannot_claim_a_bare_no(monkeypatch):
    from packages.dialogue_engine.engine import DialogueEngine

    monkeypatch.setenv("IMVERA_COVERAGE_LADDER", "1")
    engine = DialogueEngine(call_id="unheard-nutrition")
    engine.start()
    for uid, text in (("u1", "Чувствую себя хорошо."), ("u2", "Нет.")):
        engine.on_user_turn(uid, text, rich_turn=engine.build_rich_turn(text, utterance_id=uid))
        # Deliberately no PlayoutCompleted: the planned meal question is not
        # evidence that the person heard it and answered about eating.
    assert "nutrition" not in engine.state.coverage_records
    assert "coverage_nutrition" not in engine.state.observations
    assert engine.state.pending_coverage_domain == "nutrition"
