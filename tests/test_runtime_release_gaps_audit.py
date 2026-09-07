"""Release-path regressions for 489003e. Test doubles are not model/SIP benchmarks."""

import asyncio
from types import SimpleNamespace

import pytest

from packages.contracts.enums import AsrQuality, FsmState
from packages.contracts.semantic import Evidence, FactCandidate, SemanticPayload
from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.planner import Planner
from packages.dialogue.session import CallSession
from packages.voice_runtime.call_actor import CallActor, MediaCallbacks
from services.llm.http_provider import RenderChunk


async def noop(*args, **kwargs):
    pass


def session_at_wellness():
    session = CallSession(
        call_id="release-audit",
        family_id="audit-family",
        store=InMemoryCallRecordStore(),
    )
    session.start()
    session.state.mandatory_checks.update(identity=True, consent=True, can_talk=True)
    session.state.greeted = True
    session.state.fsm_state = FsmState.DAILY_CHECK
    Planner.plan_vera_turn(session.state, 2, "g2")
    return session


def fact_meaning(text, field):
    return SemanticPayload(
        dialogue_act="answer",
        control="none",
        consent_answer="not_applicable",
        answers_pending_question=False,
        needs_clarification=False,
        facts=(
            FactCandidate(
                field=field,
                value=text,
                subject="speaker",
                temporal_scope="today",
                negated=False,
                evidence=Evidence(start=0, end=len(text), quote=text),
            ),
        ),
    )


def test_out_of_order_inference_does_not_deadlock_actor():
    async def scenario():
        session = session_at_wellness()
        first_entered, second_entered, release_first = (
            asyncio.Event(),
            asyncio.Event(),
            asyncio.Event(),
        )
        texts = {b"first": "Чувствую себя хорошо", b"second": "Спала плохо"}

        async def transcribe(pcm, *args, **kwargs):
            return SimpleNamespace(text=texts[pcm], asr_quality=AsrQuality.GOOD)

        async def interpret(ctx, **kwargs):
            if ctx.raw_text == texts[b"first"]:
                first_entered.set()
                await release_first.wait()
                field = "wellness"
            else:
                second_entered.set()
                field = "sleep"
            return SimpleNamespace(payload=fact_meaning(ctx.raw_text, field))

        actor = CallActor(
            call_id=session.state.call_id,
            family_id="audit-family",
            session=session,
            stt=SimpleNamespace(transcribe_final=transcribe),
            tts=SimpleNamespace(),
            llm=SimpleNamespace(interpret_turn=interpret),
            media=MediaCallbacks(noop, noop, noop, noop),
        )
        actor._deliver_session_turn = noop
        first = asyncio.create_task(actor._handle_utterance(b"first", 1))
        await asyncio.wait_for(first_entered.wait(), 1)
        second = asyncio.create_task(actor._handle_utterance(b"second", 2))
        try:
            await asyncio.wait_for(second_entered.wait(), 1)
            await asyncio.sleep(0)
            release_first.set()
            done, pending = await asyncio.wait({first, second}, timeout=0.2)
            assert not pending, (
                "Both model results ready; actor waits while holding policy lock"
            )
            for task in done:
                task.result()
            assert {"wellness", "sleep"} <= session.state.facts.keys()
        finally:
            release_first.set()
            first.cancel()
            second.cancel()
            await asyncio.gather(first, second, return_exceptions=True)

    asyncio.run(scenario())


def test_stream_done_snapshot_does_not_replay_spoken_phrases():
    async def scenario():
        session = session_at_wellness()
        result = session.handle_user_text("Чувствую себя хорошо")
        spoken = []

        async def stream(*args, **kwargs):
            yield RenderChunk("Поняла.", delta=True)
            yield RenderChunk(" Как вы спали?", delta=True)
            yield RenderChunk("Поняла. Как вы спали?", done=True)

        actor = CallActor(
            call_id=session.state.call_id,
            family_id="audit-family",
            session=session,
            stt=SimpleNamespace(),
            tts=SimpleNamespace(),
            llm=SimpleNamespace(render_stream=stream),
            media=MediaCallbacks(noop, noop, noop, noop),
        )

        async def capture(result, text, generation):
            spoken.append(text)
            return True

        actor._speak_validated_proposal = capture
        await actor._deliver_session_turn(result)
        assert spoken == ["Поняла.", "Как вы спали?"], spoken

    asyncio.run(scenario())


def test_public_media_route_sends_actual_pcm(monkeypatch):
    from services.voice_service import main as service

    pcm = b"\x01\x00" * 320
    holders = {}

    def build(**kwargs):
        actor = SimpleNamespace(
            media=kwargs["media"],
            start=lambda: None,
            stop=noop,
            on_media_ready=noop,
            push_pcm=noop,
        )
        holders["actor"] = actor
        return actor

    class Socket:
        query_params = {}

        def __init__(self):
            self.sent = []

        async def accept(self):
            pass

        async def send_bytes(self, data):
            self.sent.append(data)

        async def send_text(self, data):
            pass

        async def close(self, **kwargs):
            pass

        async def receive(self):
            await holders["actor"].media.send_pcm(pcm)
            return {"type": "websocket.disconnect"}

    monkeypatch.setattr(service, "build_call_actor", build)
    monkeypatch.setattr(service, "record_event", lambda *args: None)
    monkeypatch.setattr(service, "_sessions", {})

    async def scenario():
        created = await service.create_call(
            service.CreateCallRequest(person_id="audit-person")
        )
        socket = Socket()
        await service.media_ws(socket, created["call_id"])
        assert socket.sent == [pcm], (
            "Media route consumed outgoing PCM without sending bytes"
        )

    asyncio.run(scenario())


def test_full_conversation_gate_rejects_silence_and_identity_only(monkeypatch):
    from scripts import voice_sip_e2e as e2e

    def row(kind, **payload):
        return {"type": kind, "payload": payload}

    rows = [
        row("call.started"),
        row("media.ready"),
        row("renderer.phrase_ready", text="Здравствуйте. Это Анна?"),
        row("playback.completed", sent_samples=8000),
        row("stt.final", text="да это я"),
        row("interpretation.ready"),
        row("renderer.phrase_ready", text="Вы согласны на звонки?"),
        row("playback.completed", sent_samples=8000),
        row("call.ended", termination_reason="disconnected"),
    ]
    monkeypatch.setattr(e2e, "_trace_rows", lambda call_id: rows)
    with pytest.raises(AssertionError):
        e2e._assert_full_conversation(
            bytes([0x80]) * 3200, "audit", capture_bytes=640
        )
