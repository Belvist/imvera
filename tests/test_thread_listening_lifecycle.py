"""Personal listening is a delivered non-question move, never a medical fact."""

from __future__ import annotations

import asyncio
import copy
from types import SimpleNamespace

import pytest

from packages.contracts.enums import FsmState, SlotStatus
from packages.contracts.semantic import Evidence, FactCandidate
from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.session import CallSession
from packages.dialogue_engine.delivery.scope import timer_scope_active, timer_scope_for
from packages.dialogue_engine.effects import SpeakEffect, TimerEffect
from packages.dialogue_engine.events import (
    PlayoutCancelled,
    PlayoutCompleted,
    SpeakEffectStale,
    TimerExpired,
    UserTurnReceived,
)
from packages.dialogue_engine.reducer import _emit_from_plan, reduce
from packages.dialogue_engine.response_plan import ResponsePlan
from packages.dialogue_engine.state import EngineState, Question, QuestionPhase
from packages.dialogue_engine.turn_understanding import RichUserTurn
from packages.voice_runtime.audio import AudioEnvelope
from packages.voice_runtime.call_actor import CallActor, MediaCallbacks
from packages.voice_runtime.playback import PlaybackQueue

pytestmark = pytest.mark.dialogue_engine


def state_for_story():
    return EngineState(call_id="listening-token", fsm_state=FsmState.DAILY_CHECK,
                       current_thread_label="рассказ", open_hook="Внучка вчера приезжала",
                       thread_last_statement="Внучка вчера приезжала",
                       thread_last_utterance_id="story-u1",
                       required_background_goals={"wellness"})


def emit_listening(state, mode="invite"):
    state, effects = _emit_from_plan(state, ResponsePlan(thread_mode=mode))
    assert len(effects) == 1 and isinstance(effects[0], SpeakEffect)
    return effects[0]


def complete(state, effect, **overrides):
    args = dict(generation=effect.generation, question_id=effect.question_id,
                revision=state.revision)
    args.update(overrides)
    return reduce(state, PlayoutCompleted(**args))[1]


def delivered_listening():
    state = state_for_story()
    effect = emit_listening(state)
    timers = complete(state, effect)
    assert len(timers) == 1 and isinstance(timers[0], TimerEffect)
    return state, effect, timers[0]


@pytest.mark.parametrize("mode", ["invite", "listen"])
def test_listening_emit_and_delivery_do_not_reserve_or_fill_a_health_question(mode):
    state = state_for_story()
    state.delivered_question = Question(question_id="health-old", slot="wellness",
                                       text="Как самочувствие?", phase=QuestionPhase.DELIVERED)
    state.waiting_on_slot = "wellness"
    facts, goals = copy.deepcopy(state.slot_values), copy.deepcopy(state.goals)
    effect = emit_listening(state, mode)
    assert not effect.marks_question and effect.question_id == "" and effect.slot is None
    assert state.active_playout.thread_mode == mode
    assert state.thread_listening_id == effect.generation_id
    assert state.thread_listening_generation == effect.generation
    assert not state.thread_listening_delivered
    assert state.delivered_question is state.playing_question is state.planned_question is None
    assert state.waiting_on_slot is None and state.answer_context_slot() is None
    assert state.asked_history == [] and state.slot_values == facts and state.goals == goals
    assert all(status == SlotStatus.OPEN for status in state.slots.values())

    timers = complete(state, effect)
    assert len(timers) == 1
    timer = timers[0]
    assert timer.timer_id == f"listen-{effect.generation_id}"
    assert timer.semantic_scope_id == f"listen:{effect.generation_id}"
    assert timer_scope_active(timer, state)
    assert state.thread_listening_delivered and state.active_playout is None
    assert state.goals == goals and state.slot_values == facts
    assert complete(state, effect) == [], "Duplicate delivery cannot arm another timer"


