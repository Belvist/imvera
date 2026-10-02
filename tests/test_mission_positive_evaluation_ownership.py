"""A positive activity rating is not a speaker-health answer in the SDK."""

import pytest

from packages.contracts.enums import SlotStatus
from packages.dialogue_engine.deterministic_mission import (
    _unowned_positive_wellness_evaluation,
)
from packages.dialogue_engine.engine import DialogueEngine
from packages.dialogue_engine.state import Question, QuestionPhase

pytestmark = pytest.mark.dialogue_engine


def opened_engine():
    engine = DialogueEngine(call_id="positive-evaluation-owner")
    engine.start()
    opening = engine.pop_speak_effect()
    assert opening is not None
    engine.on_playout_completed(opening.generation, opening.question_id)
    return engine


@pytest.mark.parametrize("text", [
    "Внучка приезжала, хорошо посидели.",
    "Отлично погуляли.",
    "Прекрасно фильм снят.",
    "С дочерью нормально поговорили.",
    "Я хорошо погуляла.",
])
def test_sdk_positive_activity_evaluation_does_not_answer_wellness(text):
    engine = opened_engine()
    turn = engine.build_rich_turn(text, utterance_id="activity")
    assert not any(a.goal_id == "wellness" for a in turn.goal_answers)
    engine.on_user_turn("activity", text, rich_turn=turn)
    assert engine.state.slots["wellness"] == SlotStatus.OPEN
    assert "wellness" not in engine.state.slot_values
    assert "wellness" not in engine.state.slot_records


@pytest.mark.parametrize("text", [
    "Хорошо.",
    "Ну хорошо.",
    "Всё хорошо.",
    "Мне хорошо.",
    "Я нормально.",
    "Мне сейчас хорошо.",
    "Здоровье нормально.",
    "По самочувствию нормально.",
    "По состоянию хорошо.",
    "Мне очень хорошо.",
    "Всё сейчас хорошо.",
    "Чувствую себя хорошо.",
    "Чувствую себя хорошо, внучка приезжала.",
    "Хорошо, дочь сегодня приезжала.",
    "Мне плохо.",
    "Так себе.",
])
def test_real_health_assessment_still_binds_delivered_wellness(text):
    engine = opened_engine()
    turn = engine.build_rich_turn(text, utterance_id="assessment")
    assert any(a.goal_id == "wellness" for a in turn.goal_answers)
    engine.on_user_turn("assessment", text, rich_turn=turn)
    assert engine.state.slots["wellness"] == SlotStatus.FILLED
    assert engine.state.slot_records["wellness"].source_text in text


@pytest.mark.parametrize("intent", ["thread_followup", "thread_continue"])
@pytest.mark.parametrize("text", ["Хорошо.", "Плохо.", "Нормально."])
def test_slotless_delivered_story_question_does_not_bind_mission_health(intent, text):
    engine = opened_engine()
    engine.state.delivered_question = Question(
        question_id="story-q", slot="", text="Хотите рассказать?",
        phase=QuestionPhase.DELIVERED, intent=intent,
    )
    turn = engine.build_rich_turn(text, utterance_id="story-evaluation")
    assert not any(a.goal_id == "wellness" for a in turn.goal_answers)
    assert engine.state.slots["wellness"] == SlotStatus.OPEN


def test_full_story_quote_does_not_own_a_proposed_positive_health_fact():
    assert _unowned_positive_wellness_evaluation(
        "Внучка приезжала, хорошо посидели.", positive_proposed=True,
    )
