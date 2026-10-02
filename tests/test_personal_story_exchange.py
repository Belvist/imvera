"""User-led personal moves share the real non-question delivery lifecycle.

ADR-029 replaces bounded thread questions. Facts/control/delivery assertions
remain strict; the intended delta is ACK → USER rather than another question.
"""

import pytest

from packages.contracts.enums import SlotStatus
from packages.contracts.semantic import Evidence, FactCandidate
from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.session import CallSession
from packages.dialogue_engine.effects import SpeakEffect, TimerEffect
from packages.dialogue_engine.events import (
    CallStarted,
    PlayoutCancelled,
    TimerExpired,
    UserTurnReceived,
)
from packages.dialogue_engine.reducer import reduce
from packages.dialogue_engine.scenario_runner import ScenarioRunner
from packages.dialogue_engine.turn_understanding import build_rich_turn_from_text

pytestmark = pytest.mark.dialogue_engine


def start(story="Внучка приезжала, хорошо посидели."):
    runner = ScenarioRunner(call_id="story-exchange", elder_display_name="Тамара")
    return runner, runner.run([CallStarted(), story])


def listening_timer(result):
    return next(
        e for e in result.effects if isinstance(e, TimerEffect) and e.reason == "thread_wait"
    )


@pytest.mark.parametrize("story,reply", [
    ("Хорошо, сегодня дочь в гости приезжала.", "Чай пили, разговаривали."),
    ("Мне одиноко, скучаю по дочери.", "Она далеко, редко звонит."),
    ("Внучка приезжала, хорошо посидели.", "Да, мы целый день разговаривали."),
])
def test_reply_yields_floor_without_reasking_or_filling_wellness(story, reply):
    runner, first = start(story)
    hook = runner.state.open_hook
    old_attempts = runner.state.goals["wellness"].delivered_attempts
    assert first.speak_effects[-1].intent == "thread_invite"
    assert not first.speak_effects[-1].marks_question
    assert runner.state.delivered_question is None
    result = runner.run([reply])
    response = result.speak_effects[-1]
    assert response.intent == "thread_listening_ack"
    assert not response.marks_question and "?" not in response.text
    assert "вы говорили" not in response.text.lower()
    assert runner.state.open_hook == hook
    assert runner.state.slots["wellness"] == SlotStatus.OPEN
    assert runner.state.goals["wellness"].delivered_attempts == old_attempts
    assert runner.state.thread_listening_delivered
    assert runner.state.answer_context_slot() in (None, "")
    assert runner.state.action_policy_router_stats["conversation_policy_authoritative"] == 2


def test_three_substantive_continuations_do_not_force_mission_return():
    runner, _ = start()
    for reply in ["Чай пили, разговаривали.", "Вспоминали нашу поездку.", "Потом гуляли в саду."]:
        result = runner.run([reply])
        response = result.speak_effects[-1]
        assert response.intent == "thread_listening_ack"
        assert not response.marks_question
        assert runner.state.slots["wellness"] == SlotStatus.OPEN
        assert not runner.state.slot_values
        assert runner.state.thread_last_statement == reply
    result = runner.run(["Больше нечего добавить."])
    response = result.speak_effects[-1]
    assert response.slot == "wellness" and response.marks_question
    runner.run(["Хорошо."])
    assert runner.state.slots["wellness"] == SlotStatus.FILLED


@pytest.mark.parametrize("answer", ["Нет.", "Не помню.", "Не знаю."])
def test_declining_story_does_not_decline_or_discharge_wellness(answer):
    runner, _ = start()
    result = runner.run([answer])
    assert result.speak_effects[-1].slot == "wellness"
    assert result.speak_effects[-1].marks_question
    assert runner.state.slots["wellness"] == SlotStatus.OPEN
    assert "wellness_unknown" not in runner.state.observations
    assert "wellness" not in runner.state.slot_values


def test_listening_timer_is_bound_to_actual_delivered_invitation():
    runner, result = start()
    token = runner.state.thread_listening_id
    timer = listening_timer(result)
    assert timer.timer_id == f"listen-{token}"
    assert timer.semantic_scope_id == f"listen:{token}"
    out = runner.run([TimerExpired(timer_id=timer.timer_id, uplink_frames=20)])
    assert out.speak_effects[-1].slot == "wellness"
    assert runner.state.slots["wellness"] == SlotStatus.OPEN


def test_old_story_timer_cannot_interrupt_new_clinical_question():
    runner, result = start()
    timer = listening_timer(result)
    runner.run(["Голова болит."])
    question = runner.state.delivered_question
    result = runner.run([TimerExpired(timer_id=timer.timer_id, uplink_frames=20)])
    assert not result.effects
    assert runner.state.delivered_question == question
    assert runner.state.pending_episode_attribute == "duration"