@pytest.mark.parametrize("bad", ["generation", "identity", "revision"])
def test_bad_playout_callback_cannot_start_listening(bad):
    state = state_for_story()
    effect = emit_listening(state)
    overrides = {"generation": effect.generation + 1} if bad == "generation" else (
        {"question_id": "wrong-token"} if bad == "identity" else {"revision": state.revision + 1}
    )
    before = state.model_dump()
    assert complete(state, effect, **overrides) == []
    assert state.model_dump() == before and not state.thread_listening_delivered


@pytest.mark.parametrize("event_kind", ["cancelled", "stale"])
def test_failed_or_stale_invitation_never_delivers_listening(event_kind):
    state = state_for_story()
    effect = emit_listening(state)
    if event_kind == "cancelled":
        event = PlayoutCancelled(generation=effect.generation, revision=state.revision)
    else:
        event = SpeakEffectStale(effect_id=effect.effect_id, intent=effect.intent,
                                 generation=effect.generation, revision=state.revision)
    assert reduce(state, event)[1] == []
    assert not state.thread_listening_id and not state.thread_listening_delivered
    assert state.thread_listening_generation == 0 and state.active_playout is None
    assert complete(state, effect) == []


def test_superseded_invitation_and_its_timer_cannot_activate_new_listening():
    state, old, timer = delivered_listening()
    replacement = emit_listening(state, "listen")
    assert not timer_scope_active(timer, state)
    assert reduce(state, PlayoutCancelled(generation=old.generation,
                                         revision=state.revision))[1] == []
    assert state.thread_listening_id == replacement.generation_id
    assert not state.thread_listening_delivered
    assert complete(state, old) == []
    before = state.model_dump()
    assert reduce(state, TimerExpired(timer_id=timer.timer_id,
                                     revision=state.revision))[1] == []
    assert state.model_dump() == before


def test_silence_resumes_a_real_open_mission_goal_without_creating_an_answer():
    state, _, timer = delivered_listening()
    facts = copy.deepcopy(state.slot_values)
    state, effects = reduce(state, TimerExpired(timer_id=timer.timer_id,
                                               revision=state.revision, uplink_frames=200))
    assert effects and any(isinstance(effect, SpeakEffect) for effect in effects)
    assert state.thread_reply_finished and not state.thread_listening_id
    assert state.slot_values == facts and state.slots["wellness"] == SlotStatus.OPEN
    assert state.playing_question and state.playing_question.slot == "wellness"
    assert not timer_scope_active(timer, state)


@pytest.mark.parametrize("guard", ["risk_handling", "red_state_pending", "safety_mode",
                                   "pending_episode_attribute", "probe_phase", "call_closed",
                                   "awaiting_goodbye_confirm", "elder_asked_to_stop"])
def test_listening_timeout_never_bypasses_a_clinical_or_control_obligation(guard):
    state, _, timer = delivered_listening()
    setattr(state, guard, "red" if guard == "safety_mode" else (
        "severity" if guard in ("pending_episode_attribute", "probe_phase") else True
    ))
    before = state.model_dump()
    assert reduce(state, TimerExpired(timer_id=timer.timer_id,
                                     revision=state.revision, uplink_frames=100))[1] == []
    assert state.model_dump() == before


def test_no_uplink_is_mic_check_then_listening_after_its_real_delivery():
    state, _, timer = delivered_listening()
    state, effects = reduce(state, TimerExpired(timer_id=timer.timer_id,
                                               revision=state.revision, uplink_frames=0))
    assert len(effects) == 1 and effects[0].intent == "mic_check"
    assert not effects[0].marks_question and not state.thread_listening_delivered
    assert not timer_scope_active(timer, state)
    timers = complete(state, effects[0])
    assert len(timers) == 1 and timer_scope_active(timers[0], state)
    assert state.slot_values == {} and not state.thread_reply_finished


def test_scope_builder_does_not_require_a_question_identity_for_listening():
    assert timer_scope_for(timer_id="listen-g4", question_id="old-health") == "listen:g4"


