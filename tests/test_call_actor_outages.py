"""Outage matrix: one dependency down at a time — the call must not hang/crash.

Each test kills exactly one thing (STT / TTS / LLM / store) and asserts:
- no exception escapes the actor/session entry point,
- the step finishes within TIMEOUT_S (no silent hang),
- the call can continue or finalize sanely afterwards.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from packages.contracts.enums import AsrQuality, FsmState
from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.session import CallSession
from packages.voice_runtime.call_actor import CallActor, MediaCallbacks
from packages.voice_runtime.playback import PlaybackQueue

TIMEOUT_S = 10.0


async def _noop(*_a, **_k):
    return None


def _down(name: str):
    async def _raise(*_a, **_k):
        raise ConnectionError(f"{name} transport down")

    return _raise


def _wellness_session(call_id: str) -> CallSession:
    session = CallSession(
        call_id=call_id,
        family_id="audit-family",
        store=InMemoryCallRecordStore(),
    )
    session.start()
    session.state.mandatory_checks.update(identity=True, consent=True, can_talk=True)
    session.state.greeted = True
    return session


def _actor(session: CallSession, **overrides) -> CallActor:
    return CallActor(
        call_id=session.state.call_id,
        family_id="audit-family",
        session=session,
        stt=overrides.get("stt", SimpleNamespace(transcribe_final=_noop)),
        tts=overrides.get("tts", SimpleNamespace(cancel=_noop)),
        llm=overrides.get("llm", SimpleNamespace(interpret_turn=_noop)),
        media=MediaCallbacks(_noop, _noop, _noop, _noop),
    )


def test_store_outage_turn_still_speaks() -> None:
    """PG down must not mute Vera (P0 G-06): the engine turn is delivered
    from engine state with a degraded marker, same generation, sent once."""

    async def scenario() -> None:
        from packages.contracts.providers import AudioChunk

        session = CallSession(
            call_id="outage-store-speaks",
            family_id="audit-family",
            store=_DownStore(),
        )
        session.start()
        session.state.mandatory_checks.update(identity=True, consent=True, can_talk=True)
        session.state.greeted = True

        async def stt(_pcm, *_a, **_k):
            return SimpleNamespace(text="хорошо", asr_quality=AsrQuality.GOOD)

        async def synthese_ok(*_a, **_k):
            yield AudioChunk(pcm_s16le=b"\x01\x00" * 320, sample_rate=16000, sequence=0)

        sent: list[bytes] = []

        async def send_pcm(data: bytes) -> None:
            sent.append(data)

        actor = _actor(
            session,
            stt=SimpleNamespace(transcribe_final=stt),
            tts=SimpleNamespace(synthesize=synthese_ok, cancel=_noop),
            llm=SimpleNamespace(interpret_turn=_down("llm")),
        )
        actor._playback = PlaybackQueue(call_id=session.state.call_id)
        actor.media = MediaCallbacks(send_pcm, _noop, _noop, _noop)
        pump = asyncio.create_task(actor._playback_pump())

        await asyncio.wait_for(actor._handle_utterance(b"u1", 1), TIMEOUT_S)
        if actor._tts_task is not None:
            await asyncio.wait_for(asyncio.shield(actor._tts_task), TIMEOUT_S)
        # Let the playback pump deliver to media.
        for _ in range(100):
            if sent:
                break
            await asyncio.sleep(0.05)
        pump.cancel()
        assert sent, "Vera must speak on store outage"

    asyncio.run(scenario())


def test_stt_outage_utterance_returns_and_next_turn_works() -> None:
    async def scenario() -> None:
        session = _wellness_session("outage-stt")
        actor = _actor(session, stt=SimpleNamespace(transcribe_final=_down("stt")))

        await asyncio.wait_for(actor._handle_utterance(b"u1", 1), TIMEOUT_S)

        async def stt_ok(_pcm, *_a, **_k):
            return SimpleNamespace(text="хорошо", asr_quality=AsrQuality.GOOD)

        actor.stt = SimpleNamespace(transcribe_final=stt_ok)
        await asyncio.wait_for(actor._handle_utterance(b"u2", 2), TIMEOUT_S)

    asyncio.run(scenario())


def test_tts_outage_speak_phrase_records_failure_without_hang() -> None:
    async def scenario() -> None:
        session = _wellness_session("outage-tts")

        async def synthesize_down(*_a, **_k):
            raise ConnectionError("tts transport down")
            yield  # pragma: no cover — makes this an async generator

        actor = _actor(session, tts=SimpleNamespace(synthesize=synthesize_down))
        actor._playback = PlaybackQueue(call_id=session.state.call_id)
        actor._render_generation = "g-outage"

        await asyncio.wait_for(actor._speak_phrase("Привет.", "g-outage"), TIMEOUT_S)
        assert actor._tts_task is not None
        await asyncio.wait_for(asyncio.shield(actor._tts_task), TIMEOUT_S)

    asyncio.run(scenario())


def test_llm_outage_full_turn_completes_via_rules() -> None:
    async def scenario() -> None:
        session = CallSession(
            call_id="outage-llm",
            family_id="audit-family",
            store=InMemoryCallRecordStore(),
        )
        session.start()
        session.state.fsm_state = FsmState.IDENTIFY_PERSON
        session.state.pending_question = "Я разговариваю с Даниил?"
        session.state.pending_question_delivered = True

        async def stt(_pcm, *_a, **_k):
            return SimpleNamespace(text="Да.", asr_quality=AsrQuality.GOOD)

        actor = _actor(
            session,
            stt=SimpleNamespace(transcribe_final=stt),
            llm=SimpleNamespace(interpret_turn=_down("llm")),
        )
        actor._speak_phrase = _noop  # type: ignore[method-assign]

        await asyncio.wait_for(actor._handle_utterance(b"u1", 1), TIMEOUT_S)

        assert session.state.mandatory_checks.get("identity") is True

    asyncio.run(scenario())


class _DownStore(InMemoryCallRecordStore):
    def ensure_call(self, *_a, **_k):
        raise ConnectionError("pg down")

    def save_observation(self, *_a, **_k):
        raise ConnectionError("pg down")

    def append_event(self, *args, **kwargs):
        raise ConnectionError("pg down")


def test_store_outage_session_start_survives() -> None:
    session = CallSession(
        call_id="outage-store",
        family_id="audit-family",
        store=_DownStore(),
    )
    result = session.start()
    assert result.persist_ok is False
    assert result.persist_error


def test_store_outage_handle_user_text_survives() -> None:
    session = CallSession(
        call_id="outage-store-turn",
        family_id="audit-family",
        store=InMemoryCallRecordStore(),
    )
    session.start()
    session.state.mandatory_checks.update(identity=True, consent=True, can_talk=True)
    session.state.greeted = True
    session._store = _DownStore()

    result = session.handle_user_text("хорошо")
    assert result.proposal is not None


def test_all_down_finalize_disconnect_survives() -> None:
    async def scenario() -> None:
        session = CallSession(
            call_id="outage-all",
            family_id="audit-family",
            store=_DownStore(),
        )
        session.start()
        await asyncio.wait_for(
            asyncio.to_thread(session.finalize_disconnect), TIMEOUT_S
        )
        assert session.state.call_finalized or session.state.final_action_done

    asyncio.run(scenario())
