"""Transactional dialogue state persistence — mid-call ledger survival."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from packages.contracts.core import (
    CallRecordStore,
    CallResultSnapshot,
    DeliveryStage,
    PersistResult,
)
from packages.contracts.turn import TurnProposal
from packages.dialogue.planner import Planner
from packages.dialogue.state import DialogueState


class PendingAction(BaseModel):
    action_id: str
    turn_id: int
    intent: str
    speech: str
    question_goal_id: str | None = None
    state_version: int


class DialogueTransition(BaseModel):
    state: DialogueState
    pending_action: PendingAction | None = None


def _state_to_metadata(state: DialogueState, pending: PendingAction | None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "dialogue_state": state.model_dump(mode="json"),
        "state_version": state.state_version,
    }
    if pending is not None:
        payload["pending_action"] = pending.model_dump(mode="json")
    return payload


def _load_state_from_snapshot(snapshot: CallResultSnapshot) -> DialogueState | None:
    raw = snapshot.metadata.get("dialogue_state")
    if not raw:
        return None
    return DialogueState.model_validate(raw)


def _load_pending(snapshot: CallResultSnapshot) -> PendingAction | None:
    raw = snapshot.metadata.get("pending_action")
    if not raw:
        return None
    return PendingAction.model_validate(raw)


class DialogueTransitionStore:
    """Persists dialogue state + outbox before TTS execution."""

    def __init__(self, store: CallRecordStore, family_id: str) -> None:
        self._store = store
        self._family_id = family_id

    def load(self, call_id: str) -> DialogueTransition | None:
        snap = self._store.get_call_result(call_id, self._family_id)
        if snap is None:
            return None
        state = _load_state_from_snapshot(snap)
        if state is None:
            return None
        return DialogueTransition(state=state, pending_action=_load_pending(snap))

    def commit_transition(
        self,
        state: DialogueState,
        proposal: TurnProposal,
        *,
        expected_version: int | None = None,
    ) -> PersistResult:
        if expected_version is not None and state.state_version != expected_version:
            return PersistResult(
                ok=False,
                delivery_stage=DeliveryStage.OBSERVATION_RECEIVED,
                error="state version mismatch",
            )

        pending: PendingAction | None = None
        if proposal.intent == "wait_for_continuation":
            pending = None
        elif proposal.speech and proposal.intent not in ("terminal_noop",):
            pending = PendingAction(
                action_id=proposal.generation_id,
                turn_id=proposal.turn_id,
                intent=proposal.intent,
                speech=proposal.speech,
                question_goal_id=proposal.question_goal_id,
                state_version=state.state_version,
            )

        snap = self._store.get_call_result(state.call_id, self._family_id)
        if snap is None:
            ensure = self._store.ensure_call(state.call_id, self._family_id)
            if not ensure.ok:
                return ensure
            snap = self._store.get_call_result(state.call_id, self._family_id)
        if snap is None:
            return PersistResult(
                ok=False,
                delivery_stage=DeliveryStage.OBSERVATION_RECEIVED,
                error="call missing",
            )

        stored_version = snap.metadata.get("state_version", -1)
        if expected_version is not None and stored_version > expected_version:
            return PersistResult(
                ok=False,
                delivery_stage=DeliveryStage.OBSERVATION_RECEIVED,
                error="stale transition",
            )

        metadata = dict(snap.metadata)
        metadata.update(_state_to_metadata(state, pending))
        facts = {k: v.value for k, v in state.facts.items()}
        quotes = {k: v.source_quote for k, v in state.facts.items()}
        updated = snap.model_copy(
            update={
                "fsm_state": state.fsm_state,
                "facts": facts,
                "fact_quotes": quotes,
                "partial": bool(state.mandatory_remaining()),
                "termination_reason": state.termination_reason,
                "metadata": metadata,
            }
        )
        return self._store.save_dialogue_snapshot(updated, self._family_id)

    def mark_action_delivered(self, state: DialogueState, action_id: str) -> PersistResult:
        Planner.mark_question_delivered(state, action_id)
        snap = self._store.get_call_result(state.call_id, self._family_id)
        if snap is None:
            return PersistResult(
                ok=False,
                delivery_stage=DeliveryStage.OBSERVATION_RECEIVED,
                error="call missing",
            )
        metadata = dict(snap.metadata)
        metadata.pop("pending_action", None)
        metadata.update(_state_to_metadata(state, None))
        updated = snap.model_copy(update={"metadata": metadata})
        return self._store.save_dialogue_snapshot(updated, self._family_id)

    def replay_pending_action(self, call_id: str) -> PendingAction | None:
        trans = self.load(call_id)
        if trans is None or trans.pending_action is None:
            return None
        return trans.pending_action
