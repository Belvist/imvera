"""External review: behavioural regressions at e0e86b0; no model/SIP claims."""

import asyncio
from types import SimpleNamespace

from packages.contracts.enums import AnswerJudgement, DialogueAct, FsmState
from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.interpretation import UserInterpretation
from packages.dialogue.planner import Planner
from packages.dialogue.session import CallSession
from packages.dialogue.state import DialogueState
from packages.voice_runtime.call_actor import CallActor, MediaCallbacks
from packages.voice_runtime.playback import PlaybackQueue


async def noop(*args, **kwargs):
    pass


def daily_session(delivered=True):
    session = CallSession(
        call_id="e0-review",
        family_id="review-family",
        store=InMemoryCallRecordStore(),
    )
    session.state.mandatory_checks.update(identity=True, consent=True, can_talk=True)
    session.state.greeted = True
    session.state.fsm_state = FsmState.DAILY_CHECK
    proposal = Planner.plan_vera_turn(session.state, 1, "question-1")
    assert session.transitions.commit_transition(session.state, proposal).ok
    if delivered:
        session.mark_spoken_action(proposal.generation_id)
    return session, proposal


def backchannel(session):
    return session.handle_user_text(
        "ага",
        interp=UserInterpretation(
            judgement=AnswerJudgement.BACKCHANNEL,
            dialogue_act=DialogueAct.BACKCHANNEL,
        ),
    )


def actor_for(session, **kwargs):
    from packages.voice_runtime.call_actor import CallActorConfig

    config = kwargs.pop("config", None)
    return CallActor(
        call_id=session.state.call_id,
        family_id=session.state.family_id,
        session=session,
        stt=SimpleNamespace(),
        tts=kwargs.get("tts", SimpleNamespace(cancel=noop)),
        llm=SimpleNamespace(),
        media=MediaCallbacks(noop, noop, noop, noop),
        config=config
        or CallActorConfig(lab_half_duplex=True, echo_ref_gate=False),
    )


def install_speech_onset(actor):
    calls = []

    def feed(pcm):
        calls.append(pcm)
        return True, False

    actor._ensure_input_chain = noop
    actor._input_resampler = SimpleNamespace(process=lambda pcm: pcm)
    actor._vad = SimpleNamespace(feed=feed)
    actor._collector = SimpleNamespace(on_frame=lambda *args: None)
    actor._media_ready = True
    return calls


def test_speech_onset_then_backchannel_keeps_a_live_wait_deadline():
    async def scenario():
        session, proposal = daily_session()
        actor = actor_for(session)
        clock = [0.0]
        actor._monotonic = lambda: clock[0]
        install_speech_onset(actor)
        applied = []

        async def capture(result):
            applied.append(result)

        actor._post_apply_turn = capture
        actor._start_answer_wait(
            goal_id=session.state.get_goal("wellness").goal_id,
            question_id=proposal.generation_id,
        )
        try:
            clock[0] = 1.0
            await actor._on_pcm(b"\x01\x00" * 320, 16000)
            result = backchannel(session)
            await actor._handle_backchannel_continuation(result)
            wait = actor._wait_state
            assert wait is not None
            actor._wait_task.cancel()
            await asyncio.gather(actor._wait_task, return_exceptions=True)
            clock[0] = wait.deadline_mono + 1
            await actor._on_wait_deadline(wait.wait_id, wait.control_epoch)
            assert len(applied) == 1, "Speech onset made the resumed answer timer stale"
            assert applied[0].proposal.intent.startswith("clarify_")
        finally:
            await actor._cancel_wait_timer()

    asyncio.run(scenario())


def test_incoming_audio_muted_while_vera_speaks_half_duplex():
    """Half-duplex: during active TTS, uplink must not reach VAD (echo self-barge-in gate)."""

    async def scenario():
        session, _ = daily_session()
        actor = actor_for(session)
        vad_calls = install_speech_onset(actor)
        actor._playback = PlaybackQueue(call_id=actor.call_id)
        actor._playback.begin_phrase("speaking", "phrase", "Расскажите...")
        actor._active_generation = "speaking"
        actor._render_generation = "speaking"
        await actor._on_pcm(b"\x01\x00" * 320, 16000)
        assert not vad_calls, "Uplink must be muted during active TTS (half-duplex)"
        assert actor._active_generation == "speaking"

        actor._active_generation = None
        await actor._on_pcm(b"\x01\x00" * 320, 16000)
        assert vad_calls, "After playback ends, uplink must reach VAD again"

    asyncio.run(scenario())


def test_blocked_tts_does_not_mark_question_delivered_or_start_answer_wait():
    async def scenario():
        session, _ = daily_session()
        backchannel(session)
        result = session.handle_wait_expired()
        assert not session.state.pending_question_delivered
        gate = asyncio.Event()

        async def synthesize(*args, **kwargs):
            await gate.wait()
            yield SimpleNamespace(pcm_s16le=b"\x01\x00" * 320, sample_rate=16000)

        actor = actor_for(session, tts=SimpleNamespace(synthesize=synthesize, cancel=noop))
        actor._playback = PlaybackQueue(call_id=actor.call_id)
        actor._playback_task = asyncio.create_task(actor._playback_pump())
        actor._render_generation = "render-review"
        actor._outbox_action_id = result.proposal.generation_id
        try:
            speak_task = asyncio.create_task(
                actor._speak_validated_proposal(
                    result, result.proposal.speech, "render-review"
                )
            )
            await asyncio.sleep(0.05)
            assert actor._playback._ledger.generated_samples == 0
            assert not session.state.pending_question_delivered, (
                "Question is marked delivered while the TTS provider has emitted zero PCM"
            )
            assert actor._wait_state is None, "Answer window started before question audio"
            speak_task.cancel()
            await asyncio.gather(speak_task, return_exceptions=True)
        finally:
            if actor._tts_task:
                actor._tts_task.cancel()
                await asyncio.gather(actor._tts_task, return_exceptions=True)
            actor._playback_task.cancel()
            await asyncio.gather(actor._playback_task, return_exceptions=True)
            await actor._cancel_wait_timer()

    asyncio.run(scenario())


def test_who_are_you_cannot_repeat_wellness_outside_question_budget():
    session, initial = daily_session()
    spoken = [initial.speech]
    for _ in range(5):
        result = session.handle_user_text(
            "Кто вы?",
            interp=UserInterpretation(
                judgement=AnswerJudgement.UNCLEAR,
                asks_who_are_you=True,
            ),
        )
        spoken.append(result.proposal.speech)
        session.mark_spoken_action(result.proposal.generation_id)
    repetitions = sum(initial.speech in text for text in spoken)
    assert repetitions <= 2, f"Same wellness question spoken {repetitions} times via detour"


def test_wait_transition_cannot_replay_superseded_question():
    session, _ = daily_session(delivered=False)
    assert session.transitions.replay_pending_action(session.state.call_id) is not None
    result = backchannel(session)
    assert result.proposal.intent == "wait_for_continuation"
    pending = session.transitions.replay_pending_action(session.state.call_id)
    assert pending is None, f"WAIT leaves old speech pending: {pending}"


def test_question_reservation_cannot_be_overwritten_by_another_action():
    state = DialogueState(call_id="exclusive-review", family_id="fam-voice")
    assert Planner.reserve_question_attempt(state, "first", "wellness")
    assert Planner.reserve_question_attempt(state, "first", "wellness")
    assert not Planner.reserve_question_attempt(state, "second", "wellness"), (
        "A different action overwrote an already reserved question attempt"
    )
    assert state.get_goal("wellness").reserved_attempt_id == "first"