@pytest.mark.parametrize("utterance,expected", [
    ("Голова болит.", "episode_headache_duration"),
    ("Не могу дышать.", "urgent_close"),
    ("До свидания.", "goodbye_final"),
])
def test_clinical_safety_and_goodbye_preempt_listening(utterance, expected):
    runner, _ = start()
    result = runner.run([utterance])
    assert result.speak_effects[-1].intent == expected
    assert not runner.state.thread_listening_id


def test_repair_during_nonquestion_listening_does_not_create_health_answer():
    runner, _ = start()
    before = dict(runner.state.slot_values)
    result = runner.run(["Повторите, пожалуйста."])
    assert result.speak_effects[-1].intent == "repair_repeat"
    assert runner.state.slot_values == before
    assert not result.speak_effects[-1].marks_question
    assert result.speak_effects[-1].slot in (None, "")


@pytest.mark.parametrize("reply", ["Хорошо.", "Плохо.", "Нормально."])
def test_bare_story_evaluation_cannot_fill_health_goal(reply):
    runner, _ = start()
    turn = build_rich_turn_from_text(reply, utterance_id="check", engine_state=runner.state)
    assert not any(f.field == "wellness" for f in turn.goal_facts)
    result = runner.run([reply])
    assert result.speak_effects
    assert runner.state.slots["wellness"] == SlotStatus.OPEN
    assert "wellness" not in runner.state.slot_values


def test_explicit_volunteered_health_report_survives_listening_context():
    runner, _ = start()
    result = runner.run(["Чувствую себя плохо."])
    assert runner.state.slots["wellness"] == SlotStatus.FILLED
    assert runner.state.slot_records["wellness"].polarity == "negative"
    assert result.speak_effects[-1].intent == "probe_concern"


def test_backchannel_rearms_listening_without_fact_or_question_attempt():
    runner, _ = start()
    old_attempts = runner.state.goals["wellness"].delivered_attempts
    result = runner.run(["Ага."])
    ack = result.speak_effects[-1]
    assert ack.intent == "thread_listening_ack" and not ack.marks_question
    assert runner.state.slots["wellness"] == SlotStatus.OPEN
    assert runner.state.goals["wellness"].delivered_attempts == old_attempts
    assert runner.state.thread_listening_delivered


def test_cancelled_invitation_never_activates_listening():
    runner = ScenarioRunner(call_id="cancel-story")
    runner.run([CallStarted()])
    text = "Внучка приезжала, хорошо посидели."
    turn = build_rich_turn_from_text(text, utterance_id="story", engine_state=runner.state)
    state, effects = reduce(
        runner.state, UserTurnReceived(turn_id="story", text=text, rich_turn=turn),
    )
    invitation = next(e for e in effects if isinstance(e, SpeakEffect))
    assert not state.thread_listening_delivered
    state, _ = reduce(state, PlayoutCancelled(
        generation=invitation.generation, question_id=invitation.question_id,
    ))
    assert not state.thread_listening_id
    assert not state.thread_listening_delivered
    assert "" not in state.goals


def test_duplicate_reply_id_cannot_spend_next_listening_turn():
    runner, _ = start()
    text = "Чай пили, разговаривали."
    turn = build_rich_turn_from_text(text, utterance_id="duplicate", engine_state=runner.state)
    event = UserTurnReceived(turn_id="duplicate", text=text, rich_turn=turn)
    runner.state, effects = reduce(runner.state, event)
    runner._record(effects)
    token = runner.state.thread_listening_id
    runner.state, effects = reduce(runner.state, event)
    assert not effects
    assert runner.state.thread_listening_id == token


def test_sdk_nonquestion_delivery_keeps_canonical_speech_and_listening_scope():
    session = CallSession(call_id="sdk-story-exchange", family_id="story-family",
                          store=InMemoryCallRecordStore())
    opening = session.start()
    session.mark_spoken_action(opening.proposal.generation_id)
    engine = session._engine
    assert engine is not None
    for number, text in enumerate([
        "Внучка приезжала, хорошо посидели.", "Чай пили, разговаривали.",
        "Вспоминали нашу поездку.", "Да, приятно было.",
    ]):
        turn = engine.build_rich_turn(text, utterance_id=f"sdk-story-{number}")
        result = session.handle_user_text(text, rich_turn=turn)
        assert result.from_engine and result.speak_effect is not None
        assert result.validated.speech == result.speak_effect.text
        assert not result.speak_effect.marks_question
        assert "?" not in result.validated.speech
        assert not engine.state.thread_listening_delivered
        assert session.mark_spoken_action(result.proposal.generation_id)
        assert engine.state.thread_listening_delivered
        followup = session.pop_engine_playout_followup()
        assert followup is not None and followup.timer_effect is not None
        assert followup.timer_effect.semantic_scope_id == (
            f"listen:{engine.state.thread_listening_id}"
        )
        assert engine.state.delivered_question is None
        assert engine.state.slots["wellness"] == SlotStatus.OPEN


