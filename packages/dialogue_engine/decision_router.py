"""Single DecisionRouter for conversation-scheduler ownership.

Modes (effective, after kill switches):
  legacy — only legacy scheduler (authoritative)
  shadow — immutable ActionPolicy evaluate + legacy authoritative
  soft   — cohort % ActionPolicy authoritative; else legacy; fail → legacy
  policy — ActionPolicy authoritative; fail → legacy

Safety/control/repair outer guards remain outside this module (reducer).
Exactly one mutating scheduler path runs per call.
"""

from __future__ import annotations

import hashlib
from typing import Any, Callable

from packages.dialogue_engine.action_policy_shadow_buffer import buffer_shadow_record
from packages.dialogue_engine.action_policy_shadow_config import (
    action_policy_mode,
    cutover_enabled,
    make_error_record,
    soft_percent,
)
from packages.dialogue_engine.response_plan import ResponsePlan

LegacyScheduler = Callable[[Any, Any], ResponsePlan]


def soft_cohort_selected(call_id: str, *, percent: int | None = None) -> bool:
    """Stable per-call cohort membership for soft mode."""
    pct = soft_percent() if percent is None else int(percent)
    pct = max(0, min(100, pct))
    if pct <= 0:
        return False
    if pct >= 100:
        return True
    digest = hashlib.sha256(f"action-policy-soft:{call_id}".encode("utf-8")).hexdigest()
    return (int(digest[:8], 16) % 100) < pct


def _bump(state: Any, key: str) -> None:
    try:
        stats = getattr(state, "action_policy_router_stats", None)
        if not isinstance(stats, dict):
            stats = {}
            state.action_policy_router_stats = stats
        stats[key] = int(stats.get(key, 0) or 0) + 1
    except Exception:
        return


def _run_shadow_compare(
    state: Any,
    turn_context: Any,
    *,
    legacy: LegacyScheduler,
) -> ResponsePlan:
    """Immutable shadow then exactly one legacy invocation."""
    shadow_record: dict | None = None
    finalize_shadow_record = None
    run_shadow_pre_legacy = None
    try:
        from packages.dialogue_engine.action_policy_shadow import (
            finalize_shadow_record as _finalize,
        )
        from packages.dialogue_engine.action_policy_shadow import (
            run_shadow_pre_legacy as _run,
        )

        finalize_shadow_record = _finalize
        run_shadow_pre_legacy = _run
    except Exception as exc:
        try:
            shadow_record = make_error_record(
                state,
                error_stage="import",
                error_type=type(exc).__name__,
            )
        except Exception:
            shadow_record = None
    else:
        try:
            shadow_record = run_shadow_pre_legacy(state, turn_context)
        except Exception as exc:
            try:
                shadow_record = make_error_record(
                    state,
                    error_stage="shadow_wrapper",
                    error_type=type(exc).__name__,
                )
            except Exception:
                shadow_record = None

    plan = legacy(state, turn_context)
    _bump(state, "legacy_invocations")

    if shadow_record is not None:
        try:
            if finalize_shadow_record is not None:
                finalized = finalize_shadow_record(shadow_record, plan)
                finalized["policy_influenced_output"] = False
                buffer_shadow_record(state, finalized)
            else:
                shadow_record["legacy_action"] = None
                shadow_record["policy_influenced_output"] = False
                buffer_shadow_record(state, shadow_record)
        except Exception as exc:
            try:
                err = make_error_record(
                    state,
                    error_stage="finalize",
                    error_type=type(exc).__name__,
                    decision_id=str(shadow_record.get("decision_id") or ""),
                    utterance_id=str(shadow_record.get("utterance_id") or ""),
                )
                buffer_shadow_record(state, err)
            except Exception:
                pass
    return plan


