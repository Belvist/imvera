"""Accepted speech continues through open invitations and previously heard summaries."""
from __future__ import annotations

import asyncio
import copy
from types import SimpleNamespace

import pytest

from packages.contracts.enums import FsmState, SlotStatus
from packages.contracts.semantic import Evidence, FactCandidate
from packages.dialogue_engine.events import CallStarted, PlayoutCompleted, User
from packages.dialogue_engine.scenario_runner import ScenarioRunner

pytestmark = pytest.mark.dialogue_engine

STORY = [
    "Вчера дочь приехала, мы смотрели фотографии.",
    "Долго сидели и вспоминали дачу.",
    "А потом пили чай и смеялись.",
    "Она рассказала про поездку к морю.",
    "Обсуждали фотографии с нашей прошлой поездки.",
    "Вспоминали, как гуляли по набережной вместе.",
]


@pytest.fixture(autouse=True)
def flags(monkeypatch):
    monkeypatch.setenv("IMVERA_COVERAGE_LADDER", "1")
    monkeypatch.setenv("IMVERA_ACTION_POLICY_MODE", "off")
    monkeypatch.setenv("IMVERA_LLM_INTERPRET", "0")
    monkeypatch.setenv("IMVERA_MISSION_LLM_INTERPRET", "0")


def heard_invitation():
    runner = ScenarioRunner(call_id="continuation-ownership")
    result = runner.run([CallStarted(), "Хорошо.", "Поела.", "Нет.",
                         "Нормальное.", "Выспалась."])
    assert result.speak_effects[-1].intent == "important_to_share"
    assert runner.state.delivered_question.intent == "important_to_share"
    return runner


def heard_summary():
    runner = heard_invitation()
    summary = runner.run(["Нет, ничего."]).speak_effects[-1]
    assert summary.intent == "summary" and runner.state.summary_delivered
    return runner, summary


def test_a_heard_open_invitation_accepts_a_story_without_consuming_more_health_questions():
    runner = heard_invitation()
    facts = copy.deepcopy(runner.state.slot_records)
    for i, text in enumerate(STORY):
        result = runner.run([text])
        state = runner.state
        assert not state.call_closed, (i, result.speak_effects)
        assert state.important_to_share_resolved  # invitation answered, no health assertion
        assert state.slot_records == facts and state.slots["plans"] == SlotStatus.OPEN
        assert "important_to_share" not in state.observations
        assert result.speak_effects and all(not s.marks_question for s in result.speak_effects)
        assert state.current_thread_label == "рассказ"
        assert state.thread_statements[-1].text in text
    result = runner.run(["На этом всё."])
    assert result.speak_effects[-1].intent == "summary"
    assert not runner.state.call_closed


@pytest.mark.parametrize("direct_fact", [False, True])
def test_new_accepted_fact_after_summary_requires_a_new_completion_opportunity(direct_fact):
    runner, old_summary = heard_summary()
    text = "Сегодня буду гулять."
    if direct_fact:
        from packages.dialogue_engine.turn_understanding import build_rich_turn_from_text

        turn = build_rich_turn_from_text(text, utterance_id="late-plans",
                                        engine_state=runner.state)
        turn = turn.model_copy(update={
            "goal_answers": (), "goal_dispositions": (), "observations": (),
            "goal_facts": (FactCandidate(
                field="plans", value="Сегодня буду гулять", subject="speaker",
                temporal_scope="today", negated=False,
                evidence=Evidence(start=0, end=len(text), quote=text),
            ),),
        })
        result = runner.run([User(text=text, rich_turn=turn)])
    else:
        result = runner.run([text])
    assert not runner.state.call_closed
    assert runner.state.slots["plans"] == SlotStatus.FILLED
    assert runner.state.slot_records["plans"].source_text in text
    assert result.speak_effects[-1].intent == "summary"
    assert result.speak_effects[-1].generation != old_summary.generation
    result = runner.run([STORY[0]])
    assert not runner.state.call_closed
    assert result.speak_effects[-1].intent == "thread_invite"
    assert runner.state.fsm_state == FsmState.DAILY_CHECK


