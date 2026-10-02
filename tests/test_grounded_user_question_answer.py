"""Bounded questions use actual service meaning/evidence, never universal identity."""

from __future__ import annotations

import pytest

from packages.contracts.enums import SlotStatus
from packages.dialogue_engine.conversation_policy import TurnContext, schedule_next_action
from packages.dialogue_engine.engine import DialogueEngine
from packages.dialogue_engine.events import CallStarted
from packages.dialogue_engine.mission import CallMission, GoalDefinition
from packages.dialogue_engine.mission_flow import answer_user_question_text
from packages.dialogue_engine.policy import apply_slot_answer
from packages.dialogue_engine.scenario_runner import ScenarioRunner
from packages.dialogue_engine.semantic_kernel.types import Observation, SubjectKind
from packages.dialogue_engine.turn_understanding import RichUserTurn, build_rich_turn_from_text

pytestmark = pytest.mark.dialogue_engine


@pytest.mark.parametrize("question,topic", [
    ("А ты вообще кто?", "Вера"),
    ("Вы робот или человек?", "голосовой помощник"),
    ("Зачем вы звоните?", "не отвечать"),
    ("Когда вы снова позвоните?", "Точного времени у меня нет"),
    ("Кто увидит мои ответы?", "настроек и согласия"),
    ("Что вы умеете?", "выслушать"),
    ("Вы умеете разговаривать?", "выслушать"),
    ("Вы любите музыку?", "нет личных предпочтений"),
])
def test_supported_question_uses_its_service_meaning(question, topic):
    engine = DialogueEngine(call_id="answer-meaning")
    before = engine.state.model_dump(mode="json")
    answer = answer_user_question_text(question, state=engine.state)
    assert topic in answer
    assert engine.state.model_dump(mode="json") == before


@pytest.mark.parametrize("question", [
    "Когда придёт дочь?",
    "Когда дочь мне позвонит?",
    "Вы знаете, когда дочь мне позвонит?",
    "Почему дочь мне не звонит?",
    "Почему болит голова?",
    "Какую таблетку выпить?",
    "Какая завтра погода?",
    "Вы знаете, кто я?",
])
def test_unsupported_question_abstains_instead_of_identity_or_unrelated_service(question):
    answer = answer_user_question_text(question)
    assert "нет надёжного ответа" in answer
    assert "Вера" not in answer and "Амвера" not in answer
    assert "семья" not in answer


def test_current_call_recall_quotes_evidence_without_inferring_a_new_fact():
    engine = DialogueEngine(call_id="answer-recall")
    apply_slot_answer(engine.state, "sleep", "positive", turn_id="accepted-sleep",
                      source_text="Спала хорошо, только раз проснулась.")
    before = engine.state.model_dump(mode="json")
    answer = answer_user_question_text("Что я говорила про сон?", state=engine.state)
    assert "Спала хорошо, только раз проснулась." in answer
    assert "positive" not in answer
    assert engine.state.model_dump(mode="json") == before


@pytest.mark.parametrize("damage", ["source", "open", "ambiguous", "earlier"])
def test_recall_requires_unambiguous_current_accepted_evidence(damage):
    engine = DialogueEngine(call_id="answer-proof", prior_call_context={"sleep": "плохо"})
    apply_slot_answer(engine.state, "sleep", "positive", turn_id="sleep-now",
                      source_text="Спала спокойно.")
    if damage == "source":
        engine.state.slot_records["sleep"].source_turn_id = ""
    elif damage == "open":
        engine.state.slots["sleep"] = SlotStatus.OPEN
    elif damage == "ambiguous":
        engine.state.observations["different"] = Observation(
            observation_id="different", attribute="answer", value="negative",
            goal_id="sleep", source_turn_id="other-turn", evidence="Спала плохо.",
            status="confirmed",
        )
    question = "Что я вчера говорила про сон?" if damage == "earlier" else "Что я говорила про сон?"
    before = engine.state.model_dump(mode="json")
    answer = answer_user_question_text(question, state=engine.state)
    assert "нет подтверждённого ответа" in answer
    assert "Спала" not in answer and "плохо" not in answer
    assert engine.state.model_dump(mode="json") == before


@pytest.mark.parametrize("status,subject,source,expected", [
    ("confirmed", SubjectKind.SPEAKER, "accepted", True),
    ("candidate", SubjectKind.SPEAKER, "accepted", False),
    ("superseded", SubjectKind.SPEAKER, "accepted", False),
    ("confirmed", SubjectKind.OTHER_PERSON, "accepted", False),
    ("confirmed", SubjectKind.SPEAKER, "", False),
])
def test_custom_goal_recall_uses_confirmed_speaker_evidence_only(status, subject, source, expected):
    mission = CallMission(mission_id="repair", goals=(GoalDefinition(
        goal_id="repair", prompt_hint="Мастер починил кран?", aliases=("ремонт",),
    ),))
    engine = DialogueEngine(call_id="answer-custom-recall", mission=mission)
    engine.state.observations["repair-obs"] = Observation(
        observation_id="repair-obs", attribute="answer", value="yes", goal_id="repair",
        source_turn_id=source, evidence="Мастер починил кран.", status=status, subject=subject,
    )
    before = engine.state.model_dump(mode="json")
    answer = answer_user_question_text("Что я говорила про ремонт?", state=engine.state)
    assert ("Мастер починил кран." in answer) is expected
    assert engine.state.model_dump(mode="json") == before


