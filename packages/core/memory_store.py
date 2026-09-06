"""In-memory store — unit tests; OBSERVATION_RECEIVED until finalize_call."""

from datetime import UTC, datetime
from threading import Lock

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


def _family_mismatch_result() -> PersistResult:
    return PersistResult(
        ok=False,
        delivery_stage=DeliveryStage.OBSERVATION_RECEIVED,
        error="family mismatch",
    )


class InMemoryCallRecordStore(CallRecordStore):
    def __init__(self) -> None:
        self._lock = Lock()
        self._events: dict[str, list[CallEvent]] = {}
        self._observations: dict[str, list[CallObservation]] = {}
        self._results: dict[str, CallResultSnapshot] = {}
        self._idempotency: set[str] = set()
        self._finalized_calls: set[str] = set()

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
            self._results[snapshot.call_id] = snapshot.model_copy(
                update={"delivery_stage": DeliveryStage.PERSISTED}
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