def test_a_story_after_heard_summary_gets_the_same_existing_thread_selector():
    runner, _ = heard_summary()
    for text in STORY:
        result = runner.run([text])
        assert not runner.state.call_closed
        assert runner.state.fsm_state == FsmState.DAILY_CHECK
        assert all(not s.marks_question for s in result.speak_effects)
    assert runner.state.action_policy_router_stats["conversation_policy_authoritative"] >= 6


def test_question_after_heard_summary_is_answered_without_automatic_goodbye():
    runner, _ = heard_summary()
    result = runner.run(["А ты кто?"])
    assert not runner.state.call_closed
    assert any("Вера" in s.text for s in result.speak_effects)


@pytest.mark.parametrize("listening", [False, True])
def test_polite_floor_completion_is_not_personal_story_content(listening):
    runner, _ = heard_summary()
    if listening:
        runner.run([STORY[0]])
    previous = copy.deepcopy(runner.state.thread_statements)
    result = runner.run(["Ну всё, спасибо."])
    assert runner.state.thread_statements == previous
    assert result.speak_effects[-1].intent == ("summary" if listening else "goodbye_final")


def test_a_story_containing_thanks_is_not_whole_floor_completion():
    runner, _ = heard_summary()
    result = runner.run(["Она сказала спасибо за фотографии нашей поездки."])
    assert not runner.state.call_closed
    assert result.speak_effects[-1].intent == "thread_invite"


@pytest.mark.parametrize("text", ["Нет, ничего.", "Вроде бы нет.", "Больше ничего."])
def test_whole_no_more_after_a_heard_listener_yields_the_floor_without_a_health_fact(text):
    runner = heard_invitation()
    runner.run(STORY[:2])
    records = copy.deepcopy(runner.state.slot_records)
    statements = copy.deepcopy(runner.state.thread_statements)
    result = runner.run([text])
    assert runner.state.thread_reply_finished
    assert runner.state.slot_records == records
    assert runner.state.thread_statements == statements
    assert result.speak_effects[-1].intent == "summary"
    assert not runner.state.call_closed  # topic completion is not a stop-call action


def test_no_more_words_with_new_story_content_do_not_complete_the_floor():
    runner = heard_invitation()
    runner.run(STORY[:2])
    records = copy.deepcopy(runner.state.slot_records)
    text = "Вроде нет, а потом мы вспоминали нашу поездку к морю."
    result = runner.run([text])
    assert not runner.state.thread_reply_finished and not runner.state.call_closed
    assert runner.state.thread_statements[-1].text in text
    assert runner.state.slot_records == records
    assert result.speak_effects[-1].intent == "thread_listening_ack"


@pytest.mark.parametrize("outcome", ["unheard", "cancelled"])
def test_unheard_open_invitation_is_not_completed_by_a_story(outcome):
    from packages.dialogue_engine.engine import DialogueEngine

    engine = DialogueEngine(call_id="unheard-invitation")
    engine.start()
    def deliver():
        while (s := engine.pop_speak_effect()) is not None:
            engine.on_playout_completed(s.generation, s.question_id)
    deliver()
    for i, text in enumerate(["Хорошо.", "Поела.", "Нет.", "Нормальное."]):
        turn = engine.build_rich_turn(text, utterance_id=f"routine-{i}")
        engine.on_user_turn(turn.utterance_id, text, rich_turn=turn)
        deliver()
    text = "Выспалась."
    turn = engine.build_rich_turn(text, utterance_id="sleep")
    engine.on_user_turn(turn.utterance_id, text, rich_turn=turn)
    invitation = engine.pop_speak_effect()
    assert invitation.intent == "important_to_share"
    if outcome == "cancelled":
        engine.on_playout_cancelled(invitation.generation, invitation.question_id)
    turn = engine.build_rich_turn(STORY[0], utterance_id="early-story")
    engine.on_user_turn(turn.utterance_id, turn.raw_text, rich_turn=turn)
    assert not engine.state.important_to_share_resolved
    assert "important_to_share" not in engine.state.observations


