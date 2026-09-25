"""PostgreSQL-backed CallRecordStore with transactional outbox."""

from __future__ import annotations

import json
import os
import threading
from datetime import UTC, datetime
from typing import Any

from packages.contracts.core import (
    CallObservation,
    CallRecordStore,
    CallResultSnapshot,
    DeliveryStage,
    PersistResult,
    TerminationReason,
)
from packages.contracts.enums import FsmState
from packages.contracts.events import CallEvent

PRODUCT_BINDING_META_KEY = "product_call_binding"


def _family_mismatch_result() -> PersistResult:
    return PersistResult(
        ok=False,
        delivery_stage=DeliveryStage.OBSERVATION_RECEIVED,
        error="family mismatch",
    )


def _persist_error(exc: Exception) -> PersistResult:
    return PersistResult(
        ok=False,
        delivery_stage=DeliveryStage.OBSERVATION_RECEIVED,
        error=str(exc),
    )


class PostgresCallRecordStore(CallRecordStore):
    """Pooled PG store (P0 plan 3a): connections come from a bounded pool,
    never per-operation connects. Pool opens lazily on first use so import
    and construction never touch the DB. Exhaustion surfaces as
    PoolTimeout → caught per-method into PersistResult(ok=False), never
    a hot-path hang."""

    def __init__(
        self,
        dsn: str,
        *,
        min_size: int | None = None,
        max_size: int | None = None,
        connect_timeout: float = 5.0,
        pool_timeout: float = 5.0,
    ) -> None:
        self._dsn = dsn
        self._min_size = int(
            min_size if min_size is not None
            else os.environ.get("IMVERA_PG_POOL_MIN", "1")
        )
        self._max_size = int(
            max_size if max_size is not None
            else os.environ.get("IMVERA_PG_POOL_MAX", "10")
        )
        self._connect_timeout = connect_timeout
        self._pool_timeout = pool_timeout
        self._pool = None
        self._pool_lock = threading.Lock()

    def _pool_or_open(self):
        pool = self._pool
        if pool is not None:
            return pool
        with self._pool_lock:
            if self._pool is None:
                from psycopg_pool import ConnectionPool

                self._pool = ConnectionPool(
                    self._dsn,
                    min_size=self._min_size,
                    max_size=self._max_size,
                    timeout=self._pool_timeout,
                    kwargs={"connect_timeout": self._connect_timeout},
                    open=True,
                )
            return self._pool

    def pool_stats(self) -> dict[str, Any]:
        pool = self._pool
        if pool is None:
            return {"opened": False}
        stats = {"opened": True}
        stats.update(pool.get_stats())
        return stats

    def close(self) -> None:
        pool, self._pool = self._pool, None
        if pool is not None:
            pool.close()

    def _connect(self):
        return self._pool_or_open().connection()

    def ensure_call(self, call_id: str, family_id: str) -> PersistResult:
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO call_results (call_id, family_id, fsm_state)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (call_id) DO NOTHING
                        """,
                        (call_id, family_id, FsmState.CALL_START.value),
                    )
                    cur.execute(
                        "SELECT family_id FROM call_results WHERE call_id = %s",
                        (call_id,),
                    )
                    row = cur.fetchone()
                    if row and row[0] != family_id:
                        conn.rollback()
                        return PersistResult(
                            ok=False,
                            delivery_stage=DeliveryStage.OBSERVATION_RECEIVED,
                            error="family_id mismatch",
                        )
                conn.commit()
            return PersistResult(ok=True, delivery_stage=DeliveryStage.OBSERVATION_RECEIVED)
        except Exception as exc:
            return PersistResult(
                ok=False,
                delivery_stage=DeliveryStage.OBSERVATION_RECEIVED,
                error=str(exc),
            )

    def append_event(self, event: CallEvent, family_id: str) -> PersistResult:
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    if not self._check_family(cur, event.call_id, family_id):
                        conn.rollback()
                        return _family_mismatch_result()
                    cur.execute(
                        """
                        INSERT INTO call_events (
                            event_id, call_id, family_id, sequence_no, event_type,
                            payload, idempotency_key, occurred_at
                        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (idempotency_key) DO NOTHING
                        """,
                        (
                            event.event_id,
                            event.call_id,
                            family_id,
                            event.sequence_no,
                            event.event_type,
                            json.dumps(event.payload),
                            event.idempotency_key,
                            event.occurred_at,
                        ),
                    )
                conn.commit()
            return PersistResult(ok=True, delivery_stage=DeliveryStage.PERSISTED)
        except Exception as exc:
            return _persist_error(exc)

    def save_observation(
        self,
        observation: CallObservation,
        family_id: str,
    ) -> PersistResult:
        try:
            with self._connect() as conn:
                with conn.transaction():
                    with conn.cursor() as cur:
                        if not self._check_family(cur, observation.call_id, family_id):
                            return _family_mismatch_result()
                        cur.execute(
                            """
                            INSERT INTO call_observations (
                                observation_id, call_id, family_id, turn_id, field,
                                value, source_quote, subject, negated, risk_level,
                                episode_id, idempotency_key, created_at
                            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                            ON CONFLICT (idempotency_key) DO NOTHING
                            RETURNING observation_id
                            """,
                            (
                                observation.observation_id,
                                observation.call_id,
                                family_id,
                                observation.turn_id,
                                observation.field,
                                observation.value,
                                observation.source_quote,
                                observation.subject,
                                observation.negated,
                                observation.risk_level.value,
                                observation.episode_id,
                                observation.idempotency_key,
                                observation.created_at,
                            ),
                        )
                        inserted = cur.fetchone()
                        if inserted:
                            self._merge_observation_into_result(cur, observation, family_id)
                            cur.execute(
                                """
                                INSERT INTO outbox (idempotency_key, call_id, family_id, payload)
                                VALUES (%s,%s,%s,%s)
                                ON CONFLICT (idempotency_key) DO NOTHING
                                """,
                                (
                                    observation.idempotency_key,
                                    observation.call_id,
                                    family_id,
                                    json.dumps(
                                        {
                                            "type": "observation",
                                            "id": observation.observation_id,
                                        }
                                    ),
                                ),
                            )
                return PersistResult(ok=True, delivery_stage=DeliveryStage.PERSISTED)
        except Exception as exc:
            return _persist_error(exc)

    def finalize_call(self, snapshot: CallResultSnapshot) -> PersistResult:
        try:
            with self._connect() as conn:
                with conn.transaction():
                    with conn.cursor() as cur:
                        if not self._check_family(cur, snapshot.call_id, snapshot.family_id):
                            return _family_mismatch_result()
                        ended_key = f"{snapshot.call_id}:CALL_ENDED"
                        cur.execute(
                            "SELECT 1 FROM call_events WHERE idempotency_key = %s",
                            (ended_key,),
                        )
                        already = cur.fetchone() is not None
                        cur.execute(
                            """
                            INSERT INTO call_results (
                                call_id, family_id, fsm_state, facts, fact_quotes,
                                observations, delivery_stage, partial, call_ended,
                                termination_reason, metadata, updated_at
                            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                            ON CONFLICT (call_id) DO UPDATE SET
                                family_id = EXCLUDED.family_id,
                                fsm_state = EXCLUDED.fsm_state,
                                facts = EXCLUDED.facts,
                                fact_quotes = EXCLUDED.fact_quotes,
                                observations = EXCLUDED.observations,
                                delivery_stage = EXCLUDED.delivery_stage,
                                partial = EXCLUDED.partial,
                                call_ended = EXCLUDED.call_ended,
                                termination_reason = EXCLUDED.termination_reason,
                                metadata = EXCLUDED.metadata,
                                updated_at = EXCLUDED.updated_at
                            """,
                            (
                                snapshot.call_id,
                                snapshot.family_id,
                                snapshot.fsm_state.value,
                                json.dumps(snapshot.facts),
                                json.dumps(snapshot.fact_quotes),
                                json.dumps(snapshot.observations),
                                DeliveryStage.PERSISTED.value,
                                snapshot.partial,
                                snapshot.call_ended,
                                (
                                    snapshot.termination_reason.value
                                    if snapshot.termination_reason
                                    else None
                                ),
                                json.dumps(snapshot.metadata),
                                datetime.now(UTC),
                            ),
                        )
                        if snapshot.call_ended and not already:
                            cur.execute(
                                """
                                INSERT INTO outbox (idempotency_key, call_id, family_id, payload)
                                VALUES (%s,%s,%s,%s)
                                ON CONFLICT (idempotency_key) DO NOTHING
                                """,
                                (
                                    ended_key,
                                    snapshot.call_id,
                                    snapshot.family_id,
                                    json.dumps({"type": "CALL_ENDED"}),
                                ),
                            )
                return PersistResult(ok=True, delivery_stage=DeliveryStage.PERSISTED)
        except Exception as exc:
            return _persist_error(exc)

    def get_call_result(self, call_id: str, family_id: str) -> CallResultSnapshot | None:
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT family_id, fsm_state, facts, fact_quotes, observations,
                               delivery_stage, partial, call_ended, termination_reason, metadata
                        FROM call_results WHERE call_id = %s
                        """,
                        (call_id,),
                    )
                    row = cur.fetchone()
                    if not row or row[0] != family_id:
                        return None
                    meta = row[9] or {}
                    mission_result = None
                    outcomes = None
                    if isinstance(meta, dict):
                        from packages.contracts.mission_result import (
                            CallOutcomes,
                            MissionResultSnapshot,
                        )

                        if meta.get("mission_result"):
                            mission_result = MissionResultSnapshot.model_validate(
                                meta["mission_result"]
                            )
                        if meta.get("outcomes"):
                            outcomes = CallOutcomes.model_validate(meta["outcomes"])
                    return CallResultSnapshot(
                        call_id=call_id,
                        family_id=row[0],
                        fsm_state=FsmState(row[1]),
                        facts=row[2] or {},
                        fact_quotes=row[3] or {},
                        observations=row[4] or [],
                        delivery_stage=DeliveryStage(row[5]),
                        partial=row[6],
                        call_ended=row[7],
                        termination_reason=TerminationReason(row[8]) if row[8] else None,
                        metadata=meta,
                        mission_result=mission_result,
                        outcomes=outcomes,
                    )
        except Exception:
            return None

    def get_events(self, call_id: str, family_id: str) -> list[CallEvent]:
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT event_id, call_id, sequence_no, occurred_at, event_type,
                               payload, idempotency_key
                        FROM call_events
                        WHERE call_id = %s AND family_id = %s
                        ORDER BY sequence_no
                        """,
                        (call_id, family_id),
                    )
                    return [
                        CallEvent(
                            event_id=r[0],
                            call_id=r[1],
                            sequence_no=r[2],
                            occurred_at=r[3],
                            event_type=r[4],
                            payload=r[5] or {},
                            idempotency_key=r[6],
                        )
                        for r in cur.fetchall()
                    ]
        except Exception:
            return []

    def save_dialogue_snapshot(
        self,
        snapshot: CallResultSnapshot,
        family_id: str,
    ) -> PersistResult:
        try:
            with self._connect() as conn:
                with conn.transaction():
                    with conn.cursor() as cur:
                        if not self._check_family(cur, snapshot.call_id, family_id):
                            return _family_mismatch_result()
                        cur.execute(
                            """
                            UPDATE call_results SET
                                family_id = %s,
                                fsm_state = %s,
                                facts = %s,
                                fact_quotes = %s,
                                partial = %s,
                                termination_reason = %s,
                                metadata = %s,
                                updated_at = %s
                            WHERE call_id = %s
                            """,
                            (
                                family_id,
                                snapshot.fsm_state.value,
                                json.dumps(snapshot.facts),
                                json.dumps(snapshot.fact_quotes),
                                snapshot.partial,
                                (
                                    snapshot.termination_reason.value
                                    if snapshot.termination_reason
                                    else None
                                ),
                                json.dumps(snapshot.metadata),
                                datetime.now(UTC),
                                snapshot.call_id,
                            ),
                        )
            return PersistResult(ok=True, delivery_stage=DeliveryStage.PERSISTED)
        except Exception as exc:
            return _persist_error(exc)

    def put_call_binding(self, binding: dict[str, Any]) -> PersistResult:
        call_id = str(binding.get("call_id") or "")
        family_id = str(binding.get("family_id") or "")
        if not call_id or not family_id:
            return PersistResult(
                ok=False,
                delivery_stage=DeliveryStage.OBSERVATION_RECEIVED,
                error="call_id and family_id required",
            )
        try:
            with self._connect() as conn:
                with conn.transaction():
                    with conn.cursor() as cur:
                        if not self._check_family(cur, call_id, family_id):
                            return _family_mismatch_result()
                        cur.execute(
                            "SELECT metadata FROM call_results WHERE call_id = %s",
                            (call_id,),
                        )
                        row = cur.fetchone()
                        meta = dict(row[0] or {}) if row else {}
                        meta[PRODUCT_BINDING_META_KEY] = dict(binding)
                        cur.execute(
                            """
                            UPDATE call_results
                            SET metadata = %s, updated_at = %s
                            WHERE call_id = %s
                            """,
                            (json.dumps(meta), datetime.now(UTC), call_id),
                        )
            return PersistResult(ok=True, delivery_stage=DeliveryStage.PERSISTED)
        except Exception as exc:
            return _persist_error(exc)

    def get_call_binding(self, call_id: str) -> dict[str, Any] | None:
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT metadata FROM call_results WHERE call_id = %s",
                        (call_id,),
                    )
                    row = cur.fetchone()
                    if not row:
                        return None
                    meta = row[0] or {}
                    if not isinstance(meta, dict):
                        return None
                    raw = meta.get(PRODUCT_BINDING_META_KEY)
                    return dict(raw) if isinstance(raw, dict) else None
        except Exception:
            return None

    def get_call_binding_by_fs_uuid(self, fs_uuid: str) -> dict[str, Any] | None:
        if not fs_uuid:
            return None
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT metadata
                        FROM call_results
                        WHERE metadata #>> %s = %s
                        LIMIT 1
                        """,
                        ([PRODUCT_BINDING_META_KEY, "metadata", "fs_uuid"], fs_uuid),
                    )
                    row = cur.fetchone()
                    if not row:
                        return None
                    meta = row[0] or {}
                    if not isinstance(meta, dict):
                        return None
                    raw = meta.get(PRODUCT_BINDING_META_KEY)
                    return dict(raw) if isinstance(raw, dict) else None
        except Exception:
            return None

    def delete_call_binding(self, call_id: str) -> PersistResult:
        try:
            with self._connect() as conn:
                with conn.transaction():
                    with conn.cursor() as cur:
                        cur.execute(
                            "SELECT metadata FROM call_results WHERE call_id = %s",
                            (call_id,),
                        )
                        row = cur.fetchone()
                        if not row:
                            return PersistResult(
                                ok=True,
                                delivery_stage=DeliveryStage.OBSERVATION_RECEIVED,
                            )
                        meta = dict(row[0] or {})
                        meta.pop(PRODUCT_BINDING_META_KEY, None)
                        cur.execute(
                            """
                            UPDATE call_results
                            SET metadata = %s, updated_at = %s
                            WHERE call_id = %s
                            """,
                            (json.dumps(meta), datetime.now(UTC), call_id),
                        )
            return PersistResult(ok=True, delivery_stage=DeliveryStage.PERSISTED)
        except Exception as exc:
            return _persist_error(exc)

    @staticmethod
    def _check_family(cur, call_id: str, family_id: str) -> bool:
        cur.execute("SELECT family_id FROM call_results WHERE call_id = %s", (call_id,))
        row = cur.fetchone()
        if row is None:
            cur.execute(
                "INSERT INTO call_results (call_id, family_id, fsm_state) VALUES (%s,%s,%s)",
                (call_id, family_id, FsmState.CALL_START.value),
            )
            return True
        return row[0] == family_id

    @staticmethod
    def _merge_observation_into_result(
        cur,
        observation: CallObservation,
        family_id: str,
    ) -> None:
        cur.execute(
            "SELECT facts, fact_quotes, observations FROM call_results WHERE call_id = %s",
            (observation.call_id,),
        )
        row = cur.fetchone()
        facts: dict[str, Any] = dict(row[0] or {}) if row else {}
        quotes: dict[str, Any] = dict(row[1] or {}) if row else {}
        obs_ids: list[str] = list(row[2] or []) if row else []
        if observation.field:
            facts[observation.field] = observation.value
            quotes[observation.field] = observation.source_quote
        if observation.observation_id not in obs_ids:
            obs_ids.append(observation.observation_id)
        cur.execute(
            """
            UPDATE call_results SET
                family_id = %s,
                facts = %s,
                fact_quotes = %s,
                observations = %s,
                delivery_stage = %s,
                updated_at = %s
            WHERE call_id = %s
            """,
            (
                family_id,
                json.dumps(facts),
                json.dumps(quotes),
                json.dumps(obs_ids),
                DeliveryStage.PERSISTED.value,
                datetime.now(UTC),
                observation.call_id,
            ),
        )