def test_zero_capture_is_not_treated_as_answer():
    runner, result = start()
    timer = listening_timer(result)
    out = runner.run([TimerExpired(timer_id=timer.timer_id, uplink_frames=0)])
    effect = out.speak_effects[-1]
    assert effect.intent == "mic_check" and not effect.marks_question
    assert runner.state.slots["wellness"] == SlotStatus.OPEN
    assert not runner.state.slot_values


def test_injected_positive_story_fact_obeys_same_ownership_guard():
    runner = ScenarioRunner(call_id="proposed-story-fact")
    runner.run([CallStarted()])
    text = "Внучка приезжала, хорошо посидели."
    turn = build_rich_turn_from_text(text, utterance_id="proposed", engine_state=runner.state)
    turn = turn.model_copy(update={"goal_facts": (FactCandidate(
        field="wellness", value="positive", subject="speaker", temporal_scope="now", negated=False,
        evidence=Evidence(start=0, end=len(text), quote=text),
    ),)})
    runner.state, _ = reduce(
        runner.state, UserTurnReceived(turn_id="proposed", text=text, rich_turn=turn),
    )
    assert runner.state.slots["wellness"] == SlotStatus.OPEN


def test_side_question_answers_and_returns_the_floor_to_the_same_story():
    runner, _ = start()
    story = runner.state.thread_last_statement
    result = runner.run(["А вы любите музыку?"])
    response = result.speak_effects[-1]
    assert response.intent == "answer_user_question"
    assert "предпочтений" in response.text
    assert not response.marks_question
    assert runner.state.current_thread_label == "рассказ"
    assert runner.state.thread_last_statement == story
    assert runner.state.thread_listening_delivered
    assert not runner.state.slot_values
    response = runner.run(["Вспоминали нашу поездку."]).speak_effects[-1]
    assert response.intent == "thread_listening_ack"


def test_topic_shift_while_listening_retains_new_statement_without_clinical_fact():
    runner, _ = start()
    for statement in ["Люблю слушать старые песни.", "Вчера смотрела интересный фильм.",
                      "Потом вспомнила поездку на море."]:
        response = runner.run([statement]).speak_effects[-1]
        assert not response.marks_question
        assert runner.state.thread_last_statement == statement
        assert not runner.state.slot_values


def test_listening_ack_does_not_repeat_the_previous_delivered_text():
    runner, result = start()
    texts = [result.speak_effects[-1].text]
    for statement in ["Чай пили, разговаривали.", "Вспоминали нашу поездку.",
                      "Да, приятно было."]:
        texts.append(runner.run([statement]).speak_effects[-1].text)
    assert all(a != b for a, b in zip(texts, texts[1:]))


def test_local_question_refusal_with_explicit_wish_to_talk_yields_floor_in_actual_sdk():
    from packages.dialogue_engine.state import GoalLifecycle

    session = CallSession(call_id="local-refusal", family_id="family",
                          store=InMemoryCallRecordStore())
    opening = session.start()
    session.mark_spoken_action(opening.proposal.generation_id)
    engine = session._engine
    text = "Не хочу отвечать на этот вопрос, но поговорить хочу."
    rich = engine.build_rich_turn(text, utterance_id="local")
    result = session.handle_user_text(text, rich_turn=rich)
    assert engine.state.goals["wellness"].lifecycle == GoalLifecycle.DECLINED
    assert not engine.state.elder_asked_to_stop
    assert "consent_declined" not in engine.state.observations
    assert not engine.state.slot_values
    assert result.proposal.intent == "thread_invite"
    assert not result.speak_effect.marks_question
    assert session.mark_spoken_action(result.proposal.generation_id)
    response = session.handle_user_text(
        "Вспоминали нашу поездку.",
        rich_turn=engine.build_rich_turn("Вспоминали нашу поездку.", utterance_id="continue"),
    )
    assert response.proposal.intent == "thread_listening_ack"
    assert engine.state.goals["wellness"].lifecycle == GoalLifecycle.DECLINED


@pytest.mark.parametrize("evaluation", ["Отлично.", "Прекрасно.", "Всё хорошо.",
                                        "Всё нормально.", "Замечательно."])
def test_existing_positive_aliases_evaluate_story_without_health_fill(evaluation):
    runner, _ = start()
    turn = build_rich_turn_from_text(evaluation, utterance_id="eval", engine_state=runner.state)
    assert not turn.goal_facts and not turn.goal_answers
    response = runner.run([evaluation]).speak_effects[-1]
    assert response.intent == "thread_listening_ack" and not response.marks_question
    assert not runner.state.slot_values
    assert runner.state.slots["wellness"] == SlotStatus.OPEN


@pytest.mark.parametrize("report,field", [("Настроение хорошее.", "mood"),
                                          ("Чувствую себя прекрасно.", "wellness")])
def test_positive_domain_predicates_remain_health_evidence_while_listening(report, field):
    runner, _ = start()
    runner.run([report])
    assert runner.state.slots[field] == SlotStatus.FILLED
    assert field in runner.state.slot_values