@pytest.mark.parametrize("stage", ["invitation", "summary", "listening"])
@pytest.mark.parametrize("text", ["Не могу дышать.", "До свидания."])
def test_safety_and_explicit_end_keep_their_owners(stage, text):
    runner = heard_invitation() if stage != "summary" else heard_summary()[0]
    if stage == "listening":
        runner.run([STORY[0]])
    result = runner.run([text])
    if text == "До свидания.":
        assert runner.state.call_closed and result.speak_effects[-1].intent == "goodbye_final"
    else:
        assert result.speak_effects[-1].intent not in {
            "thread_invite", "thread_listening_ack", "goodbye_final", "summary",
        }
        assert result.speak_effects[-1].intent == "urgent_close"
        assert runner.state.call_closed and runner.state.closing_reason == "urgent"


def test_noise_does_not_answer_an_open_invitation():
    runner = heard_invitation()
    from packages.dialogue_engine.turn_understanding import RichUserTurn

    runner.run([User(text="шшш", rich_turn=RichUserTurn(
        utterance_id="noise", raw_text="шшш", dialogue_act="garbage", control="none",
        answers_pending_question=False, needs_clarification=False,
    ))])
    assert not runner.state.important_to_share_resolved
    assert not runner.state.thread_statements


@pytest.mark.parametrize("text,domain", [("Сегодня поела.", "nutrition"),
                                        ("Сегодня таблетки приняла.", "medication")])
def test_late_routine_evidence_in_short_preset_does_not_reuse_the_old_summary(text, domain,
                                                                                  monkeypatch):
    monkeypatch.setenv("IMVERA_COVERAGE_LADDER", "0")
    runner = ScenarioRunner(call_id="short-summary")
    runner.run([CallStarted(), "Хорошо.", "Нет, ничего."])
    assert runner.state.summary_delivered
    result = runner.run([text])
    assert not runner.state.call_closed
    assert result.speak_effects[-1].intent != "goodbye_final"
    assert (domain in runner.state.coverage_records
            or any(ep.kind == "medication_issue" for ep in runner.state.issue_episodes.values()))


def test_rejected_goal_proposal_does_not_invalidate_a_summary():
    from packages.dialogue_engine.mission import GoalAnswerCandidate
    from packages.dialogue_engine.turn_understanding import RichUserTurn

    runner, _ = heard_summary()
    turn = RichUserTurn(utterance_id="rejected", raw_text="Шшш.", dialogue_act="garbage",
        control="none", answers_pending_question=False, needs_clarification=False,
        goal_answers=(GoalAnswerCandidate(goal_id="plans", value="Поеду к дочке",
                                         evidence="Шшш.", confidence=1),))
    records = copy.deepcopy(runner.state.slot_records)
    result = runner.run([User(text=turn.raw_text, rich_turn=turn)])
    assert runner.state.slots["plans"] == SlotStatus.OPEN
    assert runner.state.slot_records == records
    assert runner.state.summary_delivered
    assert all(s.intent != "summary" for s in result.speak_effects)


def test_clinical_need_in_a_story_keeps_priority_over_listening():
    runner = heard_invitation()
    runner.run([STORY[0]])
    result = runner.run(["А потом у меня голова заболела."])
    assert not runner.state.call_closed
    assert result.speak_effects[-1].marks_question
    assert result.speak_effects[-1].intent.startswith("episode_")
    assert runner.state.pending_episode_attribute
    assert any(ep.body_site == "голова" and ep.subject == "speaker"
               for ep in runner.state.issue_episodes.values())


def test_old_summary_completion_cannot_commit_a_new_summary():
    # ScenarioRunner delivers synchronously; use the genuine engine's outbox
    # to leave the new summary pending and submit the old generation instead.
    from packages.dialogue_engine.engine import DialogueEngine

    runner, old_summary = heard_summary()
    engine = DialogueEngine(call_id=runner.state.call_id)
    engine.state = runner.state
    text = "Сегодня буду гулять."
    turn = engine.build_rich_turn(text, utterance_id="late-plans")
    engine.on_user_turn(turn.utterance_id, text, rich_turn=turn)
    current = engine.pop_speak_effect()
    assert current.intent == "summary" and not engine.state.call_closed
    assert not engine.state.summary_delivered
    from packages.dialogue_engine.reducer import reduce

    reduce(engine.state, PlayoutCompleted(generation=old_summary.generation,
        question_id=old_summary.question_id, revision=engine.state.revision))
    assert not engine.state.summary_delivered
    engine.on_playout_completed(current.generation, current.question_id)
    assert engine.state.summary_delivered