def test_rejected_noise_does_not_consume_the_listening_token():
    state, _, timer = delivered_listening()
    turn = RichUserTurn(utterance_id="noise", raw_text="шшш", dialogue_act="garbage",
                        control="none", answers_pending_question=False, needs_clarification=False)
    before = state.model_dump()
    assert reduce(state, UserTurnReceived(turn_id="noise", text=turn.raw_text,
                                         rich_turn=turn, revision=state.revision))[1] == []
    assert state.model_dump() == before and timer_scope_active(timer, state)


@pytest.mark.parametrize("mode", ["invite", "listen"])
def test_repair_of_delivered_listening_never_invents_a_health_question(mode):
    state, _, timer = delivered_listening()
    if mode == "listen":
        acknowledgement = emit_listening(state, "listen")
        timer = complete(state, acknowledgement)[0]
    prior_text = state.thread_listening_text
    turn = RichUserTurn(utterance_id="repair", raw_text="Повторите.", dialogue_act="repair",
                        control="none", answers_pending_question=False, needs_clarification=False)
    state, effects = reduce(state, UserTurnReceived(turn_id="repair", text=turn.raw_text,
                                                   rich_turn=turn, revision=state.revision))
    assert len(effects) == 1 and not effects[0].marks_question and effects[0].slot is None
    assert effects[0].text == prior_text and effects[0].intent == "repair_repeat"
    assert state.playing_question is None and not state.thread_listening_delivered
    assert state.slot_values == {} and not timer_scope_active(timer, state)


@pytest.mark.parametrize("delivered", [False, True])
def test_accepted_user_continuation_invalidates_the_previous_timer_and_late_playout(delivered):
    state = state_for_story()
    invitation = emit_listening(state)
    timer = complete(state, invitation)[0] if delivered else TimerEffect(
        timer_id=f"listen-{invitation.generation_id}", wait_ms=7000,
        semantic_scope_id=f"listen:{invitation.generation_id}",
    )
    turn = RichUserTurn(utterance_id="story-u2", raw_text="Вспоминали нашу поездку.",
                        dialogue_act="answer", control="none", answers_pending_question=False,
                        needs_clarification=False)
    state, effects = reduce(state, UserTurnReceived(turn_id=turn.utterance_id,
                                                   text=turn.raw_text, rich_turn=turn,
                                                   revision=state.revision))
    expected_intent = "thread_listening_ack" if delivered else "thread_invite"
    assert len(effects) == 1 and effects[0].intent == expected_intent
    assert not effects[0].marks_question and effects[0].slot is None
    assert state.thread_consumed_reply_id == turn.utterance_id
    assert not state.thread_listening_delivered and not timer_scope_active(timer, state)
    token = state.thread_listening_id
    assert token != invitation.generation_id and not state.slot_values
    assert complete(state, invitation) == [] and state.thread_listening_id == token
    assert len(complete(state, effects[0])) == 1 and state.thread_listening_delivered


@pytest.mark.parametrize("delivered", [False, True])
def test_duplicate_source_turn_is_not_another_listener_reply(delivered):
    state = state_for_story()
    invitation = emit_listening(state)
    if delivered:
        complete(state, invitation)
    before = state.model_dump()
    duplicate = RichUserTurn(utterance_id="story-u1", raw_text="Внучка вчера приезжала",
                             dialogue_act="answer", control="none", answers_pending_question=False,
                             needs_clarification=False)
    assert reduce(state, UserTurnReceived(turn_id=duplicate.utterance_id,
                                         text=duplicate.raw_text, rich_turn=duplicate,
                                         revision=state.revision))[1] == []
    assert state.model_dump() == before


