"""A delivered listening question owns its reply; a new sentence is not a new story."""

import pytest

from packages.contracts.enums import SlotStatus
from packages.contracts.semantic import Evidence, FactCandidate
from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.session import CallSession
from packages.dialogue_engine.effects import SpeakEffect, TimerEffect
from packages.dialogue_engine.events import (
    CallStarted,
    PlayoutCancelled,
    PlayoutCompleted,
    TimerExpired,
    UserTurnReceived,
)
from packages.dialogue_engine.reducer import reduce
from packages.dialogue_engine.scenario_runner import ScenarioRunner
from packages.dialogue_engine.turn_understanding import build_rich_turn_from_text

pytestmark = pytest.mark.dialogue_engine


def start(story="Внучка приезжала, хорошо посидели."):
    runner = ScenarioRunner(call_id="story-exchange", elder_display_name="Тамара")
    result = runner.run([CallStarted(), story])
    return runner, result


@pytest.mark.parametrize("story,reply", [
    ("Хорошо, сегодня дочь в гости приезжала.", "Чай пили, разговаривали."),
    ("Мне одиноко, скучаю по дочери.", "Она далеко, редко звонит."),
    ("Внучка приезжала, хорошо посидели.", "Да, мы целый день разговаривали."),
])
def test_reply_continues_delivered_story_without_requoting_or_rearming(story, reply):
    runner, first = start(story)
    hook = runner.state.open_hook
    old_attempts = runner.state.goals["wellness"].delivered_attempts
    invitation = first.speak_effects[-1]
    assert invitation.marks_question and invitation.question_id
    assert runner.state.delivered_question.intent == "thread_followup"
    result = runner.run([reply])
    response = result.speak_effects[-1]
    assert response.intent == "thread_continue"
    assert "хотите рассказать" not in response.text.lower()
    assert "вы говорили" not in response.text.lower()
    assert response.text.count("?") == 1
    assert runner.state.open_hook == hook and runner.state.open_hook_used
    assert runner.state.slots["wellness"] == SlotStatus.OPEN
    assert runner.state.goals["wellness"].delivered_attempts == old_attempts
    assert runner.state.delivered_question.question_id == response.question_id
    assert runner.state.answer_context_slot() in (None, "")


def test_listening_is_bounded_and_resumes_unanswered_wellness():
    runner, _ = start()
    runner.run(["Чай пили, разговаривали."])
    result = runner.run(["Да, приятно было."])
    response = result.speak_effects[-1]
    assert response.intent == "resume_after_thread"
    assert response.slot == "wellness" and response.marks_question
    assert "самочувствие" in response.text.lower()
    assert "хотите рассказать" not in response.text.lower()
    assert runner.state.slots["wellness"] == SlotStatus.OPEN
    assert "wellness" not in runner.state.slot_values
    runner.run(["Хорошо."])
    assert runner.state.slots["wellness"] == SlotStatus.FILLED


@pytest.mark.parametrize("answer", ["Нет.", "Не помню.", "Не знаю."])
def test_declining_story_does_not_decline_or_discharge_wellness(answer):
    runner, _ = start()
    result = runner.run([answer])
    assert result.speak_effects[-1].intent == "resume_after_thread"
    assert runner.state.slots["wellness"] == SlotStatus.OPEN
    assert "wellness_unknown" not in runner.state.observations
    assert "wellness" not in runner.state.slot_values


def test_listening_timer_is_bound_to_actual_delivered_invitation():
    runner, result = start()
    question = runner.state.delivered_question
    timers = [e for e in result.effects if isinstance(e, TimerEffect) and e.reason == "thread_wait"]
    assert len(timers) == 1
    assert timers[0].timer_id == f"thread-{question.question_id}"
    out = runner.run([TimerExpired(timer_id=timers[0].timer_id, uplink_frames=20)])
    assert out.speak_effects[-1].intent == "resume_after_thread"
    assert runner.state.slots["wellness"] == SlotStatus.OPEN


