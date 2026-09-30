"""Transactional dialogue state persistence — mid-call ledger + action outbox.

Legacy methods take DialogueState (flag-off path + tests). Engine-native
methods (commit_engine_transition, mark_engine_*, transition_engine_outbox)
take engine-sourced values and never write the legacy dialogue_state dump.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel

from packages.contracts.core import (
    CallRecordStore,
    CallResultSnapshot,
    DeliveryStage,
    PersistResult,
    TerminationReason,
)
from packages.contracts.enums import FsmState
from packages.contracts.outbox import (
    ActionOutboxStatus,
    OutboxRecord,
    apply_transition,
    may_auto_replay,
)
from packages.contracts.turn import TurnProposal
from packages.dialogue.state import DialogueState


class PendingAction(BaseModel):
    action_id: str
    turn_id: int
    intent: str
    speech: str
    question_goal_id: str | None = None
    state_version: int


_log = logging.getLogger("dialogue.transitions")


def _store_failed(exc: Exception) -> PersistResult:
    return PersistResult(
        ok=False,
        delivery_stage=DeliveryStage.OBSERVATION_RECEIVED,
        error=str(exc),
    )


class DialogueTransition(BaseModel):
    state: DialogueState
    pending_action: PendingAction | None = None


def _load_outbox(metadata: dict[str, Any]) -> dict[str, OutboxRecord]:
    raw = metadata.get("action_outbox") or {}
    return {k: OutboxRecord.model_validate(v) for k, v in raw.items()}


def _dump_outbox(records: dict[str, OutboxRecord]) -> dict[str, Any]:
    return {k: v.model_dump(mode="json") for k, v in records.items()}


def _state_to_metadata(
    state: DialogueState,
    pending: PendingAction | None,
    outbox: dict[str, OutboxRecord],
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "dialogue_state": state.model_dump(mode="json"),
        "state_version": state.state_version,
        "action_outbox": _dump_outbox(outbox),
    }
    payload["pending_action"] = (
        pending.model_dump(mode="json") if pending is not None else None
    )
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

    def _read_snapshot(self, call_id: str) -> CallResultSnapshot | None:
        """Fail-open read: store outage → None (call continues unpersisted)."""
        try:
            return self._store.get_call_result(call_id, self._family_id)
        except Exception:
            _log.exception("get_call_result failed call_id=%s", call_id)
            return None

    def _ensure(self, call_id: str) -> PersistResult:
        try:
            return self._store.ensure_call(call_id, self._family_id)
        except Exception as exc:
            _log.exception("ensure_call failed call_id=%s", call_id)
            return _store_failed(exc)

    def _save_snapshot(self, updated: CallResultSnapshot) -> PersistResult:
        try:
            return self._store.save_dialogue_snapshot(updated, self._family_id)
        except Exception as exc:
            _log.exception("save_dialogue_snapshot failed call_id=%s", updated.call_id)
            return _store_failed(exc)

    def load(self, call_id: str) -> DialogueTransition | None:
        """Restore via the legacy dialogue_state dump.

        Scope: legacy flag-off path + dispatch/replay tests only. Engine
        commits (Cut 3) deliberately stop writing the dump, and no
        production engine-path caller uses load()/replay_pending_action()
        (verified by reference scan) — so there is nothing to restore for
        new engine calls. An engine-native replay API is out of scope until
        resume-on-new-call becomes a runtime contract (it is not today).
        """
        snap = self._read_snapshot(call_id)
        if snap is None:
            return None
        state = _load_state_from_snapshot(snap)
        if state is None:
            return None
        return DialogueTransition(state=state, pending_action=_load_pending(snap))

    def get_outbox_record(self, call_id: str, action_id: str) -> OutboxRecord | None:
        snap = self._read_snapshot(call_id)
        if snap is None:
            return None
        return _load_outbox(snap.metadata).get(action_id)

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

        snap = self._read_snapshot(state.call_id)
        if snap is None:
            ensure = self._ensure(state.call_id)
            if not ensure.ok:
                return ensure
            snap = self._read_snapshot(state.call_id)
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

        outbox = _load_outbox(snap.metadata)
        if pending is not None:
            outbox[pending.action_id] = OutboxRecord(
                action_id=pending.action_id,
                call_id=state.call_id,
                turn_id=pending.turn_id,
                intent=pending.intent,
                speech=pending.speech,
                question_goal_id=pending.question_goal_id,
                state_version=pending.state_version,
                status=ActionOutboxStatus.PENDING,
            )

        metadata = dict(snap.metadata)
        metadata.update(_state_to_metadata(state, pending, outbox))
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
        return self._save_snapshot(updated)

    def commit_engine_transition(
        self,
        *,
        call_id: str,
        facts: dict[str, str],
        fact_quotes: dict[str, str],
        fsm_state: FsmState,
        partial: bool,
        termination_reason: TerminationReason | None,
        state_revision: int,
        proposal: TurnProposal,
        expected_version: int | None = None,
    ) -> PersistResult:
        """Engine-native commit: same ledger semantics as commit_transition
        (optimistic version check, pending action, outbox merge) sourced from
        engine values. Writes no legacy dialogue_state dump; sets
        state_version from the engine revision. Read-modify-write starts from
        the stored snapshot, so store-owned keys survive on both backends."""
        if expected_version is not None and state_revision != expected_version:
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
                state_version=state_revision,
            )

        snap = self._read_snapshot(call_id)
        if snap is None:
            ensure = self._ensure(call_id)
            if not ensure.ok:
                return ensure
            snap = self._read_snapshot(call_id)
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

        outbox = _load_outbox(snap.metadata)
        if pending is not None:
            outbox[pending.action_id] = OutboxRecord(
                action_id=pending.action_id,
                call_id=call_id,
                turn_id=pending.turn_id,
                intent=pending.intent,
                speech=pending.speech,
                question_goal_id=pending.question_goal_id,
                state_version=pending.state_version,
                status=ActionOutboxStatus.PENDING,
            )

        metadata = dict(snap.metadata)
        metadata["state_version"] = state_revision
        # Cut 3b: the legacy mirror is superseded on the engine path — drop a
        # stale dump left by pre-cutover writes (rolling update) instead of
        # preserving a second state that never updates again. All other
        # store-owned/unknown keys survive via the snap copy.
        metadata.pop("dialogue_state", None)
        metadata["action_outbox"] = _dump_outbox(outbox)
        metadata["pending_action"] = (
            pending.model_dump(mode="json") if pending is not None else None
        )
        updated = snap.model_copy(
            update={
                "fsm_state": fsm_state,
                "facts": facts,
                "fact_quotes": fact_quotes,
                "partial": partial,
                "termination_reason": termination_reason,
                "metadata": metadata,
            }
        )
        return self._save_snapshot(updated)

    def _transition_outbox(
        self,
        state: DialogueState,
        action_id: str,
        target: ActionOutboxStatus,
        *,
        sent_samples: int | None = None,
    ) -> PersistResult:
        snap = self._read_snapshot(state.call_id)
        if snap is None:
            return PersistResult(
                ok=False,
                delivery_stage=DeliveryStage.OBSERVATION_RECEIVED,
                error="call missing",
            )
        outbox = _load_outbox(snap.metadata)
        record = outbox.get(action_id)
        if record is None:
            return PersistResult(
                ok=False,
                delivery_stage=DeliveryStage.OBSERVATION_RECEIVED,
                error="outbox action missing",
            )
        updated_record = apply_transition(record, target)
        if updated_record is None:
            return PersistResult(
                ok=False,
                delivery_stage=DeliveryStage.OBSERVATION_RECEIVED,
                error=f"illegal outbox transition {record.status} -> {target}",
            )
        if sent_samples is not None:
            updated_record = updated_record.model_copy(update={"sent_samples": sent_samples})
        outbox[action_id] = updated_record

        pending = _load_pending(snap)
        if target in (
            ActionOutboxStatus.TRANSPORT_COMPLETE,
            ActionOutboxStatus.CANCELLED,
            ActionOutboxStatus.DELIVERY_UNKNOWN,
        ):
            if pending and pending.action_id == action_id:
                pending = None

        metadata = dict(snap.metadata)
        metadata.update(_state_to_metadata(state, pending, outbox))
        updated = snap.model_copy(update={"metadata": metadata})
        return self._save_snapshot(updated)

    def mark_outbox_dispatching(self, state: DialogueState, action_id: str) -> PersistResult:
        return self._transition_outbox(state, action_id, ActionOutboxStatus.DISPATCHING)

    def mark_outbox_transport_complete(
        self,
        state: DialogueState,
        action_id: str,
        *,
        sent_samples: int = 0,
    ) -> PersistResult:
        return self._transition_outbox(
            state,
            action_id,
            ActionOutboxStatus.TRANSPORT_COMPLETE,
            sent_samples=sent_samples,
        )

    def mark_outbox_delivery_unknown(
        self,
        state: DialogueState,
        action_id: str,
        *,
        sent_samples: int = 0,
    ) -> PersistResult:
        return self._transition_outbox(
            state,
            action_id,
            ActionOutboxStatus.DELIVERY_UNKNOWN,
            sent_samples=sent_samples,
        )

    def mark_outbox_cancelled(self, state: DialogueState, action_id: str) -> PersistResult:
        return self._transition_outbox(state, action_id, ActionOutboxStatus.CANCELLED)

    def _transition_engine_outbox(
        self,
        call_id: str,
        action_id: str,
        target: ActionOutboxStatus,
        *,
        sent_samples: int | None = None,
        state_revision: int,
    ) -> PersistResult:
        """Engine-native outbox transition: same record mechanics as
        _transition_outbox, no legacy state dump. Metadata starts from the
        stored snapshot (read-modify-write), state_version set from the
        engine revision."""
        snap = self._read_snapshot(call_id)
        if snap is None:
            return PersistResult(
                ok=False,
                delivery_stage=DeliveryStage.OBSERVATION_RECEIVED,
                error="call missing",
            )
        outbox = _load_outbox(snap.metadata)
        record = outbox.get(action_id)
        if record is None:
            return PersistResult(
                ok=False,
                delivery_stage=DeliveryStage.OBSERVATION_RECEIVED,
                error="outbox action missing",
            )
        updated_record = apply_transition(record, target)
        if updated_record is None:
            return PersistResult(
                ok=False,
                delivery_stage=DeliveryStage.OBSERVATION_RECEIVED,
                error=f"illegal outbox transition {record.status} -> {target}",
            )
        if sent_samples is not None:
            updated_record = updated_record.model_copy(update={"sent_samples": sent_samples})
        outbox[action_id] = updated_record

        pending = _load_pending(snap)
        if target in (
            ActionOutboxStatus.TRANSPORT_COMPLETE,
            ActionOutboxStatus.CANCELLED,
            ActionOutboxStatus.DELIVERY_UNKNOWN,
        ):
            if pending and pending.action_id == action_id:
                pending = None

        metadata = dict(snap.metadata)
        metadata["state_version"] = state_revision
        # Cut 3b: drop stale legacy dump (see commit_engine_transition).
        metadata.pop("dialogue_state", None)
        metadata["action_outbox"] = _dump_outbox(outbox)
        metadata["pending_action"] = (
            pending.model_dump(mode="json") if pending is not None else None
        )
        updated = snap.model_copy(update={"metadata": metadata})
        return self._save_snapshot(updated)

    def mark_engine_outbox_dispatching(
        self, call_id: str, action_id: str, *, state_revision: int
    ) -> PersistResult:
        return self._transition_engine_outbox(
            call_id, action_id, ActionOutboxStatus.DISPATCHING, state_revision=state_revision
        )

    def mark_engine_outbox_transport_complete(
        self,
        call_id: str,
        action_id: str,
        *,
        sent_samples: int = 0,
        state_revision: int,
    ) -> PersistResult:
        return self._transition_engine_outbox(
            call_id,
            action_id,
            ActionOutboxStatus.TRANSPORT_COMPLETE,
            sent_samples=sent_samples,
            state_revision=state_revision,
        )

    def mark_engine_outbox_delivery_unknown(
        self,
        call_id: str,
        action_id: str,
        *,
        sent_samples: int = 0,
        state_revision: int,
    ) -> PersistResult:
        return self._transition_engine_outbox(
            call_id,
            action_id,
            ActionOutboxStatus.DELIVERY_UNKNOWN,
            sent_samples=sent_samples,
            state_revision=state_revision,
        )

    def mark_engine_outbox_cancelled(
        self, call_id: str, action_id: str, *, state_revision: int
    ) -> PersistResult:
        return self._transition_engine_outbox(
            call_id, action_id, ActionOutboxStatus.CANCELLED, state_revision=state_revision
        )

    def mark_engine_action_delivered(
        self, call_id: str, action_id: str, *, state_revision: int
    ) -> PersistResult:
        """Engine delivery: outbox dispatch + pending pop, never Planner."""
        dispatch = self.mark_engine_outbox_dispatching(
            call_id, action_id, state_revision=state_revision
        )
        if not dispatch.ok:
            return dispatch
        snap = self._read_snapshot(call_id)
        if snap is None:
            return PersistResult(
                ok=False,
                delivery_stage=DeliveryStage.OBSERVATION_RECEIVED,
                error="call missing",
            )
        metadata = dict(snap.metadata)
        metadata.pop("pending_action", None)
        metadata["state_version"] = state_revision
        # Cut 3b: drop stale legacy dump (see commit_engine_transition).
        metadata.pop("dialogue_state", None)
        updated = snap.model_copy(update={"metadata": metadata})
        return self._save_snapshot(updated)

    def mark_action_delivered(
        self,
        state: DialogueState,
        action_id: str,
        *,
        skip_planner: bool = False,
    ) -> PersistResult:
        if not skip_planner:
            # Flag-off only: engine delivery never passes here (Cut 3b).
            from packages.dialogue.planner import Planner

            Planner.mark_question_delivered(state, action_id)
        dispatch = self.mark_outbox_dispatching(state, action_id)
        if not dispatch.ok:
            return dispatch
        snap = self._read_snapshot(state.call_id)
        if snap is None:
            return PersistResult(
                ok=False,
                delivery_stage=DeliveryStage.OBSERVATION_RECEIVED,
                error="call missing",
            )
        metadata = dict(snap.metadata)
        metadata.pop("pending_action", None)
        outbox = _load_outbox(metadata)
        metadata.update(_state_to_metadata(state, None, outbox))
        updated = snap.model_copy(update={"metadata": metadata})
        return self._save_snapshot(updated)

    def replay_pending_action(self, call_id: str) -> PendingAction | None:
        """Legacy-scope replay (see load()). Not a runtime contract for
        engine-path calls; engine delivery owns its outbox lifecycle."""
        trans = self.load(call_id)
        if trans is None or trans.pending_action is None:
            return None
        snap = self._read_snapshot(call_id)
        if snap is not None and snap.metadata.get("pending_action") is None:
            return None
        record = self.get_outbox_record(call_id, trans.pending_action.action_id)
        if record is not None and not may_auto_replay(record.status):
            return None
        return trans.pending_action