def test_safety_during_a_story_revokes_listening_before_any_late_delivery():
    state, invitation, timer = delivered_listening()
    turn = RichUserTurn(utterance_id="urgent", raw_text="Позовите скорую.",
                        dialogue_act="answer", control="none", answers_pending_question=False,
                        needs_clarification=False)
    state, effects = reduce(state, UserTurnReceived(turn_id=turn.utterance_id, text=turn.raw_text,
                                                   rich_turn=turn, revision=state.revision))
    assert any(isinstance(effect, SpeakEffect) and effect.intent == "urgent_close"
               for effect in effects)
    assert not state.thread_listening_id and not state.thread_listening_delivered
    assert not timer_scope_active(timer, state)
    assert complete(state, invitation) == []


@pytest.mark.parametrize("outcome", ["completed", "cancelled"])
def test_real_sdk_actor_delivery_arms_only_the_completed_nonquestion_listener(outcome):
    async def scenario():
        async def noop(*args, **kwargs):
            return None

        sent = []

        async def send(pcm):
            sent.append(pcm)

        session = CallSession(call_id="sdk-listening", family_id="family",
                              store=InMemoryCallRecordStore())
        initial = session.start()
        session.mark_spoken_action(initial.speak_effect.generation_id)
        opening_followup = session.pop_engine_playout_followup()
        assert opening_followup.timer_effect.timer_id == "wait-wellness"
        engine = session._engine
        engine.outbox.cancel_timer_by_id(opening_followup.timer_effect.timer_id)
        text = "Внучка приезжала, хорошо посидели."
        turn = engine.build_rich_turn(text, utterance_id="story-u1")
        result = session.handle_user_text(text, utterance_id=turn.utterance_id, rich_turn=turn)
        invitation = result.speak_effect
        assert invitation.intent == "thread_invite" and not invitation.marks_question
        actor = CallActor(
            call_id=session.state.call_id, family_id="family", session=session,
            stt=SimpleNamespace(), tts=SimpleNamespace(cancel=noop),
            llm=SimpleNamespace(cancel_request=noop),
            media=MediaCallbacks(send, noop, noop, noop),
        )
        actor._playback = PlaybackQueue(actor.call_id)
        actor.config.post_speech_pause_ms = 0
        runtime_gen = "runtime-listening"
        actor._playback.begin_phrase(runtime_gen, "p", invitation.text)
        actor._active_generation = actor._render_generation = runtime_gen
        actor._pending_mark_render_gen = runtime_gen
        actor._pending_mark_spoken_id = invitation.generation_id
        actor._pending_speak_effect_id = invitation.effect_id
        actor._outbox_action_id = invitation.generation_id
        engine.outbox.mark_started(invitation.effect_id)
        try:
            if outcome == "cancelled":
                await actor._interrupt_playback(flush=True)
                session.mark_spoken_action(invitation.generation_id)  # late notification
                assert not engine.state.thread_listening_delivered
                assert not engine.state.thread_listening_id
                assert actor._engine_timer_id is None
                assert session.pop_engine_playout_followup() is None
                assert engine.pop_timer_effect() is None and not sent
            else:
                frame = b"\x01\x00" * 320
                await actor._playback.enqueue_wait(AudioEnvelope(
                    actor.call_id, runtime_gen, "p", 0, 16000, frame,
                ))
                actor._playback.mark_generation_done("success")
                actor._playback_task = actor._spawn_owned_task(actor._playback_pump())
                deadline = asyncio.get_running_loop().time() + 1
                while actor._engine_timer_id is None:
                    assert asyncio.get_running_loop().time() < deadline
                    await asyncio.sleep(0.005)
                assert sent == [frame]
                assert engine.state.thread_listening_delivered
                assert actor._engine_timer_id == f"listen-{invitation.generation_id}"
                assert engine.state.delivered_question is None
                assert engine.state.goals["wellness"].delivered_attempts == 1
            assert engine.state.slots["wellness"] == SlotStatus.OPEN
            assert not engine.state.slot_values
        finally:
            await actor.stop()

    asyncio.run(scenario())


