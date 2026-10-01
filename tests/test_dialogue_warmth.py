"""Warmth follows accepted meaning; it must not add facts or obligations."""

from __future__ import annotations

import pytest

from packages.dialogue_engine.engine import DialogueEngine
from packages.dialogue_engine.mission import CallMission, GoalDefinition
from packages.dialogue_engine.mission_result import build_mission_result
from packages.dialogue_engine.policy import apply_slot_answer
from packages.dialogue_engine.questions import wellness_ack
from packages.dialogue_engine.response_plan import ResponsePlan, compose_speech
from packages.dialogue_engine.state import EngineState, GoalLifecycle

pytestmark = pytest.mark.dialogue_engine


def deliver(engine: DialogueEngine) -> list:
    effects = []
    while (effect := engine.pop_speak_effect()) is not None:
        effects.append(effect)
        engine.on_playout_completed(effect.generation, effect.question_id)
    return effects


def reply(engine: DialogueEngine, text: str, uid: str) -> list:
    turn = engine.build_rich_turn(text, utterance_id=uid)
    engine.on_user_turn(uid, text, rich_turn=turn)
    return deliver(engine)


@pytest.mark.parametrize("text", ["Не помню.", "Не могу вспомнить."])
def test_unknown_acknowledges_difficulty_without_reassuring_about_health(text: str) -> None:
    engine = DialogueEngine(call_id="warm-unknown")
    engine.start()
    deliver(engine)
    reply(engine, "Голова болит.", "u1")
    spoken = reply(engine, text, "u2")
    assert spoken
    speech = " ".join(effect.text for effect in spoken).lower()
    assert "не будем угадывать" in speech
    assert "ничего страшного" not in speech
    assert "всё хорошо" not in speech
    assert speech.count("?") == 1
    episode = engine.state.issue_episodes[engine.state.active_episode_id]
    assert not episode.known_attributes.get("onset")
    assert not episode.known_attributes.get("duration")
    assert episode.unanswered_attributes
    assert engine.state.pending_episode_attribute == "severity"


def test_unknown_custom_answer_stays_partial_and_gently_moves_on() -> None:
    engine = DialogueEngine(
        call_id="warm-custom-unknown",
        mission=CallMission(
            mission_id="errands",
            goals=(
                GoalDefinition(
                    goal_id="items",
                    prompt_hint="Какие продукты вам купить?",
                    answer_type="free_text",
                    allowed_values=(),
                ),
                GoalDefinition(
                    goal_id="time",
                    prompt_hint="Когда удобно зайти?",
                    answer_type="free_text",
                    allowed_values=(),
                ),
            ),
        ),
    )
    engine.start()
    deliver(engine)
    spoken = reply(engine, "Не помню.", "u1")
    assert "не будем угадывать" in spoken[-1].text.lower()
    assert engine.state.goals["items"].lifecycle == GoalLifecycle.SKIPPED
    assert engine.state.goals["items"].answer is None
    assert engine.state.delivered_question.goal_id == "time"
    assert build_mission_result(engine.state).status != "COMPLETED"


def test_resume_explains_transition_after_health_interrupt_without_claiming_recovery() -> None:
    engine = DialogueEngine(
        call_id="warm-resume",
        mission=CallMission(
            mission_id="shopping",
            goals=(
                GoalDefinition(
                    goal_id="items",
                    prompt_hint="Какие продукты вам купить?",
                    answer_type="free_text",
                    allowed_values=(),
                ),
            ),
        ),
    )
    engine.start()
    deliver(engine)
    reply(engine, "Голова болит.", "u1")
    reply(engine, "Сегодня.", "u2")
    spoken = reply(engine, "Терпимая.", "u3")
    text = spoken[-1].text.lower()
    assert "вернёмся к моему вопросу" in text
    assert "какие продукты" in text
    assert "прошла" not in text and "полегчало" not in text
    assert text.count("?") == 1
    assert engine.state.goals["items"].answer is None
    assert engine.state.delivered_question.goal_id == "items"


@pytest.mark.parametrize(
    "bad_slot,bad_value",
    [
        ("sleep", "Спал плохо."),
        ("mood", "Настроение плохое."),
    ],
)
def test_negative_fact_is_not_overshadowed_by_positive_wellness(
    bad_slot: str,
    bad_value: str,
) -> None:
    state = EngineState(call_id="warm-mixed-fills")
    apply_slot_answer(state, "wellness", "хорошо", polarity="positive", source_text="Хорошо.")
    apply_slot_answer(state, bad_slot, bad_value, polarity="negative", source_text=bad_value)
    before = state.model_dump()
    text = compose_speech(
        ResponsePlan(
            acknowledge_facts=["wellness", bad_slot],
            next_slot="plans",
            marks_question=True,
        ),
        state,
    ).lower()
    assert not any(word in text for word in ("рада", "очень хорошо", "славно"))
    assert "понимаю" in text
    assert text.count("?") == 1
    # Renderer may rotate wording, but cannot mutate clinical facts or goal values.
    after = state.model_dump()
    for key in ("slot_records", "slot_values", "goals", "issue_episodes"):
        assert after[key] == before[key]


