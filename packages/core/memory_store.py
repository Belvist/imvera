"""In-memory store — unit tests; OBSERVATION_RECEIVED until finalize_call."""

from datetime import UTC, datetime
from threading import Lock
from typing import Any

from packages.contracts.core import (
    CallObservation,
    CallRecordStore,
    CallResultSnapshot,
    DeliveryStage,
    PersistResult,
)
from packages.contracts.enums import FsmState
from packages.contracts.events import CallEvent
from packages.dialogue.facts import FactRecord

PRODUCT_BINDING_META_KEY = "product_call_binding"


def _family_mismatch_result() -> PersistResult:
    return PersistResult(
        ok=False,
        delivery_stage=DeliveryStage.OBSERVATION_RECEIVED,
        error="family mismatch",
    )


class InMemoryCallRecordStore(CallRecordStore):
    def __init__(self, *, shared: dict[str, Any] | None = None) -> None:
        """If ``shared`` is provided, multiple store instances share the same dicts.

        Use this to simulate two processes without Python module globals.
        Production uses PostgresCallRecordStore with the same DSN instead.
        """
        self._lock = Lock()
        if shared is None:
            self._events: dict[str, list[CallEvent]] = {}
            self._observations: dict[str, list[CallObservation]] = {}
            self._results: dict[str, CallResultSnapshot] = {}
            self._idempotency: set[str] = set()
            self._finalized_calls: set[str] = set()
        else:
            self._events = shared.setdefault("events", {})
            self._observations = shared.setdefault("observations", {})
            self._results = shared.setdefault("results", {})
            self._idempotency = shared.setdefault("idempotency", set())
            self._finalized_calls = shared.setdefault("finalized_calls", set())

    def ensure_call(self, call_id: str, family_id: str) -> PersistResult:
        with self._lock:
            if call_id not in self._results:
                self._results[call_id] = CallResultSnapshot(
                    call_id=call_id,
                    family_id=family_id,
                    fsm_state=FsmState.CALL_START,
                    delivery_stage=DeliveryStage.OBSERVATION_RECEIVED,
                    partial=True,
                )
            elif self._results[call_id].family_id != family_id:
                return PersistResult(
                    ok=False,
                    delivery_stage=DeliveryStage.OBSERVATION_RECEIVED,
                    error="family_id mismatch",
                )
            return PersistResult(ok=True, delivery_stage=DeliveryStage.OBSERVATION_RECEIVED)

    def append_event(self, event: CallEvent, family_id: str) -> PersistResult:
        with self._lock:
            if event.idempotency_key in self._idempotency:
                return PersistResult(ok=True, delivery_stage=DeliveryStage.PERSISTED)
            row = self._results.get(event.call_id)
            if row and row.family_id != family_id:
                return _family_mismatch_result()
            self._idempotency.add(event.idempotency_key)
            self._events.setdefault(event.call_id, []).append(event)
            stage = row.delivery_stage if row else DeliveryStage.OBSERVATION_RECEIVED
            return PersistResult(ok=True, delivery_stage=stage)

    def save_observation(
        self,
        observation: CallObservation,
        family_id: str,
    ) -> PersistResult:
        with self._lock:
            if observation.idempotency_key in self._idempotency:
                row = self._results.get(observation.call_id)
                stage = row.delivery_stage if row else DeliveryStage.OBSERVATION_RECEIVED
                return PersistResult(ok=True, delivery_stage=stage)
            row = self._results.get(observation.call_id)
            if row is None:
                row = CallResultSnapshot(
                    call_id=observation.call_id,
                    family_id=family_id,
                    fsm_state=FsmState.CALL_START,
                )
            elif row.family_id != family_id:
                return _family_mismatch_result()

            self._idempotency.add(observation.idempotency_key)
            self._observations.setdefault(observation.call_id, []).append(observation)
            facts = dict(row.facts)
            quotes = dict(row.fact_quotes)
            if observation.field:
                facts[observation.field] = observation.value
                quotes[observation.field] = observation.source_quote
            obs_ids = list(row.observations)
            obs_ids.append(observation.observation_id)
            self._results[observation.call_id] = row.model_copy(
                update={
                    "family_id": family_id,
                    "facts": facts,
                    "fact_quotes": quotes,
                    "observations": obs_ids,
                    "delivery_stage": DeliveryStage.OBSERVATION_RECEIVED,
                }
            )
            return PersistResult(ok=True, delivery_stage=DeliveryStage.OBSERVATION_RECEIVED)

    def finalize_call(self, snapshot: CallResultSnapshot) -> PersistResult:
        with self._lock:
            existing = self._results.get(snapshot.call_id)
            if existing and existing.family_id != snapshot.family_id:
                return _family_mismatch_result()
            if snapshot.call_id in self._finalized_calls and snapshot.call_ended:
                snap = self._results.get(snapshot.call_id)
                stage = snap.delivery_stage if snap else DeliveryStage.PERSISTED
                return PersistResult(ok=True, delivery_stage=stage)
            if snapshot.call_ended:
                self._finalized_calls.add(snapshot.call_id)
            existing = self._results.get(snapshot.call_id)
            merged_metadata = dict(existing.metadata) if existing else {}
            merged_metadata.update(snapshot.metadata)
            self._results[snapshot.call_id] = snapshot.model_copy(
                update={
                    "delivery_stage": DeliveryStage.PERSISTED,
                    "metadata": merged_metadata,
                }
            )
            return PersistResult(ok=True, delivery_stage=DeliveryStage.PERSISTED)

    def get_call_result(self, call_id: str, family_id: str) -> CallResultSnapshot | None:
        with self._lock:
            row = self._results.get(call_id)
            if row is None or row.family_id != family_id:
                return None
            return row

    def get_events(self, call_id: str, family_id: str) -> list[CallEvent]:
        with self._lock:
            row = self._results.get(call_id)
            if row is None or row.family_id != family_id:
                return []
            return list(self._events.get(call_id, []))

    def get_latest_family_snapshot(
        self,
        family_id: str,
        *,
        exclude_call_id: str | None = None,
    ) -> CallResultSnapshot | None:
        """Most recent finalized call for a family — used for cross-call follow-up."""
        with self._lock:
            candidates: list[CallResultSnapshot] = []
            for call_id, row in self._results.items():
                if row.family_id != family_id:
                    continue
                if exclude_call_id and call_id == exclude_call_id:
                    continue
                if not row.call_ended:
                    continue
                candidates.append(row)
            if not candidates:
                return None
            return candidates[-1]

    def save_dialogue_snapshot(
        self,
        snapshot: CallResultSnapshot,
        family_id: str,
    ) -> PersistResult:
        with self._lock:
            row = self._results.get(snapshot.call_id)
            if row is None:
                return PersistResult(
                    ok=False,
                    delivery_stage=DeliveryStage.OBSERVATION_RECEIVED,
                    error="call missing",
                )
            if row.family_id != family_id:
                return _family_mismatch_result()
            self._results[snapshot.call_id] = snapshot.model_copy(
                update={"delivery_stage": DeliveryStage.PERSISTED}
            )
            return PersistResult(ok=True, delivery_stage=DeliveryStage.PERSISTED)

    def put_call_binding(self, binding: dict[str, Any]) -> PersistResult:
        call_id = str(binding.get("call_id") or "")
        family_id = str(binding.get("family_id") or "")
        if not call_id or not family_id:
            return PersistResult(
                ok=False,
                delivery_stage=DeliveryStage.OBSERVATION_RECEIVED,
                error="call_id and family_id required",
            )
        with self._lock:
            row = self._results.get(call_id)
            if row is None:
                row = CallResultSnapshot(
                    call_id=call_id,
                    family_id=family_id,
                    fsm_state=FsmState.CALL_START,
                    delivery_stage=DeliveryStage.OBSERVATION_RECEIVED,
                    partial=True,
                )
            elif row.family_id != family_id:
                return _family_mismatch_result()
            meta = dict(row.metadata)
            meta[PRODUCT_BINDING_META_KEY] = dict(binding)
            self._results[call_id] = row.model_copy(update={"metadata": meta})
            return PersistResult(ok=True, delivery_stage=DeliveryStage.PERSISTED)

    def get_call_binding(self, call_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._results.get(call_id)
            if row is None:
                return None
            raw = row.metadata.get(PRODUCT_BINDING_META_KEY)
            return dict(raw) if isinstance(raw, dict) else None

    def get_call_binding_by_fs_uuid(self, fs_uuid: str) -> dict[str, Any] | None:
        if not fs_uuid:
            return None
        with self._lock:
            for row in self._results.values():
                raw = row.metadata.get(PRODUCT_BINDING_META_KEY)
                if not isinstance(raw, dict):
                    continue
                meta = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
                if meta.get("fs_uuid") == fs_uuid:
                    return dict(raw)
            return None

    def delete_call_binding(self, call_id: str) -> PersistResult:
        with self._lock:
            row = self._results.get(call_id)
            if row is None:
                return PersistResult(ok=True, delivery_stage=DeliveryStage.OBSERVATION_RECEIVED)
            meta = dict(row.metadata)
            meta.pop(PRODUCT_BINDING_META_KEY, None)
            self._results[call_id] = row.model_copy(update={"metadata": meta})
            return PersistResult(ok=True, delivery_stage=DeliveryStage.PERSISTED)

    def clear_call_bindings(self) -> None:
        with self._lock:
            for call_id, row in list(self._results.items()):
                meta = dict(row.metadata)
                if PRODUCT_BINDING_META_KEY not in meta:
                    continue
                meta.pop(PRODUCT_BINDING_META_KEY, None)
                self._results[call_id] = row.model_copy(update={"metadata": meta})


def observation_from_fact(
    call_id: str,
    turn_id: int,
    fact: FactRecord,
    obs_seq: int,
) -> CallObservation:
    return CallObservation(
        observation_id=f"{call_id}-obs-{obs_seq}",
        call_id=call_id,
        turn_id=turn_id,
        field=fact.field,
        value=fact.value,
        source_quote=fact.source_quote,
        subject=fact.subject,
        negated=fact.negated,
        idempotency_key=f"{call_id}:fact:{fact.field}:r{fact.revision}",
        created_at=datetime.now(UTC),
    )


def observation_from_risk(
    call_id: str,
    turn_id: int,
    quote: str,
    obs_seq: int,
    episode_id: str | None,
) -> CallObservation:
    from packages.contracts.enums import RiskLevel

    return CallObservation(
        observation_id=f"{call_id}-risk-{obs_seq}",
        call_id=call_id,
        turn_id=turn_id,
        field=None,
        value=quote,
        source_quote=quote,
        risk_level=RiskLevel.RED,
        episode_id=episode_id,
        idempotency_key=f"{call_id}:risk:{turn_id}:{episode_id or 'none'}",
        created_at=datetime.now(UTC),
    )
