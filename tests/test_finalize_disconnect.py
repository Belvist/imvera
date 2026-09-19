"""Regression: CallActor._finalize_disconnect must reach session finalization.

Covers the Cut-2 bug where `is_finalized` was read as a bound method
(always truthy) so disconnect finalization never ran on live calls.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from packages.contracts.core import TerminationReason
from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.session import CallSession
from packages.voice_runtime.call_actor import CallActor, MediaCallbacks

pytestmark = pytest.mark.dialogue_engine


async def _noop(*_a, **_k):
    return None


def _actor(session: CallSession) -> CallActor:
    return CallActor(
        call_id=session.state.call_id,
        family_id="audit-family",
        session=session,
        stt=SimpleNamespace(),
        tts=SimpleNamespace(),
        llm=SimpleNamespace(),
        media=MediaCallbacks(_noop, _noop, _noop, _noop),
    )


def test_disconnect_finalizes_unfinalized_session() -> None:
    async def scenario() -> None:
        session = CallSession(
            call_id="actor-disc",
            family_id="audit-family",
            store=InMemoryCallRecordStore(),
        )
        actor = _actor(session)
        calls: list[str] = []
        original = session.finalize_disconnect

        def recording() -> None:
            calls.append("finalize_disconnect")
            original()

        session.finalize_disconnect = recording  # type: ignore[method-assign]
        assert not session.is_finalized()
        await actor._finalize_disconnect()
        assert calls == ["finalize_disconnect"]
        assert session.state.final_action_done is True
        assert session.state.termination_reason == TerminationReason.DISCONNECTED
        assert session.is_finalized()

    import asyncio

    asyncio.run(scenario())


def test_disconnect_returns_early_when_finalized() -> None:
    async def scenario() -> None:
        session = CallSession(
            call_id="actor-disc-done",
            family_id="audit-family",
            store=InMemoryCallRecordStore(),
        )
        actor = _actor(session)
        session.state.call_finalized = True
        calls: list[str] = []

        def recording() -> None:
            calls.append("finalize_disconnect")

        session.finalize_disconnect = recording  # type: ignore[method-assign]
        await actor._finalize_disconnect()
        assert calls == []

    import asyncio

    asyncio.run(scenario())