def sdk_delivered_story():
    session = CallSession(call_id="heard-listening", family_id="family",
                          store=InMemoryCallRecordStore())
    opening = session.start()
    session.mark_spoken_action(opening.speak_effect.generation_id)
    session.pop_engine_playout_followup()
    invitation = sdk_user_turn(session, "Внучка приезжала, хорошо посидели.", "story-u1")
    assert invitation.intent == "thread_invite"
    session.mark_spoken_action(invitation.generation_id)
    followup = session.pop_engine_playout_followup()
    assert followup.timer_effect.timer_id == f"listen-{invitation.generation_id}"
    return session, invitation, followup.timer_effect


def sdk_user_turn(session, text, source):
    turn = session._engine.build_rich_turn(text, utterance_id=source)
    return session.handle_user_text(text, utterance_id=source, rich_turn=turn).speak_effect


@pytest.mark.parametrize("pending_outcome", ["unheard", "cancelled", "stale"])
def test_sdk_unheard_listener_ack_retains_the_actual_heard_origin(pending_outcome):
    session, invitation, old_timer = sdk_delivered_story()
    state = session._engine.state
    ack = sdk_user_turn(session, "Чай пили, разговаривали.", "story-u2")
    assert ack.intent == "thread_listening_ack" and not ack.marks_question
    if pending_outcome == "cancelled":
        session.cancel_playout_action(ack.generation_id)
        session.mark_spoken_action(ack.generation_id)  # late terminal callback
    elif pending_outcome == "stale":
        session._engine.on_speak_effect_stale(ack)
        session.mark_spoken_action(ack.generation_id)
    assert state.thread_heard_listening_id == invitation.generation_id
    assert state.thread_heard_listening_generation == invitation.generation
    assert state.thread_heard_listening_text == invitation.text
    assert state.answer_context_slot() is None
    assert not timer_scope_active(old_timer, state), "Historical context cannot revive a timer"

    response = sdk_user_turn(session, "Хорошо.", "story-u3")
    assert state.slots["wellness"] == SlotStatus.OPEN and "wellness" not in state.slot_values
    assert response.intent == "thread_listening_ack" and not response.marks_question
    assert state.thread_heard_listening_id == invitation.generation_id
    session.mark_spoken_action(response.generation_id)
    assert state.thread_heard_listening_id == response.generation_id
    assert state.thread_heard_listening_text == response.text


@pytest.mark.parametrize("pending_outcome", ["unheard", "cancelled"])
def test_sdk_unheard_return_question_does_not_own_a_story_evaluation(pending_outcome):
    session, invitation, _ = sdk_delivered_story()
    returned = sdk_user_turn(session, "Больше нечего добавить.", "story-finished")
    state = session._engine.state
    assert returned.marks_question and returned.slot == "wellness"
    if pending_outcome == "cancelled":
        session.cancel_playout_action(returned.generation_id)
        session.mark_spoken_action(returned.generation_id)
    assert state.thread_heard_listening_id == invitation.generation_id
    assert state.answer_context_slot() is None
    sdk_user_turn(session, "Хорошо.", "story-early-evaluation")
    assert state.slots["wellness"] == SlotStatus.OPEN and "wellness" not in state.slot_values


def test_sdk_actual_new_question_delivery_releases_the_heard_story_origin():
    session, _, _ = sdk_delivered_story()
    returned = sdk_user_turn(session, "Больше нечего добавить.", "story-finished")
    state = session._engine.state
    assert state.answer_context_slot() is None
    session.mark_spoken_action(returned.generation_id)
    assert not state.thread_heard_listening_id and not state.thread_heard_listening_text
    assert state.thread_heard_listening_generation == 0
    assert state.answer_context_slot() == "wellness"
    sdk_user_turn(session, "Хорошо.", "actual-health-answer")
    assert state.slots["wellness"] == SlotStatus.FILLED


