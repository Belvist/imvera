"""Lightweight ActionPolicy shadow config — no frozen policy imports.

MODE=off excludes broad medical cutover; personal-thread authority is reported separately.
"""

from __future__ import annotations

import os
from typing import Any

# Historical v9/v10 baselines remain immutable. v11 preserves unknown/refusal
# evidence in the existing snapshot. Exact-source CI is required before pinning.
HISTORICAL_BASELINE_SHA = "254f0baed11ba7913d276c50ca7bd574778f19a5"
FROZEN_POLICY_SHA: str | None = None
POLICY_STATUS = "candidate"
POLICY_VERSION = "action-policy-phase1-v11"
ACTIVE_POLICY_MANIFEST = "docs/evaluation/action-policy-v11-disposition-candidate-manifest.json"


def policy_provenance() -> dict[str, Any]:
    """Truthful lightweight provenance; no filesystem/model work on the hot path."""
    return {
        "frozen_policy_sha": FROZEN_POLICY_SHA,
        "historical_baseline_sha": HISTORICAL_BASELINE_SHA,
        "policy_status": POLICY_STATUS,
        "policy_version": POLICY_VERSION,
        "active_policy_manifest": ACTIVE_POLICY_MANIFEST,
    }


SHADOW_SCHEMA_VERSION = 1
SHADOW_BUFFER_MAX = 64
DECISION_SCOPE = "conversation_scheduler"

# Effective modes after kill switches. "off" is an alias for "legacy".
_ALLOWED_MODES = frozenset({"off", "legacy", "shadow", "soft", "policy"})

ERROR_FLAG_BY_STAGE = {
    "turn_context_view": "shadow_context_error",
    "build_policy_snapshot": "shadow_snapshot_error",
    "choose": "shadow_choose_error",
    "policy_constraint": "policy_constraint_violation",
    "finalize": "shadow_finalize_error",
    "shadow_wrapper": "shadow_choose_error",
    "import": "shadow_choose_error",
    "authoritative_fallback": "authoritative_fallback_legacy",
}


def cutover_enabled() -> bool:
    """Hard kill companion for soft/policy. Default false — fail secure."""
    raw = os.environ.get("IMVERA_ACTION_POLICY_CUTOVER_ENABLED", "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def soft_percent() -> int:
    raw = os.environ.get("IMVERA_ACTION_POLICY_SOFT_PERCENT", "0").strip()
    try:
        return max(0, min(100, int(raw)))
    except ValueError:
        return 0


def action_policy_mode() -> str:
    """Effective router mode. Unknown / ungated soft|policy → legacy."""
    raw = os.environ.get("IMVERA_ACTION_POLICY_MODE", "off").strip().lower()
    if raw not in _ALLOWED_MODES:
        return "legacy"
    if raw in {"off", "legacy"}:
        return "legacy"
    if raw == "shadow":
        return "shadow"
    # soft / policy require explicit cutover enable (no redeploy kill: unset/0).
    if not cutover_enabled():
        return "legacy"
    return raw


def action_policy_runtime_truth() -> dict[str, Any]:
    """Safe for startup even when evaluator package is broken."""
    return {
        "action_policy.mode": action_policy_mode(),
        "action_policy.mode_raw": os.environ.get("IMVERA_ACTION_POLICY_MODE", "off"),
        "action_policy.cutover_enabled": cutover_enabled(),
        "action_policy.soft_percent": soft_percent(),
        "action_policy.policy_version": POLICY_VERSION,
        "action_policy.frozen_policy_sha": FROZEN_POLICY_SHA,
        "action_policy.decision_scope": DECISION_SCOPE,
        "action_policy.personal_thread_authority": "action_policy_v11",
        "action_policy.personal_thread_scope": "grounded_nonurgent_daily",
        "action_policy.historical_baseline_sha": HISTORICAL_BASELINE_SHA,
        "action_policy.policy_status": POLICY_STATUS,
        "action_policy.active_policy_manifest": ACTIVE_POLICY_MANIFEST,
        "IMVERA_ACTION_POLICY_MODE": os.environ.get("IMVERA_ACTION_POLICY_MODE", "off"),
        "IMVERA_ACTION_POLICY_CUTOVER_ENABLED": os.environ.get(
            "IMVERA_ACTION_POLICY_CUTOVER_ENABLED", ""
        ),
        "IMVERA_ACTION_POLICY_SOFT_PERCENT": os.environ.get(
            "IMVERA_ACTION_POLICY_SOFT_PERCENT", "0"
        ),
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
        **policy_provenance(),
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
