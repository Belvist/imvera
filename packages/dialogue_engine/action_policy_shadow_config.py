"""Lightweight ActionPolicy shadow config — no frozen policy imports.

MODE=off must work even if action_policy_shadow / action_policy fail to import.
"""

from __future__ import annotations

import os
from typing import Any

# Candidate under development — freeze commit sets immutable SHA.
FROZEN_POLICY_SHA = "UNFROZEN-action-policy-phase1-v8"
POLICY_VERSION = "action-policy-phase1-v8"
SHADOW_SCHEMA_VERSION = 1
SHADOW_BUFFER_MAX = 64
DECISION_SCOPE = "conversation_scheduler"

# Modes — soft/hard intentionally unavailable until DecisionRouter phase.
_ALLOWED_MODES = frozenset({"off", "shadow"})

ERROR_FLAG_BY_STAGE = {
    "turn_context_view": "shadow_context_error",
    "build_policy_snapshot": "shadow_snapshot_error",
    "choose": "shadow_choose_error",
    "policy_constraint": "policy_constraint_violation",
    "finalize": "shadow_finalize_error",
    "shadow_wrapper": "shadow_choose_error",
    "import": "shadow_choose_error",
}


def action_policy_mode() -> str:
    raw = os.environ.get("IMVERA_ACTION_POLICY_MODE", "off").strip().lower()
    if raw in _ALLOWED_MODES:
        return raw
    return "off"


def action_policy_runtime_truth() -> dict[str, Any]:
    """Safe for startup even when evaluator package is broken."""
    return {
        "action_policy.mode": action_policy_mode(),
        "action_policy.policy_version": POLICY_VERSION,
        "action_policy.frozen_policy_sha": FROZEN_POLICY_SHA,
        "action_policy.decision_scope": DECISION_SCOPE,
        "IMVERA_ACTION_POLICY_MODE": os.environ.get("IMVERA_ACTION_POLICY_MODE", "off"),
    }


def empty_shadow_health() -> dict[str, Any]:
    return {
        "shadow_records_produced": 0,
        "shadow_records_persisted": 0,
        "shadow_records_retry": 0,
        "shadow_records_persist_failed": 0,
        "shadow_records_dropped": 0,
        "telemetry_health": "ok",
    }


def ensure_shadow_health(state: Any) -> dict[str, Any]:
    health = getattr(state, "action_policy_shadow_health", None)
    if not isinstance(health, dict):
        health = empty_shadow_health()
        try:
            state.action_policy_shadow_health = health
        except Exception:
            return health
    for key, default in empty_shadow_health().items():
        health.setdefault(key, default)
    return health


def make_error_record(
    state: Any,
    *,
    error_stage: str,
    error_type: str,
    input_kind: str = "timer_or_internal",
    decision_origin: str = "internal_scheduler",
    decision_id: str | None = None,
    utterance_id: str = "",
    engine_revision_before_legacy: int | None = None,
    extra_flags: list[str] | None = None,
) -> dict[str, Any]:
    """Full ACTION_POLICY_SHADOW schema v1 error payload — no exception text."""
    from packages.dialogue_engine.runtime import git_sha_short

    call_id = str(getattr(state, "call_id", "") or "")
    turn_seq = int(getattr(state, "turn_seq", 0) or 0)
    revision = int(
        engine_revision_before_legacy
        if engine_revision_before_legacy is not None
        else (getattr(state, "revision", 0) or 0)
    )
    utt = utterance_id or str(getattr(state, "processing_turn_id", "") or "")
    flag = ERROR_FLAG_BY_STAGE.get(error_stage, "shadow_choose_error")
    flags = [flag]
    if extra_flags:
        for item in extra_flags:
            if item and item not in flags:
                flags.append(item)
    did = decision_id or f"{call_id}:ACTION_POLICY_SHADOW:error:{turn_seq}:{revision}"
    return {
        "schema_version": SHADOW_SCHEMA_VERSION,
        "decision_scope": DECISION_SCOPE,
        "cutover_eligible": False,
        "decision_origin": decision_origin,
        "decision_id": did,
        "turn_id": turn_seq,
        "utterance_id": utt,
        "engine_revision_before_legacy": revision,
        "engine_turn_seq": turn_seq,
        "deployment_sha": git_sha_short(),
        "frozen_policy_sha": FROZEN_POLICY_SHA,
        "policy_version": POLICY_VERSION,
        "input_kind": input_kind,
        "shadow_status": "error",
        "shadow_action": None,
        "legacy_action": None,
        "agree": False,
        "mandatory_class": None,
        "divergence_class": "unclassified",
        "shadow_total_latency_ms": None,
        "policy_choose_latency_ms": None,
        "shadow_latency_ms": None,
        "policy_influenced_output": False,
        "pending_before": {"episode_id": None, "need": None},
        "critical_flags": {
            "urgent": False,
            "control": False,
            "repair": False,
            "user_question": False,
            "pending_obligation": False,
            "new_speaker_issue": False,
        },
        "snapshot_summary": None,
        "chosen_score": None,
        "chosen_contributions": None,
        "candidate_count": None,
        "rejection_rule_ids": None,
        "error_stage": error_stage,
        "error_type": error_type,
        "critical_violation": True,
        "critical_violation_flags": flags,
        "snapshot_fingerprint_sha256": None,
        "idempotency_key": f"{call_id}:ACTION_POLICY_SHADOW:{did}",
    }
