"""Lightweight ActionPolicy shadow telemetry transport — no frozen policy imports.

Dependency direction:

    config
      ↑
   transport (this module)
      ↑           ↑
   session     evaluator

CallSession / DialogueEngine must import only this module (or config) for
drain / requeue / health / buffer — never action_policy_shadow evaluator.
"""

from __future__ import annotations

from typing import Any

from packages.dialogue_engine.action_policy_shadow_config import (
    FROZEN_POLICY_SHA,
    POLICY_VERSION,
    SHADOW_BUFFER_MAX,
    SHADOW_SCHEMA_VERSION,
    empty_shadow_health,
    ensure_shadow_health,
)


def buffer_shadow_record(state: Any, record: dict[str, Any]) -> None:
    health = ensure_shadow_health(state)
    health["shadow_records_produced"] = int(health["shadow_records_produced"]) + 1
    buf = getattr(state, "action_policy_shadow_records", None)
    if buf is None:
        try:
            state.action_policy_shadow_records = []
            buf = state.action_policy_shadow_records
        except Exception:
            return
    while len(buf) >= SHADOW_BUFFER_MAX:
        buf.pop(0)
        health["shadow_records_dropped"] = int(health["shadow_records_dropped"]) + 1
        health["telemetry_health"] = "degraded"
    buf.append(record)


# Alias used by conversation_policy fail-open path.
buffer_shadow_record_light = buffer_shadow_record


def drain_shadow_records(state: Any) -> list[dict[str, Any]]:
    buf = getattr(state, "action_policy_shadow_records", None)
    if not buf:
        return []
    out = list(buf)
    buf.clear()
    return out


def requeue_shadow_records(state: Any, records: list[dict[str, Any]]) -> None:
    if not records:
        return
    health = ensure_shadow_health(state)
    health["shadow_records_retry"] = int(health["shadow_records_retry"]) + len(records)
    health["shadow_records_persist_failed"] = int(
        health["shadow_records_persist_failed"]
    ) + len(records)
    buf = getattr(state, "action_policy_shadow_records", None)
    if buf is None:
        try:
            state.action_policy_shadow_records = []
            buf = state.action_policy_shadow_records
        except Exception:
            return
    for record in records:
        if len(buf) >= SHADOW_BUFFER_MAX:
            health["shadow_records_dropped"] = int(health["shadow_records_dropped"]) + 1
            health["telemetry_health"] = "degraded"
            continue
        buf.append(record)


def mark_shadow_persisted(state: Any, count: int = 1) -> None:
    health = ensure_shadow_health(state)
    health["shadow_records_persisted"] = int(health["shadow_records_persisted"]) + count


def shadow_health_counters(state: Any) -> dict[str, Any]:
    return dict(ensure_shadow_health(state))


def buffer_remaining(state: Any) -> int:
    buf = getattr(state, "action_policy_shadow_records", None)
    return len(buf) if buf else 0


def compute_telemetry_health_status(state: Any) -> dict[str, Any]:
    """Derive ACTION_POLICY_SHADOW_HEALTH payload fields from ephemeral counters."""
    health = ensure_shadow_health(state)
    produced = int(health.get("shadow_records_produced", 0) or 0)
    persisted = int(health.get("shadow_records_persisted", 0) or 0)
    dropped = int(health.get("shadow_records_dropped", 0) or 0)
    remaining = buffer_remaining(state)
    retry = int(health.get("shadow_records_retry", 0) or 0)
    persist_failed = int(health.get("shadow_records_persist_failed", 0) or 0)

    complete = produced == persisted and dropped == 0 and remaining == 0
    if complete:
        status = "complete"
    elif dropped > 0 or remaining > 0 or persist_failed > persisted:
        status = "incomplete"
    else:
        status = "degraded"

    # Mirror into ephemeral health for operators.
    health["telemetry_health"] = status
    return {
        "schema_version": SHADOW_SCHEMA_VERSION,
        "policy_version": POLICY_VERSION,
        "frozen_policy_sha": FROZEN_POLICY_SHA,
        "records_produced": produced,
        "records_persisted": persisted,
        "retry_count": retry,
        "persist_failed_count": persist_failed,
        "dropped_count": dropped,
        "buffer_remaining": remaining,
        "telemetry_health": status,
        "telemetry_complete": complete,
    }


def reset_shadow_health_for_tests(state: Any) -> None:
    """Test helper — not used on production call path."""
    try:
        state.action_policy_shadow_health = empty_shadow_health()
        state.action_policy_shadow_records = []
    except Exception:
        pass
