"""Telephony stream must wait audible duration before listen (fs-bf61f52b)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.session import CallSession
from packages.voice_runtime.call_actor import CallActor, CallActorConfig, MediaCallbacks


async def _noop_async(*_a, **_k):
    return None


def _noop(*_a, **_k):
    return None


@pytest.mark.asyncio
async def test_audible_wait_holds_for_sent_duration(monkeypatch: pytest.MonkeyPatch) -> None:
    session = CallSession(
        call_id="audible-wait",
        family_id="audit-family",
        store=InMemoryCallRecordStore(),
    )
    session.start()
    clock = {"t": 1000.0}
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock["t"] += seconds

    actor = CallActor(
        call_id=session.state.call_id,
        family_id="audit-family",
        session=session,
        stt=SimpleNamespace(),
        tts=SimpleNamespace(),
        llm=SimpleNamespace(),
        media=MediaCallbacks(_noop_async, _noop_async, _noop_async, _noop_async),
        config=CallActorConfig(telephony_stream=True, post_speech_pause_ms=0),
    )
    actor._monotonic = lambda: clock["t"]
    actor._output_sample_rate = 16000
    # 112800 samples @ 16kHz ≈ 7.05s — opening-scale blast from fs-bf61f52b
    actor._playout_first_send_mono = 1000.0
    clock["t"] = 1000.4  # ~400ms after first send (queue already drained)
    monkeypatch.setattr("packages.voice_runtime.call_actor.asyncio.sleep", fake_sleep)

    await actor._await_audible_playout_end(112_800)

    assert sleeps, "expected audible wait sleep"
    assert sleeps[0] == pytest.approx(7.05 - 0.4, abs=0.05)


@pytest.mark.asyncio
async def test_audible_wait_noop_when_already_elapsed(monkeypatch: pytest.MonkeyPatch) -> None:
    session = CallSession(
        call_id="audible-done",
        family_id="audit-family",
        store=InMemoryCallRecordStore(),
    )
    session.start()
    clock = {"t": 1010.0}
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock["t"] += seconds

    actor = CallActor(
        call_id=session.state.call_id,
        family_id="audit-family",
        session=session,
        stt=SimpleNamespace(),
        tts=SimpleNamespace(),
        llm=SimpleNamespace(),
        media=MediaCallbacks(_noop_async, _noop_async, _noop_async, _noop_async),
        config=CallActorConfig(telephony_stream=True, post_speech_pause_ms=0),
    )
    actor._monotonic = lambda: clock["t"]
    actor._output_sample_rate = 16000
    actor._playout_first_send_mono = 1000.0
    monkeypatch.setattr("packages.voice_runtime.call_actor.asyncio.sleep", fake_sleep)

    await actor._await_audible_playout_end(16_000)

    assert sleeps == []
