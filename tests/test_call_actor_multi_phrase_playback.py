"""Multi-phrase render stream — sequential TTS/playback, deferred turn finalize."""

import asyncio
from types import SimpleNamespace

from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.planner import Planner
from packages.dialogue.session import CallSession
from packages.voice_runtime.call_actor import CallActor, CallActorConfig, MediaCallbacks
from packages.voice_runtime.opening_cache import CachedOpening
from packages.voice_runtime.playback import PlaybackQueue
from services.llm.http_provider import RenderChunk


async def noop(*args, **kwargs):
    pass


def wellness_session():
    session = CallSession(
        call_id="multi-phrase",
        family_id="audit-family",
        store=InMemoryCallRecordStore(),
    )
    session.state.mandatory_checks.update(identity=True, consent=True, can_talk=True)
    session.state.greeted = True
    proposal = Planner.plan_vera_turn(session.state, 1, "question-1")
    session.mark_spoken_action(proposal.generation_id)
    return session


def test_streaming_phrases_speak_sequentially_not_concurrently():
    async def scenario():
        session = wellness_session()
        result = session.handle_user_text("Чувствую себя хорошо")
        tts_started: list[str] = []
        tts_active: list[str] = []
        pcm = b"\x01\x00" * 320

        async def synthesize(text, **kwargs):
            tts_started.append(text)
            assert not tts_active, f"Concurrent TTS while {tts_active[0]!r} active"
            tts_active.append(text)
            yield SimpleNamespace(pcm_s16le=pcm, sample_rate=16000)
            tts_active.clear()

        async def stream(*args, **kwargs):
            yield RenderChunk("Поняла.", delta=True)
            yield RenderChunk(" Как вы спали?", delta=True)
            yield RenderChunk("Поняла. Как вы спали?", done=True)

        actor = CallActor(
            call_id=session.state.call_id,
            family_id=session.state.family_id,
            session=session,
            stt=SimpleNamespace(),
            tts=SimpleNamespace(synthesize=synthesize, cancel=noop),
            llm=SimpleNamespace(render_stream=stream, cancel_request=noop),
            media=MediaCallbacks(noop, noop, noop, noop),
            config=CallActorConfig(telephony_stream=False),
        )
        actor._playback = PlaybackQueue(call_id=actor.call_id, sample_rate=16000)
        actor._playback_task = asyncio.create_task(actor._playback_pump())

        await actor._deliver_session_turn(result)

        assert tts_started == ["Поняла.", "Как вы спали?"]
        assert actor._delivered_phrases == ["Поняла.", "Как вы спали?"]
        assert actor._wait_state is not None, "Answer wait starts only after full turn"
        actor._playback_task.cancel()
        await actor._cancel_wait_timer()
        await asyncio.gather(actor._playback_task, return_exceptions=True)

    asyncio.run(scenario())


def test_barge_in_during_multi_phrase_cancels_render_generation():
    async def scenario():
        session = wellness_session()
        result = session.handle_user_text("Чувствую себя хорошо")

        async def synthesize(text, **kwargs):
            yield SimpleNamespace(pcm_s16le=b"\x01\x00" * 320, sample_rate=16000)

        async def stream(*args, **kwargs):
            yield RenderChunk("Поняла.", delta=True)
            await asyncio.sleep(0.05)
            yield RenderChunk(" Как вы спали?", delta=True)
            yield RenderChunk("Поняла. Как вы спали?", done=True)

        actor = CallActor(
            call_id=session.state.call_id,
            family_id=session.state.family_id,
            session=session,
            stt=SimpleNamespace(),
            tts=SimpleNamespace(synthesize=synthesize, cancel=noop),
            llm=SimpleNamespace(render_stream=stream, cancel_request=noop),
            media=MediaCallbacks(noop, noop, noop, noop),
            config=CallActorConfig(telephony_stream=False),
        )
        actor._playback = PlaybackQueue(call_id=actor.call_id, sample_rate=16000)
        actor._playback_task = asyncio.create_task(actor._playback_pump())

        deliver = asyncio.create_task(actor._deliver_session_turn(result))
        await asyncio.sleep(0.02)
        await actor._interrupt_playback(flush=True)
        await asyncio.wait_for(deliver, timeout=2.0)
        assert actor._render_generation is None
        actor._playback_task.cancel()
        await asyncio.gather(actor._playback_task, return_exceptions=True)

    asyncio.run(scenario())