def test_old_story_timer_cannot_interrupt_a_new_clinical_question():
    runner, result = start()
    timer = next(
        e for e in result.effects if isinstance(e, TimerEffect) and e.reason == "thread_wait"
    )
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
    assert not any(e.intent == "thread_continue" for e in result.speak_effects)


def test_repeat_names_the_listening_question_and_preserves_health_facts():
    runner, _ = start()
    invitation = runner.state.delivered_question
    before = dict(runner.state.slot_values)
    result = runner.run(["Повторите, пожалуйста."])
    assert invitation.text in result.speak_effects[-1].text
    assert runner.state.slot_values == before
    assert runner.state.delivered_question.question_id == invitation.question_id
    assert result.speak_effects[-1].slot in (None, "")
    runner.state, effects = reduce(runner.state, PlayoutCompleted(
        generation=result.speak_effects[-1].generation,
        question_id=invitation.question_id,
    ))
    assert any(isinstance(e, TimerEffect) and e.reason == "thread_wait" for e in effects)


@pytest.mark.parametrize("reply", ["Хорошо.", "Плохо.", "Нормально."])
def test_bare_story_evaluation_cannot_fill_a_health_goal(reply):
    runner, _ = start()
    turn = build_rich_turn_from_text(reply, utterance_id="check", engine_state=runner.state)
    assert not any(f.field == "wellness" for f in turn.goal_facts)
    result = runner.run([reply])
    assert result.speak_effects
    assert runner.state.slots["wellness"] == SlotStatus.OPEN
    assert "wellness" not in runner.state.slot_values


def test_second_story_is_not_an_infinite_sequence_of_identical_invitations():
    runner, _ = start()
    replies = ["Чай пили, разговаривали.", "Вспоминали нашу поездку.", "Потом гуляли в саду."]
    speaks = []
    for reply in replies:
        speaks.extend(runner.run([reply]).speak_effects)
    assert sum(e.intent.startswith("thread_") for e in speaks) <= 1
    assert all("вы говорили" not in e.text.lower() for e in speaks)
    assert any(e.intent == "resume_after_thread" for e in speaks)
    assert all(isinstance(e, SpeakEffect) for e in speaks)


def test_explicit_volunteered_health_report_survives_listening_context():
    runner, _ = start()
    result = runner.run(["Чувствую себя плохо."])
    assert runner.state.slots["wellness"] == SlotStatus.FILLED
    assert runner.state.slot_records["wellness"].polarity == "negative"
    assert result.speak_effects[-1].intent == "probe_concern"


def test_backchannel_keeps_real_invitation_and_rearms_its_own_timer():
    runner, _ = start()
    question = runner.state.delivered_question
    result = runner.run(["Ага."])
    ack = result.speak_effects[-1]
    assert ack.intent == "thread_listening_ack" and not ack.marks_question
    assert runner.state.delivered_question == question
    runner.state, effects = reduce(runner.state, PlayoutCompleted(
        generation=ack.generation, question_id=ack.question_id,
    ))
    assert any(
        isinstance(e, TimerEffect) and e.timer_id == f"thread-{question.question_id}"
        for e in effects
    )
    assert runner.state.thread_followup_count == 1
    assert runner.state.slots["wellness"] == SlotStatus.OPEN


def test_undelivered_invitation_rolls_back_prompt_budget():
    runner = ScenarioRunner(call_id="cancel-story")
    runner.run([CallStarted()])
    text = "Внучка приезжала, хорошо посидели."
    turn = build_rich_turn_from_text(text, utterance_id="story", engine_state=runner.state)
    state, effects = reduce(runner.state, UserTurnReceived(
        turn_id="story", text=text, rich_turn=turn,
    ))
    invitation = next(e for e in effects if isinstance(e, SpeakEffect))
    old_question = state.delivered_question
    state, _ = reduce(state, PlayoutCancelled(
        generation=invitation.generation, question_id=invitation.question_id,
    ))
    assert state.delivered_question == old_question
    assert state.thread_followup_count == 0 and not state.open_hook_used
    assert "" not in state.goals


