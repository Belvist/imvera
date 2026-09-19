"""Cut 3: engine-native TransitionStore boundary (A.5.3).

Legacy methods untouched (flag-off + dispatch tests). Engine methods must:
write engine-sourced ledger without the legacy dialogue_state dump, enforce
the same optimistic version + outbox transition rules, preserve store-owned
metadata keys.
"""

from __future__ import annotations

import pytest

from packages.contracts.enums import FsmState
from packages.contracts.outbox import ActionOutboxStatus
from packages.contracts.turn import TurnProposal
from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.transition_store import DialogueTransitionStore

pytestmark = pytest.mark.dialogue_engine


def _store() -> DialogueTransitionStore:
    inner = InMemoryCallRecordStore()
    assert inner.ensure_call("eng-1", "fam").ok
    return DialogueTransitionStore(inner, "fam")


def _proposal(intent: str = "background_mood", speech: str = "Поняла.") -> TurnProposal:
    return TurnProposal(
        turn_id=1,
        generation_id="g-1",
        speech=speech,
        intent=intent,
        fsm_state=FsmState.DAILY_CHECK,
        mandatory_remaining=[],
    )


def test_engine_commit_writes_ledger_without_legacy_dump() -> None:
    store = _store()
    result = store.commit_engine_transition(
        call_id="eng-1",
        facts={"wellness": "Хорошо."},
        fact_quotes={"wellness": "Хорошо."},
        fsm_state=FsmState.DAILY_CHECK,
        partial=True,
        termination_reason=None,
        state_revision=7,
        proposal=_proposal(),
    )
    assert result.ok, result.error
    snap = store._store.get_call_result("eng-1", "fam")
    assert snap is not None
    assert snap.facts == {"wellness": "Хорошо."}
    assert snap.fsm_state == FsmState.DAILY_CHECK
    assert "dialogue_state" not in snap.metadata
    assert snap.metadata["state_version"] == 7
    outbox = snap.metadata["action_outbox"]
    assert outbox["g-1"]["status"] == ActionOutboxStatus.PENDING.value
    assert snap.metadata["pending_action"]["action_id"] == "g-1"


def test_engine_commit_version_guard() -> None:
    store = _store()
    bad = store.commit_engine_transition(
        call_id="eng-1",
        facts={},
        fact_quotes={},
        fsm_state=FsmState.DAILY_CHECK,
        partial=True,
        termination_reason=None,
        state_revision=3,
        proposal=_proposal(),
        expected_version=5,
    )
    assert not bad.ok
    assert bad.error == "state version mismatch"


def test_engine_outbox_lifecycle() -> None:
    store = _store()
    assert store.commit_engine_transition(
        call_id="eng-1",
        facts={},
        fact_quotes={},
        fsm_state=FsmState.DAILY_CHECK,
        partial=True,
        termination_reason=None,
        state_revision=7,
        proposal=_proposal(),
    ).ok
    assert store.mark_engine_outbox_dispatching(
        "eng-1", "g-1", state_revision=8
    ).ok
    done = store.mark_engine_outbox_transport_complete(
        "eng-1", "g-1", sent_samples=160, state_revision=9
    )
    assert done.ok, done.error
    snap = store._store.get_call_result("eng-1", "fam")
    assert snap is not None
    record = snap.metadata["action_outbox"]["g-1"]
    assert record["status"] == ActionOutboxStatus.TRANSPORT_COMPLETE.value
    assert record["sent_samples"] == 160
    assert "dialogue_state" not in snap.metadata
    illegal = store.mark_engine_outbox_cancelled("eng-1", "g-1", state_revision=10)
    assert not illegal.ok


def test_engine_action_delivered_pops_pending() -> None:
    store = _store()
    assert store.commit_engine_transition(
        call_id="eng-1",
        facts={},
        fact_quotes={},
        fsm_state=FsmState.DAILY_CHECK,
        partial=True,
        termination_reason=None,
        state_revision=7,
        proposal=_proposal(),
    ).ok
    assert store.mark_engine_action_delivered("eng-1", "g-1", state_revision=8).ok
    snap = store._store.get_call_result("eng-1", "fam")
    assert snap is not None
    assert snap.metadata.get("pending_action") is None
    assert "dialogue_state" not in snap.metadata


def test_engine_commit_drops_stale_legacy_dump() -> None:
    """Rolling-update edge: a pre-cutover dialogue_state dump must not
    survive engine writes as a stale second state. Store-owned and unknown
    keys survive; outbox and version stay current."""
    store = _store()
    seed = store._store.get_call_result("eng-1", "fam")
    assert seed is not None
    store._store.save_dialogue_snapshot(
        seed.model_copy(
            update={
                "metadata": {
                    **seed.metadata,
                    "dialogue_state": {"old": "stale-mirror"},
                    "product_call_binding": {"trunk": "lab"},
                    "custom_unknown": "keep-me",
                }
            }
        ),
        "fam",
    )
    result = store.commit_engine_transition(
        call_id="eng-1",
        facts={"wellness": "Хорошо."},
        fact_quotes={"wellness": "Хорошо."},
        fsm_state=FsmState.DAILY_CHECK,
        partial=True,
        termination_reason=None,
        state_revision=7,
        proposal=_proposal(),
    )
    assert result.ok, result.error
    snap = store._store.get_call_result("eng-1", "fam")
    assert snap is not None
    assert "dialogue_state" not in snap.metadata
    assert snap.metadata["product_call_binding"] == {"trunk": "lab"}
    assert snap.metadata["custom_unknown"] == "keep-me"
    assert snap.metadata["action_outbox"]["g-1"]["status"] == ActionOutboxStatus.PENDING.value
    assert snap.metadata["state_version"] == 7