@pytest.mark.parametrize("utterance,expected", [
    ("Голова болит.", "episode_headache_duration"),
    ("Не могу дышать.", "safety_clarify"),
    ("До свидания.", "goodbye_final"),
    ("Не звоните больше.", "goodbye_final"),
])
def test_sdk_explicit_clinical_or_terminal_control_releases_heard_listening(utterance, expected):
    session, invitation, old_timer = sdk_delivered_story()
    response = sdk_user_turn(session, utterance, "clinical-control")
    state = session._engine.state
    assert response.intent == expected
    assert not state.thread_heard_listening_id and not state.thread_heard_listening_text
    assert not timer_scope_active(old_timer, state)
    session.mark_spoken_action(invitation.generation_id)
    assert not state.thread_heard_listening_id
    if utterance == "Голова болит.":
        assert state.pending_episode_attribute == "duration"
        sdk_user_turn(session, "Третий день.", "clinical-early-duration")
        episode = state.issue_episodes[state.active_episode_id]
        assert episode.known_attributes.get("duration") == "Третий день"


def test_sdk_explicit_volunteered_health_fact_survives_heard_story_context():
    session, _, _ = sdk_delivered_story()
    sdk_user_turn(session, "Самочувствие хорошее.", "explicit-health")
    state = session._engine.state
    assert state.slots["wellness"] == SlotStatus.FILLED
    assert state.slot_values["wellness"] == "positive"
    assert not state.thread_heard_listening_id


@pytest.mark.parametrize("cancelled", [False, True])
def test_sdk_repair_with_pending_ack_repeats_the_actual_heard_invitation(cancelled):
    session, invitation, _ = sdk_delivered_story()
    ack = sdk_user_turn(session, "Чай пили, разговаривали.", "story-u2")
    if cancelled:
        session.cancel_playout_action(ack.generation_id)
    repair = sdk_user_turn(session, "Повторите, пожалуйста.", "repair-u3")
    state = session._engine.state
    assert repair.intent == "repair_repeat" and repair.text == invitation.text
    assert not repair.marks_question and repair.slot is None
    assert state.thread_heard_listening_id == invitation.generation_id
    assert state.slots["wellness"] == SlotStatus.OPEN and not state.slot_values
    session.mark_spoken_action(repair.generation_id)
    assert state.thread_heard_listening_id == repair.generation_id


@pytest.mark.parametrize("field,text,value,topic", [
    ("plans", "Сегодня буду гулять.", "Сегодня буду гулять", "планы"),
    ("mood", "Настроение хорошее.", "positive", "настроение"),
])
@pytest.mark.parametrize("cancelled", [False, True])
def test_sdk_typed_topic_fact_and_unheard_question_preserve_heard_answer_ownership(
    field, text, value, topic, cancelled,
):
    session, invitation, old_timer = sdk_delivered_story()
    engine = session._engine
    turn = engine.build_rich_turn(text, utterance_id=f"typed-{field}")
    turn = turn.model_copy(update={"goal_facts": (FactCandidate(
        field=field, value=value, subject="speaker", temporal_scope="today", negated=False,
        evidence=Evidence(start=0, end=len(text), quote=text),
    ),)})
    pending = session.handle_user_text(
        text, utterance_id=turn.utterance_id, rich_turn=turn,
    ).speak_effect
    state = engine.state
    assert state.slots[field] == SlotStatus.FILLED and state.slot_values[field] == value
    assert state.current_thread_label == topic
    assert pending.intent == "important_to_share" and pending.marks_question
    if cancelled:
        session.cancel_playout_action(pending.generation_id)
        session.mark_spoken_action(pending.generation_id)  # cannot replace actual origin
    assert state.thread_heard_listening_id == invitation.generation_id
    assert state.answer_context_slot() is None
    assert not timer_scope_active(old_timer, state)

    sdk_user_turn(session, "Хорошо.", f"early-{field}")
    assert state.slots["wellness"] == SlotStatus.OPEN and "wellness" not in state.slot_values
    assert state.slot_values[field] == value, "The accepted typed fact remains grounded"
    assert state.thread_heard_listening_id == invitation.generation_id