def test_duplicate_reply_id_cannot_spend_the_next_listening_turn():
    runner, _ = start()
    text = "Чай пили, разговаривали."
    turn = build_rich_turn_from_text(text, utterance_id="duplicate", engine_state=runner.state)
    event = UserTurnReceived(turn_id="duplicate", text=text, rich_turn=turn)
    runner.state, effects = reduce(runner.state, event)
    runner._record(effects)
    question = runner.state.delivered_question
    count = runner.state.thread_followup_count
    runner.state, effects = reduce(runner.state, event)
    assert not effects
    assert runner.state.delivered_question == question
    assert runner.state.thread_followup_count == count


def test_sdk_delivery_keeps_canonical_story_questions_and_timer_scope():
    session = CallSession(
        call_id="sdk-story-exchange", family_id="story-family",
        store=InMemoryCallRecordStore(),
    )
    opening = session.start()
    session.mark_spoken_action(opening.proposal.generation_id)
    engine = session._engine
    assert engine is not None
    turns = [
        ("Внучка приезжала, хорошо посидели.", "thread_followup"),
        ("Чай пили, разговаривали.", "thread_continue"),
        ("Да, приятно было.", "resume_after_thread"),
    ]
    for number, (text, intent) in enumerate(turns):
        turn = engine.build_rich_turn(text, utterance_id=f"sdk-story-{number}")
        result = session.handle_user_text(text, rich_turn=turn)
        assert result.from_engine and result.speak_effect is not None
        assert result.proposal.intent == intent
        assert result.validated.speech == result.speak_effect.text
        assert result.validated.speech.count("?") == 1
        assert session.mark_spoken_action(result.proposal.generation_id)
        question = engine.state.delivered_question
        assert question.question_id == result.speak_effect.question_id
        if intent.startswith("thread_"):
            followup = session.pop_engine_playout_followup()
            assert followup is not None
            timer = followup.timer_effect
            assert timer is not None
            assert timer.timer_id == f"thread-{question.question_id}"
            assert timer.semantic_scope_id == f"wait:{question.question_id}"
        assert engine.state.slots["wellness"] == SlotStatus.OPEN


def test_zero_capture_during_listening_is_not_treated_as_an_answer():
    runner, result = start()
    question = runner.state.delivered_question
    timer = next(
        e for e in result.effects if isinstance(e, TimerEffect) and e.reason == "thread_wait"
    )
    out = runner.run([TimerExpired(timer_id=timer.timer_id, uplink_frames=0)])
    effect = out.speak_effects[-1]
    assert effect.intent == "mic_check" and not effect.marks_question
    assert runner.state.delivered_question == question
    assert runner.state.slots["wellness"] == SlotStatus.OPEN
    runner.state, effects = reduce(runner.state, PlayoutCompleted(
        generation=effect.generation, question_id=effect.question_id,
    ))
    assert any(
        isinstance(e, TimerEffect) and e.timer_id == timer.timer_id for e in effects
    )


def test_injected_positive_story_fact_obeys_the_same_sdk_ownership_guard():
    runner = ScenarioRunner(call_id="proposed-story-fact")
    runner.run([CallStarted()])
    text = "Внучка приезжала, хорошо посидели."
    turn = build_rich_turn_from_text(text, utterance_id="proposed", engine_state=runner.state)
    turn = turn.model_copy(update={"goal_facts": (FactCandidate(
        field="wellness", value="positive", subject="speaker", temporal_scope="now",
        negated=False,
        evidence=Evidence(start=0, end=len(text), quote=text),
    ),)})
    runner.state, _ = reduce(runner.state, UserTurnReceived(
        turn_id="proposed", text=text, rich_turn=turn,
    ))
    assert runner.state.slots["wellness"] == SlotStatus.OPEN
    assert "wellness" not in runner.state.slot_records
