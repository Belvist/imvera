"""In-memory durable store — real persistence contract, replaceable with Core DB."""

from datetime import UTC, datetime
from threading import Lock

from packages.contracts.core import CallObservation, CallResultSnapshot, DeliveryStage
from packages.contracts.enums import FsmState
from packages.contracts.events import CallEvent
from packages.dialogue.facts import FactRecord


class CallRecordStore:
    """Thread-safe store for one deployment; idempotent append."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._events: dict[str, list[CallEvent]] = {}
        self._observations: dict[str, list[CallObservation]] = {}
        self._results: dict[str, CallResultSnapshot] = {}
        self._idempotency: set[str] = set()
        self._seq: dict[str, int] = {}

    def _next_seq(self, call_id: str) -> int:
        self._seq[call_id] = self._seq.get(call_id, 0) + 1
        return self._seq[call_id]

    def append_event(self, event: CallEvent) -> bool:
        with self._lock:
            if event.idempotency_key in self._idempotency:
                return False
            self._idempotency.add(event.idempotency_key)
            self._events.setdefault(event.call_id, []).append(event)
            return True

    def save_observation(self, observation: CallObservation) -> bool:
        with self._lock:
            if observation.idempotency_key in self._idempotency:
                return False
            self._idempotency.add(observation.idempotency_key)
            self._observations.setdefault(observation.call_id, []).append(observation)
            result = self._results.get(observation.call_id)
            if result is None:
                result = CallResultSnapshot(
                    call_id=observation.call_id,
                    family_id="",
                    fsm_state=FsmState.DAILY_CHECK,
                    delivery_stage=DeliveryStage.PERSISTED,
                    partial=True,
                )
            facts = dict(result.facts)
            quotes = dict(result.fact_quotes)
            if observation.field:
                facts[observation.field] = observation.value
                quotes[observation.field] = observation.source_quote
            obs_ids = list(result.observations)
            obs_ids.append(observation.observation_id)
            self._results[observation.call_id] = result.model_copy(
                update={
                    "facts": facts,
                    "fact_quotes": quotes,
                    "observations": obs_ids,
                    "delivery_stage": DeliveryStage.PERSISTED,
                    "partial": True,
                }
            )
            return True

    def upsert_call_result(self, snapshot: CallResultSnapshot) -> None:
        with self._lock:
            self._results[snapshot.call_id] = snapshot

    def get_call_result(self, call_id: str) -> CallResultSnapshot | None:
        with self._lock:
            return self._results.get(call_id)

    def get_events(self, call_id: str) -> list[CallEvent]:
        with self._lock:
            return list(self._events.get(call_id, []))

    def get_observations(self, call_id: str) -> list[CallObservation]:
        with self._lock:
            return list(self._observations.get(call_id, []))


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
