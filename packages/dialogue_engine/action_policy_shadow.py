"""Production-safe ActionPolicy conversation_scheduler shadow (outside frozen v7).

Shadow never owns ResponsePlan / SpeakEffect / TTS. Fail-open always.
Scope: conversation_scheduler only — not outer safety/control/repair/timer guards.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any

from packages.dialogue_engine.action_policy.actions import PolicyConstraintViolation
from packages.dialogue_engine.action_policy.bridge import legacy_plan_to_action_key
from packages.dialogue_engine.action_policy.mandatory import compute_mandatory_class
from packages.dialogue_engine.action_policy.policy import choose
from packages.dialogue_engine.action_policy.snapshot import (
    PolicySnapshot,
    TurnContextView,
    build_policy_snapshot,
)
from packages.dialogue_engine.action_policy_shadow_buffer import (
    buffer_shadow_record,
    drain_shadow_records,
    mark_shadow_persisted,
    requeue_shadow_records,
    shadow_health_counters,
)
from packages.dialogue_engine.action_policy_shadow_config import (
    DECISION_SCOPE,
    FROZEN_POLICY_SHA,
    POLICY_VERSION,
    SHADOW_SCHEMA_VERSION,
    action_policy_mode,
    action_policy_runtime_truth,
    make_error_record,
)
from packages.dialogue_engine.response_plan import ResponsePlan
from packages.dialogue_engine.runtime import git_sha_short

_LOG = logging.getLogger("dialogue.action_policy_shadow")

# Re-export for evaluator tests; session/engine must use buffer module directly.
__all__ = [
    "FROZEN_POLICY_SHA",
    "POLICY_VERSION",
    "SHADOW_SCHEMA_VERSION",
    "action_policy_mode",
    "action_policy_runtime_truth",
    "buffer_shadow_record",
    "classify_divergence",
    "drain_shadow_records",
    "finalize_shadow_record",
    "make_error_record",
    "mark_shadow_persisted",
    "requeue_shadow_records",
    "run_shadow_pre_legacy",
    "shadow_health_counters",
    "snapshot_fingerprint_sha256",
]


def _burden_bucket(burden: float) -> str:
    if burden < 0.25:
        return "low"
    if burden < 0.55:
        return "medium"
    if burden < 0.8:
        return "high"
    return "very_high"


def _structural_fingerprint_payload(snapshot: PolicySnapshot) -> dict[str, Any]:
    """Normalized structural state only — no free-text / medical attribute values."""
    episodes = []
    for ep in snapshot.episodes:
        episodes.append(
            {
                "episode_id": ep.episode_id,
                "kind": ep.kind,
                "status": ep.status,
                "speaker_owned": bool(ep.speaker_owned),
                "temporal_known": bool(ep.temporal_known),
                "current_known": bool(ep.current_known),
                "severity_known": bool(ep.severity_known),
                "functional_impact_known": bool(ep.functional_impact_known),
                "known_dimension_count": int(ep.known_dimension_count),
                "interrogation_eligible": bool(ep.interrogation_eligible),
            }
        )
    return {
        "turn_number": int(snapshot.turn_number),
        "episodes": episodes,
        "active_episode_id": snapshot.active_episode_id,
        "pending_episode_ids": list(snapshot.pending_episode_ids),
        "pending_episode_attribute": snapshot.pending_episode_attribute,
        "risk_level": snapshot.risk_level,
        "important_to_share_asked": bool(snapshot.important_to_share_asked),
        "important_to_share_resolved": bool(snapshot.important_to_share_resolved),
        "background_goal_status": list(snapshot.background_goal_status),
        "required_background_goals": list(snapshot.required_background_goals),
        "mandatory_background_goals": bool(snapshot.mandatory_background_goals),
        "wellness_entry_covered": bool(snapshot.wellness_entry_covered),
        "probe_phase": snapshot.probe_phase,
        "suspended_kind": snapshot.suspended_kind,
        "last_question_need": snapshot.last_question_need,
        "last_delivered_question_need": snapshot.last_delivered_question_need
        or snapshot.last_question_need,
        "questions_asked_this_episode": int(snapshot.questions_asked_this_episode),
        "user_burden_bucket": _burden_bucket(float(snapshot.user_burden)),
        "call_closed": bool(snapshot.call_closed),
        "fsm_state": snapshot.fsm_state,
    }


def snapshot_fingerprint_sha256(snapshot: PolicySnapshot) -> str:
    payload = _structural_fingerprint_payload(snapshot)
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _action_kind(label: str) -> str:
    return label.split(":", 1)[0]


def classify_divergence(
    *,
    shadow_label: str | None,
    legacy_label: str,
    agree: bool,
    pending_discard: bool = False,
) -> str:
    """Non-overlapping pair classifier — every listed class is reachable."""
    if agree:
        return "agree"
    if pending_discard:
        return "critical_pending_difference"
    if not shadow_label:
        return "unclassified"

    sk = _action_kind(shadow_label)
    lk = _action_kind(legacy_label)

    if sk == "SAFETY" or lk == "SAFETY":
        return "critical_safety_difference"
    if sk in {"CONTROL", "GOODBYE_FINAL"} or lk in {"CONTROL", "GOODBYE_FINAL"}:
        return "critical_control_difference"
    if sk == "REPAIR" or lk == "REPAIR":
        return "critical_repair_difference"

    # ITS ↔ ASK = transition timing (not optional-ask classes).
    if sk == "IMPORTANT_TO_SHARE" and lk == "ASK_EPISODE":
        return "shadow_transitions_earlier"
    if sk == "ASK_EPISODE" and lk == "IMPORTANT_TO_SHARE":
        return "shadow_transitions_later"

    # SUMMARY close timing.
    if sk == "SUMMARY_CLOSE" and lk != "SUMMARY_CLOSE":
        return "shadow_closes_earlier"
    if lk == "SUMMARY_CLOSE" and sk != "SUMMARY_CLOSE":
        return "shadow_closes_later"

    # Optional ask continuum (ACK only — ITS/SUMMARY handled above).
    if sk == "ASK_EPISODE" and lk == "ACK_ONLY":
        return "shadow_asks_optional"
    if sk == "ACK_ONLY" and lk == "ASK_EPISODE":
        return "shadow_skips_optional"

    if sk == "BACKGROUND_GOAL" or lk == "BACKGROUND_GOAL":
        return "background_goal_difference"
    if sk == "ASK_EPISODE" and lk == "ASK_EPISODE":
        return "episode_need_difference"
    if lk == "ACK_ONLY" or sk == "ACK_ONLY":
        return "legacy_ack_vs_shadow_action"
    return "unclassified"


def _critical_pending_discard(
    shadow_label: str | None,
    ctx: TurnContextView,
    snapshot: PolicySnapshot,
) -> bool:
    if not snapshot.outstanding_pending_obligation():
        return False
    if ctx.urgent_risk or ctx.explicit_farewell or ctx.repair or ctx.user_question:
        return False
    if ctx.control not in {"", "none"}:
        return False
    from packages.dialogue_engine.action_policy.needs import normalize_attribute

    pending = normalize_attribute(snapshot.pending_episode_attribute)
    if pending and shadow_label == f"ASK_EPISODE:{pending}":
        return False
    return True


def evaluate_critical_violation(
    *,
    shadow_label: str | None,
    ctx: TurnContextView,
    snapshot: PolicySnapshot,
    shadow_status: str,
    constraint_violation: bool,
    error_flags: list[str] | None = None,
) -> tuple[bool, list[str]]:
    flags: list[str] = list(error_flags or [])
    if shadow_status == "error" and not flags:
        flags.append("shadow_choose_error")
    if constraint_violation and "policy_constraint_violation" not in flags:
        flags.append("policy_constraint_violation")
    if ctx.urgent_risk and shadow_label != "SAFETY":
        flags.append("critical_safety_miss")
    if ctx.explicit_farewell and shadow_label not in {
        "GOODBYE_FINAL",
        "CONTROL:stop_call",
    }:
        flags.append("critical_control_miss")
    if ctx.control not in {"", "none", "stop_call"} and not (
        shadow_label and shadow_label.startswith("CONTROL:")
    ):
        flags.append("critical_control_miss")
    if ctx.repair and shadow_label != "REPAIR":
        if not ctx.urgent_risk and not ctx.explicit_farewell:
            flags.append("critical_repair_miss")
    if _critical_pending_discard(shadow_label, ctx, snapshot):
        flags.append("critical_pending_discard")
    return bool(flags), flags


def _askable_need_count(snapshot: PolicySnapshot) -> int:
    try:
        from packages.dialogue_engine.action_policy.need_value import currently_askable_needs

        return len(currently_askable_needs(snapshot))
    except Exception:
        return 0


def turn_context_view_from_scheduler(
    turn_context: Any,
) -> tuple[TurnContextView, str, str]:
    """Return (view, input_kind, decision_origin)."""
    turn = getattr(turn_context, "turn", None)
    if turn is not None:
        return TurnContextView.from_turn(turn), "rich", "rich_user_turn"

    user_text = str(getattr(turn_context, "user_text", "") or "")
    clarify = bool(getattr(turn_context, "clarify", False))
    filled = tuple(getattr(turn_context, "newly_filled_slots", ()) or ())
    if user_text or filled or clarify or getattr(turn_context, "answer_slot", None):
        view = TurnContextView(
            raw_text=user_text,
            needs_clarification=clarify,
            clarify_target="concern" if clarify else None,
            unresolved_concern=clarify,
        )
        return view, "semantic_projection", "semantic_projection"
    return TurnContextView(), "timer_or_internal", "internal_scheduler"


def _next_decision_ordinal(state: Any) -> int:
    current = int(getattr(state, "action_policy_shadow_decision_ordinal", 0) or 0) + 1
    try:
        state.action_policy_shadow_decision_ordinal = current
    except Exception:
        pass
    return current


def allocate_decision_id(state: Any, turn_context: Any) -> tuple[str, str, int]:
    """Stable decision_id even if processing_turn_id was cleared before schedule."""
    turn = getattr(turn_context, "turn", None)
    utterance_id = ""
    if turn is not None:
        utterance_id = str(getattr(turn, "utterance_id", "") or "")
    if not utterance_id:
        utterance_id = str(getattr(state, "processing_turn_id", "") or "")
    call_id = str(getattr(state, "call_id", "") or "")
    turn_seq = int(getattr(state, "turn_seq", 0) or 0)
    revision = int(getattr(state, "revision", 0) or 0)
    ordinal = _next_decision_ordinal(state)
    if utterance_id:
        decision_id = f"{call_id}:utt:{utterance_id}:d{ordinal}:r{revision}"
    else:
        decision_id = f"{call_id}:sched:t{turn_seq}:d{ordinal}:r{revision}"
    return decision_id, utterance_id, revision


def _ok_base_record(
    *,
    state: Any,
    input_kind: str,
    decision_origin: str,
    decision_id: str,
    utterance_id: str,
    revision: int,
    snapshot: PolicySnapshot,
    ctx: TurnContextView,
) -> dict[str, Any]:
    turn_seq = int(getattr(state, "turn_seq", 0) or 0)
    call_id = str(getattr(state, "call_id", "") or "")
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
        "shadow_action": None,
        "legacy_action": None,
        "agree": None,
        "mandatory_class": None,
        "divergence_class": None,
        "shadow_total_latency_ms": None,
        "policy_choose_latency_ms": None,
        "shadow_latency_ms": None,
        "policy_influenced_output": False,
        "pending_before": {
            "episode_id": snapshot.active_episode_id,
            "need": snapshot.pending_episode_attribute,
        },
        "critical_flags": {
            "urgent": bool(ctx.urgent_risk),
            "control": bool(ctx.control not in {"", "none"}),
            "repair": bool(ctx.repair),
            "user_question": bool(ctx.user_question),
            "pending_obligation": bool(snapshot.outstanding_pending_obligation()),
            "new_speaker_issue": bool(ctx.has_new_speaker_issue),
        },
        "snapshot_summary": {
            "episode_count": len(snapshot.episodes),
            "active_episode": snapshot.active_episode_id,
            "pending_episode_count": len(snapshot.pending_episode_ids),
            "askable_need_count": _askable_need_count(snapshot),
            "user_burden_bucket": _burden_bucket(snapshot.user_burden),
            "its_pending": snapshot.its_pending,
            "its_resolved": snapshot.important_to_share_resolved,
            "wellness_entry_covered": snapshot.wellness_entry_covered,
        },
        "chosen_score": None,
        "chosen_contributions": None,
        "candidate_count": None,
        "rejection_rule_ids": None,
        "error_stage": "",
        "error_type": "",
        "critical_violation": False,
        "critical_violation_flags": [],
        "snapshot_fingerprint_sha256": snapshot_fingerprint_sha256(snapshot),
        "idempotency_key": f"{call_id}:ACTION_POLICY_SHADOW:{decision_id}",
    }
    return record


def run_shadow_pre_legacy(state: Any, turn_context: Any) -> dict[str, Any]:
    """Pre-legacy evaluation. Must not mutate EngineState decision semantics."""
    total_started = time.perf_counter()
    decision_id, utterance_id, revision = allocate_decision_id(state, turn_context)
    input_kind = "timer_or_internal"
    decision_origin = "internal_scheduler"
    ctx: TurnContextView | None = None
    snapshot: PolicySnapshot | None = None

    try:
        ctx, input_kind, decision_origin = turn_context_view_from_scheduler(turn_context)
    except Exception as exc:
        rec = make_error_record(
            state,
            error_stage="turn_context_view",
            error_type=type(exc).__name__,
            input_kind=input_kind,
            decision_origin=decision_origin,
            decision_id=decision_id,
            utterance_id=utterance_id,
            engine_revision_before_legacy=revision,
        )
        rec["shadow_total_latency_ms"] = round(
            (time.perf_counter() - total_started) * 1000.0, 4
        )
        rec["shadow_latency_ms"] = rec["shadow_total_latency_ms"]
        return rec

    try:
        snapshot = build_policy_snapshot(state)
    except Exception as exc:
        rec = make_error_record(
            state,
            error_stage="build_policy_snapshot",
            error_type=type(exc).__name__,
            input_kind=input_kind,
            decision_origin=decision_origin,
            decision_id=decision_id,
            utterance_id=utterance_id,
            engine_revision_before_legacy=revision,
        )
        rec["shadow_total_latency_ms"] = round(
            (time.perf_counter() - total_started) * 1000.0, 4
        )
        rec["shadow_latency_ms"] = rec["shadow_total_latency_ms"]
        return rec

    assert ctx is not None and snapshot is not None
    record = _ok_base_record(
        state=state,
        input_kind=input_kind,
        decision_origin=decision_origin,
        decision_id=decision_id,
        utterance_id=utterance_id,
        revision=revision,
        snapshot=snapshot,
        ctx=ctx,
    )

    try:
        choose_started = time.perf_counter()
        decision = choose(snapshot, ctx)
        choose_ms = (time.perf_counter() - choose_started) * 1000.0
        shadow_label = decision.chosen.key.label()
        record["shadow_action"] = shadow_label
        record["policy_choose_latency_ms"] = round(choose_ms, 4)
        record["mandatory_class"] = compute_mandatory_class(snapshot, ctx).value
        if decision.candidates:
            record["chosen_score"] = float(decision.candidates[0].score)
            record["chosen_contributions"] = {
                str(k): float(v)
                for k, v in (decision.candidates[0].contributions or {}).items()
            }
        record["candidate_count"] = len(decision.candidates)
        record["rejection_rule_ids"] = sorted(
            {r.rule_id for r in decision.rejected if r.rule_id}
        )
        critical, flags = evaluate_critical_violation(
            shadow_label=shadow_label,
            ctx=ctx,
            snapshot=snapshot,
            shadow_status="ok",
            constraint_violation=False,
        )
        record["critical_violation"] = critical
        record["critical_violation_flags"] = flags
        if critical:
            record["cutover_eligible"] = False
        record["_shadow_ctx"] = ctx
        record["_shadow_snapshot"] = snapshot
        # Stamp total only when the pre-legacy record is fully formed.
        total_ms = (time.perf_counter() - total_started) * 1000.0
        record["shadow_total_latency_ms"] = round(total_ms, 4)
        record["shadow_latency_ms"] = record["shadow_total_latency_ms"]
        return record
    except PolicyConstraintViolation as exc:
        total_ms = (time.perf_counter() - total_started) * 1000.0
        rec = make_error_record(
            state,
            error_stage="policy_constraint",
            error_type="PolicyConstraintViolation",
            input_kind=input_kind,
            decision_origin=decision_origin,
            decision_id=decision_id,
            utterance_id=utterance_id,
            engine_revision_before_legacy=revision,
        )
        rec["shadow_total_latency_ms"] = round(total_ms, 4)
        rec["shadow_latency_ms"] = rec["shadow_total_latency_ms"]
        rec["mandatory_class"] = getattr(exc, "mandatory_class", None)
        rec["rejection_rule_ids"] = sorted(
            {
                r.rule_id
                for r in getattr(exc, "rejected", ())
                if getattr(r, "rule_id", None)
            }
        )
        rec["_shadow_ctx"] = ctx
        rec["_shadow_snapshot"] = snapshot
        return rec
    except Exception as exc:
        total_ms = (time.perf_counter() - total_started) * 1000.0
        rec = make_error_record(
            state,
            error_stage="choose",
            error_type=type(exc).__name__,
            input_kind=input_kind,
            decision_origin=decision_origin,
            decision_id=decision_id,
            utterance_id=utterance_id,
            engine_revision_before_legacy=revision,
        )
        rec["shadow_total_latency_ms"] = round(total_ms, 4)
        rec["shadow_latency_ms"] = rec["shadow_total_latency_ms"]
        rec["_shadow_ctx"] = ctx
        rec["_shadow_snapshot"] = snapshot
        return rec


def finalize_shadow_record(
    record: dict[str, Any],
    legacy_plan: ResponsePlan,
) -> dict[str, Any]:
    """Attach legacy comparison. Strips private keys."""
    legacy_label = legacy_plan_to_action_key(legacy_plan).label()
    record["legacy_action"] = legacy_label
    record["policy_influenced_output"] = False
    shadow_label = record.get("shadow_action")
    pending_discard = False
    ctx = record.get("_shadow_ctx")
    snapshot = record.get("_shadow_snapshot")
    if (
        record.get("shadow_status") == "ok"
        and shadow_label
        and ctx is not None
        and snapshot is not None
    ):
        pending_discard = _critical_pending_discard(shadow_label, ctx, snapshot)
        agree = shadow_label == legacy_label
        record["agree"] = agree
        record["divergence_class"] = classify_divergence(
            shadow_label=shadow_label,
            legacy_label=legacy_label,
            agree=agree,
            pending_discard=pending_discard,
        )
        if pending_discard:
            record["critical_violation"] = True
            flags = list(record.get("critical_violation_flags") or [])
            if "critical_pending_discard" not in flags:
                flags.append("critical_pending_discard")
            record["critical_violation_flags"] = flags
            record["cutover_eligible"] = False
        elif record.get("critical_violation"):
            record["cutover_eligible"] = False
        elif record.get("divergence_class") == "unclassified":
            record["cutover_eligible"] = False
        else:
            record["cutover_eligible"] = True
    else:
        record["agree"] = False
        if not record.get("divergence_class"):
            record["divergence_class"] = "unclassified"
        record["cutover_eligible"] = False
        if record.get("shadow_status") == "error":
            record["critical_violation"] = True

    if record.get("divergence_class") == "unclassified":
        record["cutover_eligible"] = False

    record.pop("_shadow_ctx", None)
    record.pop("_shadow_snapshot", None)
    for forbidden in (
        "raw_text",
        "transcript",
        "source_quote",
        "mandatory_question",
        "spoken_text",
        "user_text",
    ):
        record.pop(forbidden, None)
    return record