@pytest.mark.parametrize("value", ["Нормально.", "Обычно.", "Ничего."])
@pytest.mark.parametrize("seq", [0, 1, 2])
def test_neutral_wellness_does_not_exaggerate_joy(value: str, seq: int) -> None:
    text = wellness_ack(value=value, turn_seq=seq).lower()
    assert not any(word in text for word in ("рада за вас", "очень хорошо", "славно"))
    assert len(text.split()) >= 3


@pytest.mark.parametrize("polarity", ["negative", "uncertain"])
@pytest.mark.parametrize("seq", [0, 1, 2])
def test_ack_does_not_smuggle_a_second_question(polarity: str, seq: int) -> None:
    state = EngineState(call_id="warm-one-question")
    apply_slot_answer(state, "wellness", "плохо", polarity=polarity, source_text="Плохо.")
    state.turn_seq = seq
    text = compose_speech(
        ResponsePlan(
            acknowledge_facts=["wellness"],
            mandatory_question="Как вы спали?",
            marks_question=True,
        ),
        state,
    ).lower()
    assert text.count("?") == 1
    assert "расскажите, что беспокоит" not in text
    assert "уточните чуть подробнее" not in text


def test_belly_and_nausea_ack_does_not_invent_medical_severity() -> None:
    engine = DialogueEngine(call_id="warm-multiple")
    engine.start()
    deliver(engine)
    spoken = reply(engine, "Живот болит и тошнит.", "u1")
    text = " ".join(effect.text for effect in spoken).lower()
    assert "серьёзно" not in text
    assert "живот" in text and "тошнот" in text
    assert engine.state.issue_episodes


def test_warmth_does_not_override_refusal_or_add_questions() -> None:
    engine = DialogueEngine(call_id="warm-refusal")
    engine.start()
    deliver(engine)
    spoken = reply(engine, "Спасибо, не хочу разговаривать.", "u1")
    assert spoken
    assert "?" not in " ".join(effect.text for effect in spoken)
    assert engine.state.elder_asked_to_stop
    assert engine.state.goals["wellness"].lifecycle != GoalLifecycle.SATISFIED


def test_positive_wellness_can_still_be_acknowledged_positively() -> None:
    assert "рада" in wellness_ack(polarity="positive", value="Хорошо.").lower()


def test_positive_sleep_is_not_misread_from_substring() -> None:
    state = EngineState(call_id="warm-good-sleep")
    apply_slot_answer(
        state, "sleep", "Спал неплохо.", polarity="positive", source_text="Спал неплохо."
    )
    text = compose_speech(ResponsePlan(acknowledge_facts=["sleep"], next_slot="plans"), state)
    assert "тяжёлая" not in text and "неважный" not in text


def test_rendering_resume_twice_does_not_duplicate_transition() -> None:
    state = EngineState(call_id="warm-render-repeat")
    plan = ResponsePlan(
        acknowledgement_kind="resume_mission",
        mandatory_question="Какие продукты вам купить?",
        marks_question=True,
    )
    first = compose_speech(plan, state)
    assert compose_speech(plan, state) == first
    assert first.count("Вернёмся") == 1


@pytest.mark.parametrize("text", ["Не хочу разговаривать.", "Спасибо, не хочу разговаривать."])
def test_new_refusal_wording_uses_existing_decline_act(text: str) -> None:
    from packages.dialogue_engine.check_path import is_politeness_refusal
    from packages.dialogue_engine.protocol.acts import normalize_act

    assert is_politeness_refusal(text)
    assert normalize_act(EngineState(call_id="warm-refusal-act"), text) == "DECLINE"


def test_refusal_wording_does_not_suppress_a_complaint() -> None:
    from packages.dialogue_engine.check_path import is_politeness_refusal

    assert not is_politeness_refusal("Не хочу разговаривать, сильно болит голова.")


def test_emergency_in_refusal_still_uses_frozen_urgent_path() -> None:
    engine = DialogueEngine(call_id="warm-refusal-urgent")
    engine.start()
    deliver(engine)
    spoken = reply(engine, "Не хочу разговаривать, не могу дышать.", "u1")
    assert spoken[-1].intent == "urgent_close"
    assert "не будем угадывать" not in spoken[-1].text.lower()
    assert "вернёмся" not in spoken[-1].text.lower()


def test_complaint_survives_call_control_without_changing_consent_decision() -> None:
    engine = DialogueEngine(call_id="warm-refusal-evidence")
    engine.start()
    deliver(engine)
    text = "Не хочу разговаривать, сильно болит голова."
    spoken = reply(engine, text, "u1")
    # Keep the existing deterministic consent decision and stop questioning.
    assert spoken[-1].intent == "revoke_consent_final"
    assert "?" not in spoken[-1].text
    assert engine.state.closing_reason == "revoke_consent"
    episode = next(ep for ep in engine.state.issue_episodes.values() if ep.body_site == "голова")
    assert any(m.evidence.quote in text for m in episode.mentions)
    assert episode.known_attributes.get("severity") == "сильно"
    assert engine.state.goals["wellness"].lifecycle != GoalLifecycle.SATISFIED
