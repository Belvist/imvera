"""Renderer retries must preserve one answer and the same planned question."""

from __future__ import annotations

import pytest

from packages.dialogue_engine.response_plan import (
    ResponsePlan,
    compose_speech,
    composed_text,
    render_response_plan,
)
from packages.dialogue_engine.state import EngineState


@pytest.mark.parametrize("entrypoints", [
    ("compose", "compose", "render"),
    ("render", "render", "compose"),
    ("render", "compose", "render"),
])
@pytest.mark.parametrize("question", ["Как вы себя чувствуете?", ""])
def test_user_answer_is_rendered_once_without_creating_a_question(
    entrypoints: tuple[str, ...], question: str,
) -> None:
    state = EngineState(call_id="render-retry")
    before = state.model_dump()
    answer = "Я Вера, звоню узнать, как вы."
    acknowledgement = "Я вас слышу."
    plan = ResponsePlan(
        acknowledge=acknowledgement,
        answer_user_question=answer,
        mandatory_question=question,
        intent="answer_user_question",
        slot="wellness" if question else None,
    )
    expected = " ".join(part for part in (acknowledgement, answer, question) if part)
    for entrypoint in entrypoints:
        if entrypoint == "compose":
            text = compose_speech(plan, state)
        else:
            rendered = render_response_plan(plan, state)
            assert rendered is plan
            text = composed_text(rendered)
        assert text == expected
        assert text.count(answer) == 1
        assert text.count("?") == bool(question)
        assert plan.marks_question == bool(question)
        assert plan.intent == ("ask_mission_goal" if question else "answer_user_question")
        assert plan.slot == ("wellness" if question else None)
        assert plan.mandatory_question == " ".join(part for part in (answer, question) if part)
    assert state.model_dump() == before


def test_replacing_an_answer_keeps_the_original_mission_question() -> None:
    state = EngineState(call_id="render-answer-replacement")
    question = "Какие продукты вам купить?"
    plan = ResponsePlan(
        answer_user_question="Я Вера, звоню узнать, как вы.",
        mandatory_question=question,
        intent="ask_mission_goal",
        slot="items",
        marks_question=True,
    )
    compose_speech(plan, state)
    plan.answer_user_question = "Этот вопрос поможет записать ваш список."
    expected = f"{plan.answer_user_question} {question}"
    assert compose_speech(plan, state) == expected
    assert compose_speech(plan, state) == expected
    assert plan.intent == "ask_mission_goal"
    assert plan.slot == "items" and plan.marks_question
    assert plan.mandatory_question == expected


def test_removing_an_answer_keeps_the_original_mission_question() -> None:
    state = EngineState(call_id="render-answer-removal")
    question = "Какие продукты вам купить?"
    plan = ResponsePlan(
        answer_user_question="Я Вера.", mandatory_question=question,
        intent="ask_mission_goal", slot="items", marks_question=True,
    )
    compose_speech(plan, state)
    plan.answer_user_question = None
    assert compose_speech(plan, state) == question
    assert compose_speech(plan, state) == question
    assert plan.mandatory_question == question
    assert plan.intent == "ask_mission_goal" and plan.marks_question


def test_replacing_a_planned_question_does_not_lose_its_first_words() -> None:
    state = EngineState(call_id="render-question-replacement")
    plan = ResponsePlan(
        answer_user_question="Я Вера.", mandatory_question="Какие продукты вам купить?",
        intent="ask_mission_goal", slot="items", marks_question=True,
    )
    compose_speech(plan, state)
    plan.mandatory_question = "Какое молоко вам купить?"
    expected = "Я Вера. Какое молоко вам купить?"
    assert compose_speech(plan, state) == expected
    assert compose_speech(plan, state) == expected
    assert plan.slot == "items" and plan.marks_question
