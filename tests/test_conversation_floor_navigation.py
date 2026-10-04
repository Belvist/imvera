"""Whole exchanges: acknowledgments, floor handoff and call navigation are distinct."""
import pytest

from packages.contracts.enums import SlotStatus
from packages.dialogue_engine.events import CallStarted
from packages.dialogue_engine.mission_flow import answer_user_question_text
from packages.dialogue_engine.scenario_runner import ScenarioRunner

pytestmark = pytest.mark.dialogue_engine


def started(monkeypatch, mode="off"):
    monkeypatch.setenv("IMVERA_ACTION_POLICY_MODE", mode)
    monkeypatch.setenv("IMVERA_COVERAGE_LADDER", "1")
    runner = ScenarioRunner(call_id="floor-navigation")
    runner.run([CallStarted()])
    return runner


@pytest.mark.parametrize("answer", [
    "Нормально вроде бы.", "Хорошо вроде бы.", "Ну нормально вроде бы.",
])
def test_hedged_evaluation_answers_heard_wellness_not_a_story(monkeypatch, answer):
    runner = started(monkeypatch)
    out = runner.run([answer])
    assert runner.state.slots["wellness"] == SlotStatus.FILLED
    assert runner.state.slot_records["wellness"].source_text == answer
    assert out.speak_effects[-1].intent != "thread_invite"
    assert runner.state.current_thread_label != "рассказ"


@pytest.mark.parametrize("feedback", [
    "Да.", "Ага.", "Понимаю.", "Нормально.", "Нормально вроде бы.",
    "Нормально говорю.", "Я вас слушаю.", "Правильно.",
])
def test_feedback_does_not_replace_story_anchor(monkeypatch, feedback):
    runner = started(monkeypatch)
    story = "Вчера дочь приезжала, мы смотрели старые фотографии."
    runner.run([story])
    before = dict(runner.state.slot_values)
    out = runner.run([feedback])
    assert runner.state.thread_last_statement == story
    assert runner.state.slot_values == before
    assert not out.speak_effects[-1].marks_question
    out = runner.run(["Потом вспоминали деревню и соседей."])
    assert out.speak_effects[-1].intent == "thread_listening_ack"
    assert runner.state.thread_last_statement == "Потом вспоминали деревню и соседей."


@pytest.mark.parametrize("handoff", ["Вот и всё.", "Я всё сказала.", "Правильно, говорю, всё."])
def test_explicit_floor_handoff_resumes_need_without_inventing_answer(monkeypatch, handoff):
    runner = started(monkeypatch)
    runner.run(["Вчера дочь приезжала, мы смотрели старые фотографии."])
    out = runner.run([handoff])
    assert out.speak_effects[-1].marks_question
    assert out.speak_effects[-1].slot == "wellness"
    assert runner.state.slots["wellness"] == SlotStatus.OPEN
    assert not runner.state.slot_values


@pytest.mark.parametrize("mode", ["off", "shadow", "soft", "policy"])
@pytest.mark.parametrize("question", [
    "И что дальше?", "Что теперь?", "А дальше что будем делать?",
    "и что дальше", "что теперь", "а дальше что будем делать",
])
def test_navigation_answers_then_uses_existing_next_need(monkeypatch, mode, question):
    runner = started(monkeypatch, mode)
    runner.run(["Вчера дочь приезжала, мы смотрели старые фотографии."])
    before = dict(runner.state.slot_values)
    out = runner.run([question])
    reply = out.speak_effects[-1]
    assert "нет надёжного ответа" not in reply.text
    assert reply.marks_question and reply.slot == "wellness"
    assert runner.state.slot_values == before
    assert runner.state.delivered_question.slot == "wellness"
    assert runner.state.thread_reply_finished


@pytest.mark.parametrize("question", [
    "Что будет дальше с моей дочерью?", "Что делать, если болит голова?",
    "А что дальше будет с погодой?", "Когда дальше принимать таблетки?",
])
def test_external_and_medical_questions_are_not_call_navigation(question):
    assert "нет надёжного ответа" in answer_user_question_text(question)


def test_full_live_vague_exchange_does_not_get_stuck_in_listening(monkeypatch):
    runner = started(monkeypatch)
    intents = []
    for text in ["Нормально вроде бы.", "Нормально говорю.", "Да.",
                 "Правильно, говорю, всё.", "И что дальше?"]:
        out = runner.run([text])
        intents.append(out.speak_effects[-1].intent)
    assert runner.state.slots["wellness"] == SlotStatus.FILLED
    assert "thread_invite" not in intents
    assert "thread_listening_ack" not in intents
    assert "нет надёжного ответа" not in out.speak_effects[-1].text


@pytest.mark.parametrize("statement", [
    "Всё нормально, вчера дочь приезжала.",
    "Я всё рассказала дочери, потом мы гуляли.",
    "А дальше мы пошли гулять в саду.",
])
def test_story_content_is_not_floor_handoff(monkeypatch, statement):
    runner = started(monkeypatch)
    runner.run(["Вчера дочь приезжала, мы смотрели старые фотографии."])
    out = runner.run([statement])
    assert out.speak_effects[-1].intent == "thread_listening_ack"
    assert not out.speak_effects[-1].marks_question
    assert not runner.state.thread_reply_finished


@pytest.mark.parametrize("semantic_field", ["slot", "next_slot"])
def test_semantic_question_is_realized_before_answer_composition(semantic_field):
    from packages.dialogue_engine.response_plan import ResponsePlan, compose_speech
    from packages.dialogue_engine.state import EngineState

    state = EngineState(call_id="semantic-composition")
    plan = ResponsePlan(answer_user_question="Можем продолжить.",
                        marks_question=True, **{semantic_field: "wellness"})
    before = state.model_dump()
    text = compose_speech(plan, state)
    assert text.startswith("Можем продолжить.") and text.count("?") == 1
    assert plan.marks_question and plan.slot == "wellness"
    after_first = state.model_dump()
    assert compose_speech(plan, state) == text
    assert state.model_dump() == after_first
    # The existing surface owner advances its phrase rotation once. Nothing
    # else, especially evidence/obligations/facts, may change during rendering.
    assert {k: v for k, v in after_first.items() if k != "pool_counters"} == {
        k: v for k, v in before.items() if k != "pool_counters"
    }
    assert set(after_first["pool_counters"]) == {"slot:wellness"}


def test_answer_only_slot_context_does_not_create_an_unplanned_question():
    from packages.dialogue_engine.response_plan import ResponsePlan, compose_speech
    from packages.dialogue_engine.state import EngineState

    plan = ResponsePlan(answer_user_question="Я Вера.", slot="wellness", marks_question=False)
    assert compose_speech(plan, EngineState(call_id="answer-only")) == "Я Вера."
    assert not plan.marks_question
