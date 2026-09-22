"""Cut 1 delivery: composer bridge accepted/rejected/fallback in CallActor."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from packages.contracts.enums import AnswerJudgement, DialogueAct
from packages.contracts.interpretation import TurnInterpretation
from packages.contracts.turn import TurnProposal
from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.interpretation import UserInterpretation
from packages.dialogue.session import CallSession, SessionTurnResult
from packages.dialogue.validator import Validator
from packages.dialogue_engine.effects import SpeakEffect
from packages.voice_runtime.call_actor import CallActor, CallActorConfig, MediaCallbacks
from packages.voice_runtime.playback import PlaybackQueue
from services.llm.http_provider import RenderChunk

pytestmark = pytest.mark.dialogue_engine

BRIDGE = "Поняла вас. Боль сильная или терпимая?"
QUESTION = "Боль сильная или терпимая?"
ORIGINAL = "Поняла вас. Боль сильная или терпимая?"
USER_TEXT = "Сильно болит голова."


async def noop(*args, **kwargs):
    pass


def engine_result_with_bridge(session: CallSession) -> SessionTurnResult:
    session.turn_id += 1
    proposal = TurnProposal(
        turn_id=session.turn_id,
        generation_id="g-ep",
        speech=ORIGINAL,
        intent="episode_headache_severity",
        fsm_state=session.state.fsm_state,
        mandatory_remaining=session.state.mandatory_remaining(),
    )
    validated = Validator.validate(proposal)
    interp = UserInterpretation(
        judgement=AnswerJudgement.VALID, dialogue_act=DialogueAct.ANSWER
    )
    contract = TurnInterpretation(
        call_id=session.state.call_id,
        turn_id=session.turn_id,
        raw_text=USER_TEXT,
        dialogue_act=DialogueAct.ANSWER,
        judgement=AnswerJudgement.VALID,
        state_version=session.state.state_version,
    )
    fx = SpeakEffect(
        effect_id="fx-1",
        revision=1,
        generation_id="g-ep",
        generation=1,
        text=ORIGINAL,
        intent="episode_headache_severity",
        question_id="g-ep",
        marks_question=True,
        bridge_text=BRIDGE,
        question_text=QUESTION,
        bridge_llm_allowed=True,
    )
    return SessionTurnResult(
        user_text=USER_TEXT,
        interpretation=interp,
        turn_contract=contract,
        proposal=proposal,
        validated=validated,
        safety=session.safety.model_copy(deep=True),
        from_engine=True,
        speak_effect=fx,
    )


def run_delivery(monkeypatch, stream, env_on: bool = True) -> list[str]:
    async def scenario():
        session = CallSession(
            call_id="composer",
            family_id="audit-family",
            store=InMemoryCallRecordStore(),
        )
        session.state.mandatory_checks.update(
            identity=True, consent=True, can_talk=True
        )
        session.state.greeted = True
        result = engine_result_with_bridge(session)
        spoken: list[str] = []
        pcm = b"\x01\x00" * 320

        async def synthesize(text, **kwargs):
            spoken.append(text)
            yield SimpleNamespace(pcm_s16le=pcm, sample_rate=16000)

        calls: list[str] = []

        async def fake_stream(*args, **kwargs):
            calls.append("render")
            async for c in stream():
                yield c

        actor = CallActor(
            call_id=session.state.call_id,
            family_id=session.state.family_id,
            session=session,
            stt=SimpleNamespace(),
            tts=SimpleNamespace(synthesize=synthesize, cancel=noop),
            llm=SimpleNamespace(render_stream=fake_stream, cancel_request=noop),
            media=MediaCallbacks(noop, noop, noop, noop),
            config=CallActorConfig(telephony_stream=False, post_speech_pause_ms=0),
        )
        actor._playback = PlaybackQueue(call_id=actor.call_id, sample_rate=16000)
        actor._playback_task = asyncio.create_task(actor._playback_pump())
        monkeypatch.setenv("IMVERA_COMPOSER_BRIDGE", "1" if env_on else "0")
        await actor._deliver_session_turn(result)
        actor._playback_task.cancel()
        await actor._cancel_wait_timer()
        await asyncio.gather(actor._playback_task, return_exceptions=True)
        return spoken, calls

    return asyncio.run(scenario())


def test_composer_accept_rewrites_bridge_only(monkeypatch: pytest.MonkeyPatch) -> None:
    async def stream():
        yield RenderChunk("Сочувствую, боль", delta=True)
        yield RenderChunk(" действительно сильная", delta=True)
        yield RenderChunk("Сочувствую, боль действительно сильная", done=True)

    spoken, calls = run_delivery(monkeypatch, stream)
    assert calls == ["render"]
    assert spoken == ["Сочувствую, боль действительно сильная. " + QUESTION]


def test_composer_reject_keeps_original_byte_identical(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def stream():
        yield RenderChunk("Нужно проверить, как вы чувствуетесь", done=True)

    spoken, calls = run_delivery(monkeypatch, stream)
    assert calls == ["render"]
    assert " ".join(spoken) == ORIGINAL


def test_composer_llm_error_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    async def stream():
        raise RuntimeError("worker down")
        yield  # pragma: no cover

    spoken, calls = run_delivery(monkeypatch, stream)
    assert " ".join(spoken) == ORIGINAL


def test_composer_flag_off_never_calls_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    async def stream():
        raise AssertionError("must not run")

    spoken, calls = run_delivery(monkeypatch, stream, env_on=False)
    assert calls == []
    assert " ".join(spoken) == ORIGINAL