@pytest.mark.parametrize("phase", ["invitation", "summary"])
@pytest.mark.parametrize("cancelled", [False, True])
def test_sdk_actor_actual_pcm_completion_and_cancel_keep_continuation_ownership(phase, cancelled):
    """Real SDK/CallActor playback; controlled PCM, no audio model or FreeSWITCH."""
    from packages.core.memory_store import InMemoryCallRecordStore
    from packages.dialogue.session import CallSession
    from packages.voice_runtime.audio import AudioEnvelope
    from packages.voice_runtime.call_actor import CallActor, MediaCallbacks
    from packages.voice_runtime.playback import PlaybackQueue

    async def scenario():
        async def noop(*args, **kwargs):
            return None

        sent = []
        async def send(pcm):
            sent.append(pcm)

        session = CallSession(call_id=f"actor-{phase}-{cancelled}", family_id="family",
                              store=InMemoryCallRecordStore())
        engine = session._engine
        def finish(effect):
            session.mark_spoken_action(effect.generation_id)
            follow = session.pop_engine_playout_followup()
            if follow and follow.timer_effect:
                engine.outbox.cancel_timer_by_id(follow.timer_effect.timer_id)

        def reply(text, uid):
            turn = engine.build_rich_turn(text, utterance_id=uid)
            return session.handle_user_text(text, utterance_id=uid, rich_turn=turn).speak_effect

        finish(session.start().speak_effect)
        for i, text in enumerate(["Хорошо.", "Поела.", "Нет.", "Нормальное."]):
            finish(reply(text, f"routine-{i}"))
        previous_heard = engine.state.delivered_question.question_id
        effect = reply("Выспалась.", "sleep")
        assert effect.intent == "important_to_share"
        if phase == "summary":
            finish(effect)
            effect = reply("Нет, ничего.", "decline")
            assert effect.intent == "summary" and not engine.state.summary_delivered
        actor = CallActor(call_id=session.state.call_id, family_id="family", session=session,
            stt=SimpleNamespace(), tts=SimpleNamespace(cancel=noop),
            llm=SimpleNamespace(cancel_request=noop), media=MediaCallbacks(send, noop, noop, noop))
        actor._playback = PlaybackQueue(actor.call_id)
        actor.config.post_speech_pause_ms = 0
        runtime_gen = "actual-playback"
        actor._playback.begin_phrase(runtime_gen, "p", effect.text)
        actor._active_generation = actor._render_generation = runtime_gen
        actor._pending_mark_render_gen = runtime_gen
        actor._pending_mark_spoken_id = effect.generation_id
        actor._pending_speak_effect_id = effect.effect_id
        actor._outbox_action_id = effect.generation_id
        engine.outbox.mark_started(effect.effect_id)
        try:
            if cancelled:
                await actor._interrupt_playback(flush=True)
                session.mark_spoken_action(effect.generation_id)
                assert not sent and not engine.state.summary_delivered
                if phase == "invitation":
                    assert engine.state.delivered_question.question_id == previous_heard
            else:
                frame = b"\x01\x00" * 320
                await actor._playback.enqueue_wait(AudioEnvelope(
                    actor.call_id, runtime_gen, "p", 0, 16000, frame))
                actor._playback.mark_generation_done("success")
                actor._playback_task = actor._spawn_owned_task(actor._playback_pump())
                deadline = asyncio.get_running_loop().time() + 1
                while actor._pending_mark_spoken_id is not None:
                    assert asyncio.get_running_loop().time() < deadline
                    await asyncio.sleep(.005)
                assert sent == [frame]
                if phase == "summary":
                    assert engine.state.summary_delivered
                else:
                    assert engine.state.delivered_question.intent == "important_to_share"
            response = reply(STORY[0], "story")
            assert not engine.state.call_closed
            assert not engine.state.summary_delivered
            if cancelled and phase == "invitation":
                assert not engine.state.important_to_share_resolved
            else:
                assert response.intent == "thread_invite" and not response.marks_question
                assert engine.state.important_to_share_resolved
            assert engine.state.slots["plans"] == SlotStatus.OPEN
            assert "important_to_share" not in engine.state.observations
        finally:
            await actor.stop()

    asyncio.run(scenario())