def test_daily_question_preserves_suspended_clinical_need_without_filling_wellness():
    runner = ScenarioRunner(call_id="answer-suspension")
    runner.run([CallStarted(), "Голова болит."])
    previous = runner.state.delivered_question
    assert previous is not None and previous.episode_id
    old_slots = dict(runner.state.slot_values)
    rich = build_rich_turn_from_text("Вы любите музыку?", utterance_id="question",
                                     engine_state=runner.state)
    assert rich.user_question and not rich.goal_facts
    result = runner.run(["Вы любите музыку?"])
    assert "нет личных предпочтений" in result.speak_effects[-1].text
    suspended = runner.state.suspended_obligation
    assert suspended is not None and suspended.episode_id == previous.episode_id
    assert runner.state.slot_values == old_slots


def test_answer_inside_story_keeps_listening_delivery_semantics():
    runner = ScenarioRunner(call_id="answer-story")
    runner.run([CallStarted(), "Внучка приезжала, хорошо посидели."])
    result = runner.run(["А вы любите музыку?"])
    speak = result.speak_effects[-1]
    assert "нет личных предпочтений" in speak.text
    assert not speak.marks_question
    assert runner.state.thread_last_move == "listen"
    assert runner.state.thread_listening_generation == speak.generation
    assert runner.state.thread_listening_delivered
    assert runner.state.current_thread_label == "рассказ"
    assert runner.state.slots["wellness"] == SlotStatus.OPEN


@pytest.mark.parametrize("question", ["Вы любите музыку?", "Кто вы?"])
def test_answer_without_clinical_pending_yields_the_actual_floor(question):
    runner = ScenarioRunner(call_id="answer-floor")
    runner.run([CallStarted()])
    answered = runner.run([question])
    response = answered.speak_effects[-1]
    assert response.intent == "answer_user_question" and not response.marks_question
    assert runner.state.thread_listening_delivered
    assert runner.state.thread_heard_listening_generation == response.generation
    assert runner.state.answer_context_slot() is None
    assert not runner.state.slot_values and not runner.state.issue_episodes

    continued = runner.run(["Вчера фотографии смотрела."])
    assert continued.speak_effects[-1].intent == "thread_listening_ack"
    assert not continued.speak_effects[-1].marks_question
    assert runner.state.current_thread_label == "рассказ"
    assert runner.state.thread_last_statement == "Вчера фотографии смотрела."
    assert not runner.state.slot_values and not runner.state.issue_episodes


def test_bare_ack_after_answer_is_not_a_stale_wellness_answer():
    runner = ScenarioRunner(call_id="answer-bare")
    runner.run([CallStarted(), "Вы любите музыку?"])
    result = runner.run(["Хорошо."])
    assert not result.speak_effects[-1].marks_question
    assert runner.state.slots["wellness"] == SlotStatus.OPEN
    assert not runner.state.slot_values and not runner.state.issue_episodes


def test_answer_does_not_yield_a_free_floor_over_pending_clinical_need():
    runner = ScenarioRunner(call_id="answer-clinical-floor")
    runner.run([CallStarted(), "Голова болит."])
    pending = runner.state.pending_episode_attribute
    episode = runner.state.active_episode_id
    runner.run(["Вы любите музыку?"])
    assert not runner.state.thread_listening_id
    assert not runner.state.thread_heard_listening_id
    assert runner.state.pending_episode_attribute == pending
    assert runner.state.active_episode_id == episode
    assert runner.state.suspended_obligation.episode_id == episode


def test_answer_cannot_reopen_stale_story_floor_over_reactive_complaint():
    runner = ScenarioRunner(call_id="answer-reactive-clinical")
    runner.run([CallStarted(), "Внучка приезжала, хорошо посидели.", "Да, голова болит."])
    pending = runner.state.pending_episode_attribute
    episode = runner.state.active_episode_id
    assert pending and episode
    runner.run(["Вы любите музыку?"])
    assert not runner.state.thread_listening_id
    assert not runner.state.thread_heard_listening_id
    assert runner.state.pending_episode_attribute == pending
    assert runner.state.active_episode_id == episode
    assert runner.state.suspended_obligation.episode_id == episode


def test_custom_service_answer_does_not_claim_health_mission():
    mission = CallMission(mission_id="visit", goals=(GoalDefinition(
        goal_id="worker_visited", prompt_hint="Мастер сегодня приходил?",
    ),))
    engine = DialogueEngine(call_id="answer-custom-purpose", mission=mission)
    answer = answer_user_question_text("Зачем вы звоните?", state=engine.state)
    assert "по поручению" in answer and "не отвечать" in answer
    assert "самочувствие" not in answer


def test_planned_question_cannot_be_claimed_as_previously_spoken():
    engine = DialogueEngine(call_id="answer-delivery")
    engine.start()
    assert engine.state.planned_question is not None
    assert engine.state.delivered_question is None
    answer = answer_user_question_text("Что вы спрашивали?", state=engine.state)
    assert "Я спрашивала" not in answer


def test_direct_daily_plan_uses_existing_answer_owner():
    engine = DialogueEngine(call_id="answer-plan")
    engine.start()
    speak = engine.pop_speak_effect()
    assert speak is not None
    engine.on_playout_completed(speak.generation, speak.question_id)
    question = "Какая завтра погода?"
    turn = RichUserTurn(utterance_id="question", raw_text=question,
                        dialogue_act="question", user_question=question, control="none",
                        needs_clarification=False,
                        answers_pending_question=False)
    plan = schedule_next_action(engine.state, TurnContext(turn=turn, user_text=question))
    assert plan.answer_user_question == answer_user_question_text(question, state=engine.state)
    assert plan.suspend is not None
    assert not plan.marks_question