def test_tts_failure_releases_reserved_attempt_without_starting_wait():
    async def scenario():
        session = CallSession(
            call_id="tts-fail",
            family_id="audit-family",
            store=InMemoryCallRecordStore(),
        )
        open_result = session.start()
        goal = session.state.get_goal("wellness")
        assert goal is not None
        assert goal.reserved_attempt_id == open_result.proposal.generation_id

        async def failing_synthesize(*args, **kwargs):
            raise RuntimeError("tts down")
            yield  # pragma: no cover

        actor = CallActor(
            call_id=session.state.call_id,
            family_id="audit-family",
            session=session,
            stt=SimpleNamespace(),
            tts=SimpleNamespace(synthesize=failing_synthesize, cancel=noop),
            llm=SimpleNamespace(cancel_request=noop),
            media=MediaCallbacks(noop, noop, noop, noop),
            config=CallActorConfig(telephony_stream=False),
        )
        actor._playback = PlaybackQueue(call_id=actor.call_id, sample_rate=16000)
        actor._playback_task = asyncio.create_task(actor._playback_pump())

        await actor._deliver_session_turn(open_result)

        goal = session.state.get_goal("wellness")
        assert goal is not None
        assert goal.reserved_attempt_id is None
        assert actor._wait_state is None
        actor._playback_task.cancel()
        await asyncio.gather(actor._playback_task, return_exceptions=True)

    asyncio.run(scenario())


def test_opening_cache_plays_without_live_tts(monkeypatch):
    async def scenario():
        session = CallSession(
            call_id="opening-cache",
            family_id="audit-family",
            store=InMemoryCallRecordStore(),
        )
        open_result = session.start()
        speech = open_result.validated.speech
        cached_pcm = b"\x01\x00" * 3200
        tts_called = False

        async def synthesize(*args, **kwargs):
            nonlocal tts_called
            tts_called = True
            yield SimpleNamespace(pcm_s16le=b"\x00\x00" * 320, sample_rate=16000)

        monkeypatch.setattr(
            "packages.voice_runtime.call_actor.load_opening",
            lambda text: CachedOpening(text, cached_pcm, 16000)
            if text == speech
            else None,
        )

        sent: list[bytes] = []

        async def send_pcm(pcm: bytes) -> None:
            sent.append(pcm)

        actor = CallActor(
            call_id=session.state.call_id,
            family_id="audit-family",
            session=session,
            stt=SimpleNamespace(),
            tts=SimpleNamespace(synthesize=synthesize, cancel=noop),
            llm=SimpleNamespace(cancel_request=noop),
            media=MediaCallbacks(send_pcm, noop, noop, noop),
            config=CallActorConfig(telephony_stream=False),
        )
        actor._playback = PlaybackQueue(call_id=actor.call_id, sample_rate=16000)
        actor._playback_task = asyncio.create_task(actor._playback_pump())

        await actor._deliver_session_turn(open_result)

        assert not tts_called
        assert sent, "Cached opening PCM should reach the downlink"
        actor._playback_task.cancel()
        await asyncio.gather(actor._playback_task, return_exceptions=True)

    asyncio.run(scenario())


def test_barge_in_before_second_phrase_skips_second_tts():
    async def scenario():
        session = wellness_session()
        result = session.handle_user_text("Чувствую себя хорошо")
        tts_started: list[str] = []

        async def synthesize(text, **kwargs):
            tts_started.append(text)
            yield SimpleNamespace(pcm_s16le=b"\x01\x00" * 320, sample_rate=16000)

        async def stream(*args, **kwargs):
            yield RenderChunk("Поняла.", delta=True)
            await asyncio.sleep(0.05)
            yield RenderChunk(" Как вы спали?", delta=True)
            yield RenderChunk("Поняла. Как вы спали?", done=True)

        actor = CallActor(
            call_id=session.state.call_id,
            family_id=session.state.family_id,
            session=session,
            stt=SimpleNamespace(),
            tts=SimpleNamespace(synthesize=synthesize, cancel=noop),
            llm=SimpleNamespace(render_stream=stream, cancel_request=noop),
            media=MediaCallbacks(noop, noop, noop, noop),
            config=CallActorConfig(telephony_stream=False),
        )
        actor._playback = PlaybackQueue(call_id=actor.call_id, sample_rate=16000)
        actor._playback_task = asyncio.create_task(actor._playback_pump())

        deliver = asyncio.create_task(actor._deliver_session_turn(result))
        await asyncio.sleep(0.02)
        await actor._interrupt_playback(flush=True)
        await asyncio.wait_for(deliver, timeout=2.0)
        assert tts_started == ["Поняла."]
        actor._playback_task.cancel()
        await asyncio.gather(actor._playback_task, return_exceptions=True)

    asyncio.run(scenario())
