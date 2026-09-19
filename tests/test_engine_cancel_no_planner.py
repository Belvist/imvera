"""Cut 3a: engine cancellation never touches legacy Planner (A.5.3).

The reservation lifecycle (reserve/release) lives only in legacy plan
flows, so on the engine path there is nothing to release. Regression for
the C4 tail: cancelled engine outbox must not call Planner.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from packages.contracts.enums import FsmState
from packages.contracts.outbox import ActionOutboxStatus
from packages.contracts.turn import TurnProposal
from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue import planner as planner_module
from packages.dialogue.session import CallSession
from packages.voice_runtime.call_actor import CallActor, MediaCallbacks

pytestmark = pytest.mark.dialogue_engine


async def _noop(*_a, **_k):
    return None


def test_engine_cancel_never_calls_planner(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        session = CallSession(
            call_id="eng-cancel",
            family_id="fam",
            store=InMemoryCallRecordStore(),
        )
        assert session._engine is not None
        proposal = TurnProposal(
            turn_id=1,
            generation_id="g-cancel",
            speech="Поняла.",
            intent="background_mood",
            fsm_state=FsmState.DAILY_CHECK,
            mandatory_remaining=[],
        )
        facts = {"wellness": "Хорошо."}
        commit = session.transitions.commit_engine_transition(
            call_id="eng-cancel",
            facts=facts,
            fact_quotes=dict(facts),
            fsm_state=FsmState.DAILY_CHECK,
            partial=True,
            termination_reason=None,
            state_revision=session._engine.revision,
            proposal=proposal,
        )
        assert commit.ok, commit.error
        actor = CallActor(
            call_id="eng-cancel",
            family_id="fam",
            session=session,
            stt=SimpleNamespace(),
            tts=SimpleNamespace(),
            llm=SimpleNamespace(),
            media=MediaCallbacks(_noop, _noop, _noop, _noop),
        )
        actor._outbox_action_id = "g-cancel"
        calls: list[str] = []
        monkeypatch.setattr(
            planner_module.Planner,
            "release_question_attempt",
            staticmethod(lambda *a, **k: calls.append("release")),
        )
        await actor._finalize_outbox_action(sent_samples=0, outcome="fail")
        assert calls == []
        snap = session.store.get_call_result("eng-cancel", "fam")
        assert snap is not None
        record = snap.metadata["action_outbox"]["g-cancel"]
        assert record["status"] == ActionOutboxStatus.CANCELLED.value

    asyncio.run(scenario())