def _choose_policy_plan(state: Any, turn_context: Any) -> tuple[ResponsePlan, dict[str, Any]]:
    """Exactly one choose() → ResponsePlan. Raises on constraint/import/snapshot failure."""
    import time

    from packages.dialogue_engine.action_policy.bridge import (
        legacy_plan_to_action_key,
        to_response_plan,
    )
    from packages.dialogue_engine.action_policy.mandatory import compute_mandatory_class
    from packages.dialogue_engine.action_policy.policy import choose
    from packages.dialogue_engine.action_policy.snapshot import build_policy_snapshot
    from packages.dialogue_engine.action_policy_shadow import (
        allocate_decision_id,
        evaluate_critical_violation,
        snapshot_fingerprint_sha256,
        turn_context_view_from_scheduler,
    )
    from packages.dialogue_engine.action_policy_shadow_config import (
        DECISION_SCOPE,
        FROZEN_POLICY_SHA,
        POLICY_VERSION,
        SHADOW_SCHEMA_VERSION,
    )
    from packages.dialogue_engine.runtime import git_sha_short

    total_started = time.perf_counter()
    decision_id, utterance_id, revision = allocate_decision_id(state, turn_context)
    ctx, input_kind, decision_origin = turn_context_view_from_scheduler(turn_context)
    snapshot = build_policy_snapshot(state)

    choose_started = time.perf_counter()
    decision = choose(snapshot, ctx)
    choose_ms = (time.perf_counter() - choose_started) * 1000.0
    plan = to_response_plan(decision, snapshot)
    if plan is None or not getattr(plan, "action", None):
        raise RuntimeError("invalid_policy_plan")

    shadow_label = decision.chosen.key.label()
    # Authoritative path: legacy_action mirrors policy (no second scheduler).
    legacy_label = legacy_plan_to_action_key(plan).label()
    if legacy_label != shadow_label:
        # Bridge incompatibility — fail open to legacy via caller.
        raise RuntimeError("bridge_label_mismatch")

    critical, flags = evaluate_critical_violation(
        shadow_label=shadow_label,
        ctx=ctx,
        snapshot=snapshot,
        shadow_status="ok",
        constraint_violation=False,
    )
    if critical:
        raise RuntimeError("critical_violation_blocks_authoritative")

    call_id = str(getattr(state, "call_id", "") or "")
    turn_seq = int(getattr(state, "turn_seq", 0) or 0)
    total_ms = (time.perf_counter() - total_started) * 1000.0
    record: dict[str, Any] = {
        "schema_version": SHADOW_SCHEMA_VERSION,
        "decision_scope": DECISION_SCOPE,
        "cutover_eligible": True,
        "decision_origin": decision_origin,
        "decision_id": decision_id,
        "turn_id": turn_seq,
        "utterance_id": utterance_id,
        "engine_revision_before_legacy": revision,
        "engine_turn_seq": turn_seq,
        "deployment_sha": git_sha_short(),
        "frozen_policy_sha": FROZEN_POLICY_SHA,
        "policy_version": POLICY_VERSION,
        "input_kind": input_kind,
        "shadow_status": "ok",
        "shadow_action": shadow_label,
        "legacy_action": shadow_label,
        "agree": True,
        "mandatory_class": compute_mandatory_class(snapshot, ctx).value,
        "divergence_class": "policy_authoritative",
        "shadow_total_latency_ms": round(total_ms, 4),
        "policy_choose_latency_ms": round(choose_ms, 4),
        "shadow_latency_ms": round(total_ms, 4),
        "policy_influenced_output": True,
        "pending_before": {
            "episode_id": snapshot.active_episode_id,
            "need": snapshot.pending_episode_attribute,
        },
        "critical_flags": {
            "urgent": bool(getattr(ctx, "urgent_risk", False)),
            "control": bool(
                getattr(ctx, "control", None) not in (None, "", "none")
            ),
            "repair": bool(getattr(ctx, "repair", False)),
            "user_question": bool(getattr(ctx, "user_question", False)),
            "pending_obligation": bool(snapshot.pending_episode_attribute),
            "new_speaker_issue": False,
        },
        "snapshot_summary": None,
        "chosen_score": (
            float(decision.candidates[0].score) if decision.candidates else None
        ),
        "chosen_contributions": (
            {
                str(k): float(v)
                for k, v in (decision.candidates[0].contributions or {}).items()
            }
            if decision.candidates
            else None
        ),
        "candidate_count": len(decision.candidates),
        "rejection_rule_ids": sorted(
            {r.rule_id for r in decision.rejected if r.rule_id}
        ),
        "error_stage": "",
        "error_type": "",
        "critical_violation": False,
        "critical_violation_flags": flags,
        "snapshot_fingerprint_sha256": snapshot_fingerprint_sha256(snapshot),
        "idempotency_key": f"{call_id}:ACTION_POLICY_SHADOW:{decision_id}",
        "router_mode": action_policy_mode(),
    }
    return plan, record


def _run_authoritative_policy(
    state: Any,
    turn_context: Any,
    *,
    legacy: LegacyScheduler,
) -> ResponsePlan:
    """ActionPolicy owns scheduler decision; any failure → single legacy fallback."""
    try:
        plan, record = _choose_policy_plan(state, turn_context)
        buffer_shadow_record(state, record)
        _bump(state, "policy_authoritative")
        return plan
    except Exception as exc:
        _bump(state, "policy_fallback_legacy")
        try:
            err = make_error_record(
                state,
                error_stage="authoritative_fallback",
                error_type=type(exc).__name__,
                extra_flags=["authoritative_fallback_legacy"],
            )
            buffer_shadow_record(state, err)
        except Exception:
            pass
        plan = legacy(state, turn_context)
        _bump(state, "legacy_invocations")
        return plan


def route_schedule_next_action(
    state: Any,
    turn_context: Any,
    *,
    legacy: LegacyScheduler,
) -> ResponsePlan:
    """Single routing entry for conversation scheduler decisions."""
    mode = action_policy_mode()
    _bump(state, f"mode_{mode}")

    if mode == "legacy":
        plan = legacy(state, turn_context)
        _bump(state, "legacy_invocations")
        return plan

    if mode == "shadow":
        return _run_shadow_compare(state, turn_context, legacy=legacy)

    # soft / policy — require cutover_enabled (enforced inside action_policy_mode)
    if mode == "soft":
        call_id = str(getattr(state, "call_id", "") or "")
        if not soft_cohort_selected(call_id):
            _bump(state, "soft_cohort_miss")
            plan = legacy(state, turn_context)
            _bump(state, "legacy_invocations")
            return plan
        _bump(state, "soft_cohort_hit")
        return _run_authoritative_policy(state, turn_context, legacy=legacy)

    if mode == "policy":
        if not cutover_enabled():
            # Defense in depth — mode() already gates this.
            plan = legacy(state, turn_context)
            _bump(state, "legacy_invocations")
            return plan
        return _run_authoritative_policy(state, turn_context, legacy=legacy)

    # Unknown effective mode → fail secure to legacy.
    plan = legacy(state, turn_context)
    _bump(state, "legacy_invocations")
    return plan