@pytest.mark.parametrize("evaluation", ["Хорошо.", "Плохо.", "Нормально."])
def test_sdk_cached_canonical_answer_cannot_override_current_heard_story_context(evaluation):
    session = CallSession(call_id="cached-meaning", family_id="family",
                          store=InMemoryCallRecordStore())
    opening = session.start()
    session.mark_spoken_action(opening.speak_effect.generation_id)
    session.pop_engine_playout_followup()
    engine = session._engine
    cached = engine.build_rich_turn(evaluation, utterance_id="queued-health-answer")
    assert any(answer.goal_id == "wellness" for answer in cached.goal_answers)
    assert cached.goal_dispositions == ()
    invitation = sdk_user_turn(session, "Внучка приезжала, хорошо посидели.", "story-u1")
    session.mark_spoken_action(invitation.generation_id)
    session.pop_engine_playout_followup()

    response = session.handle_user_text(
        evaluation, utterance_id=cached.utterance_id, rich_turn=cached,
    ).speak_effect
    state = engine.state
    assert state.slots["wellness"] == SlotStatus.OPEN and "wellness" not in state.slot_values
    assert state.slots["mood"] == SlotStatus.OPEN and "mood" not in state.slot_values
    assert state.goals["wellness"].answer is None
    assert response.intent == "thread_listening_ack" and not response.marks_question
    assert state.thread_heard_listening_id == invitation.generation_id
    assert not any(
        getattr(obs, "goal_id", None) == "wellness"
        and getattr(obs, "source_turn_id", "") == cached.utterance_id
        for obs in state.observations.values()
    )


def test_sdk_cached_explicit_health_report_keeps_its_grounded_meaning_during_listening():
    session = CallSession(call_id="cached-explicit-health", family_id="family",
                          store=InMemoryCallRecordStore())
    opening = session.start()
    session.mark_spoken_action(opening.speak_effect.generation_id)
    session.pop_engine_playout_followup()
    engine = session._engine
    cached = engine.build_rich_turn("Самочувствие хорошее.", utterance_id="queued-explicit")
    assert any(answer.goal_id == "wellness" for answer in cached.goal_answers)
    invitation = sdk_user_turn(session, "Внучка приезжала, хорошо посидели.", "story-u1")
    session.mark_spoken_action(invitation.generation_id)
    session.pop_engine_playout_followup()
    session.handle_user_text(cached.raw_text, utterance_id=cached.utterance_id, rich_turn=cached)
    assert engine.state.slots["wellness"] == SlotStatus.FILLED
    assert engine.state.slot_records["wellness"].polarity == "positive"


def test_sdk_cached_canonical_answer_is_valid_after_actual_health_question_delivery():
    session = CallSession(call_id="cached-current-health", family_id="family",
                          store=InMemoryCallRecordStore())
    opening = session.start()
    session.mark_spoken_action(opening.speak_effect.generation_id)
    session.pop_engine_playout_followup()
    engine = session._engine
    cached = engine.build_rich_turn("Хорошо.", utterance_id="queued-health")
    invitation = sdk_user_turn(session, "Внучка приезжала, хорошо посидели.", "story-u1")
    session.mark_spoken_action(invitation.generation_id)
    session.pop_engine_playout_followup()
    health = sdk_user_turn(session, "Больше нечего добавить.", "story-finished")
    assert health.marks_question and health.slot == "wellness"
    session.mark_spoken_action(health.generation_id)
    assert not engine.state.thread_heard_listening_id
    session.handle_user_text(cached.raw_text, utterance_id=cached.utterance_id, rich_turn=cached)
    assert engine.state.slots["wellness"] == SlotStatus.FILLED
    assert engine.state.slot_records["wellness"].polarity == "positive"
