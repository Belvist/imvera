"""Production-safe ActionPolicy shadow evaluation (outside frozen v7 package).

Shadow never owns ResponsePlan / SpeakEffect / TTS. Fail-open always.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import asdict, is_dataclass
from typing import Any

from packages.dialogue_engine.action_policy.actions import (
    PolicyConstraintViolation,
)
from packages.dialogue_engine.action_policy.bridge import legacy_plan_to_action_key
from packages.dialogue_engine.action_policy.mandatory import compute_mandatory_class
from packages.dialogue_engine.action_policy.policy import choose
from packages.dialogue_engine.action_policy.scorer import POLICY_VERSION
from packages.dialogue_engine.action_policy.snapshot import (
    PolicySnapshot,
    TurnContextView,
    build_policy_snapshot,
)
from packages.dialogue_engine.response_plan import ResponsePlan
from packages.dialogue_engine.runtime import git_sha_short

_LOG = logging.getLogger("dialogue.action_policy_shadow")

FROZEN_POLICY_SHA = "61e17934f7be3b10ca5df9b2581cb0a8b853c1fe"
SHADOW_SCHEMA_VERSION = 1

# Modes — soft/hard intentionally unavailable in M1.
_ALLOWED_MODES = frozenset({"off", "shadow"})


def action_policy_mode() -> str:
    raw = os.environ.get("IMVERA_ACTION_POLICY_MODE", "off").strip().lower()
    if raw in _ALLOWED_MODES:
        return raw
    return "off"


def action_policy_runtime_truth() -> dict[str, Any]:
    mode = action_policy_mode()
    return {
        "action_policy.mode": mode,
        "action_policy.policy_version": POLICY_VERSION,
        "action_policy.frozen_policy_sha": FROZEN_POLICY_SHA,
        "IMVERA_ACTION_POLICY_MODE": os.environ.get("IMVERA_ACTION_POLICY_MODE", "off"),
    }


def _burden_bucket(burden: float) -> str:
    if burden < 0.25:
        return "low"
    if burden < 0.55:
        return "medium"
    if burden < 0.8:
        return "high"
    return "very_high"


def _safe_jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _safe_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe_jsonable(v) for v in value]
    if is_dataclass(value):
        return _safe_jsonable(asdict(value))
    return str(value)


def snapshot_fingerprint_sha256(snapshot: PolicySnapshot) -> str:
    payload = _safe_jsonable(asdict(snapshot))
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def turn_context_view_from_scheduler(
    turn_context: Any,
) -> tuple[TurnContextView, str]:
    """Build TurnContextView + input_kind without pretending non-rich equals rich."""
    turn = getattr(turn_context, "turn", None)
    if turn is not None:
        return TurnContextView.from_turn(turn), "rich"

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
        return view, "semantic_projection"
    return TurnContextView(), "timer_or_internal"


def _askable_need_count(snapshot: PolicySnapshot) -> int:
    try:
        from packages.dialogue_engine.action_policy.need_value import currently_askable_needs

        return len(currently_askable_needs(snapshot))
    except Exception:
        return 0


def classify_divergence(
    *,
    shadow_label: str | None,
    legacy_label: str,
    agree: bool,
) -> str:
    if agree:
        return "agree"
    if not shadow_label:
        return "unclassified"
    s = shadow_label
    legacy = legacy_label

    def _kind(label: str) -> str:
        return label.split(":", 1)[0]

    sk, lk = _kind(s), _kind(legacy)
    if sk == "SAFETY" or lk == "SAFETY":
        return "critical_safety_difference"
    if sk in {"CONTROL", "GOODBYE_FINAL"} or lk in {"CONTROL", "GOODBYE_FINAL"}:
        return "critical_control_difference"
    if sk == "REPAIR" or lk == "REPAIR":
        return "critical_repair_difference"
    if sk == "ASK_EPISODE" and lk in {"IMPORTANT_TO_SHARE", "SUMMARY_CLOSE", "ACK_ONLY"}:
        return "shadow_asks_optional"
    if lk == "ASK_EPISODE" and sk in {"IMPORTANT_TO_SHARE", "SUMMARY_CLOSE", "ACK_ONLY"}:
        return "shadow_skips_optional"
    if sk == "IMPORTANT_TO_SHARE" and lk == "ASK_EPISODE":
        return "shadow_transitions_earlier"
    if lk == "IMPORTANT_TO_SHARE" and sk == "ASK_EPISODE":
        return "shadow_transitions_later"
    if sk == "SUMMARY_CLOSE" and lk != "SUMMARY_CLOSE":
        return "shadow_closes_earlier"
    if lk == "SUMMARY_CLOSE" and sk != "SUMMARY_CLOSE":
        return "shadow_closes_later"
    if sk == "BACKGROUND_GOAL" or lk == "BACKGROUND_GOAL":
        return "background_goal_difference"
    if sk == "ASK_EPISODE" and lk == "ASK_EPISODE":
        return "episode_need_difference"
    if lk == "ACK_ONLY" and sk != "ACK_ONLY":
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
    # Any other action (including ASK of a different need) silently loses pending.
    return True


def evaluate_critical_violation(
    *,
    shadow_label: str | None,
    ctx: TurnContextView,
    snapshot: PolicySnapshot,
    shadow_status: str,
    constraint_violation: bool,
) -> tuple[bool, list[str]]:
    flags: list[str] = []
    if shadow_status == "error":
        flags.append("shadow_exception")
    if constraint_violation:
        flags.append("policy_constraint_violation")
    if ctx.urgent_risk and shadow_label != "SAFETY":
        flags.append("critical_safety_miss")
    if ctx.explicit_farewell and shadow_label not in {"GOODBYE_FINAL", "CONTROL:stop_call"}:
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


def _base_record(
    *,
    state: Any,
    input_kind: str,
    snapshot: PolicySnapshot | None,
    ctx: TurnContextView | None,
    shadow_status: str,
    error_stage: str = "",
    error_type: str = "",
) -> dict[str, Any]:
    turn_id = int(getattr(state, "turn_seq", 0) or 0)
    utterance_id = str(getattr(state, "processing_turn_id", "") or "")
    call_id = str(getattr(state, "call_id", "") or "")
    revision = int(getattr(state, "revision", 0) or 0)
    pending_need = None
    pending_ep = None
    if snapshot is not None:
        pending_need = snapshot.pending_episode_attribute
        pending_ep = snapshot.active_episode_id
    record: dict[str, Any] = {
        "schema_version": SHADOW_SCHEMA_VERSION,
        "turn_id": turn_id,
        "utterance_id": utterance_id,
        "deployment_sha": git_sha_short(),
        "frozen_policy_sha": FROZEN_POLICY_SHA,
        "policy_version": POLICY_VERSION,
        "input_kind": input_kind,
        "shadow_status": shadow_status,
        "shadow_action": None,
        "legacy_action": None,
        "agree": None,
        "mandatory_class": None,
        "divergence_class": None,
        "shadow_latency_ms": None,
        "policy_influenced_output": False,
        "pending_before": {"episode_id": pending_ep, "need": pending_need},
        "critical_flags": {
            "urgent": bool(ctx.urgent_risk) if ctx else False,
            "control": bool(ctx and ctx.control not in {"", "none"}),
            "repair": bool(ctx.repair) if ctx else False,
            "user_question": bool(ctx.user_question) if ctx else False,
            "pending_obligation": bool(
                snapshot.outstanding_pending_obligation() if snapshot else False
            ),
            "new_speaker_issue": bool(ctx.has_new_speaker_issue) if ctx else False,
        },
        "snapshot_summary": None,
        "chosen_score": None,
        "chosen_contributions": None,
        "candidate_count": None,
        "rejection_rule_ids": None,
        "error_stage": error_stage,
        "error_type": error_type,
        "critical_violation": False,
        "critical_violation_flags": [],
        "snapshot_fingerprint_sha256": None,
        "idempotency_key": (
            f"{call_id}:ACTION_POLICY_SHADOW:{utterance_id or turn_id}:{revision}"
        ),
    }
    if snapshot is not None:
        record["snapshot_fingerprint_sha256"] = snapshot_fingerprint_sha256(snapshot)
        record["snapshot_summary"] = {
            "episode_count": len(snapshot.episodes),
            "active_episode": snapshot.active_episode_id,
            "pending_episode_count": len(snapshot.pending_episode_ids),
            "askable_need_count": _askable_need_count(snapshot),
            "user_burden_bucket": _burden_bucket(snapshot.user_burden),
            "its_pending": snapshot.its_pending,
            "its_resolved": snapshot.important_to_share_resolved,
            "wellness_entry_covered": snapshot.wellness_entry_covered,
        }
    return record


def run_shadow_pre_legacy(state: Any, turn_context: Any) -> dict[str, Any]:
    """Pre-legacy evaluation. Must not mutate EngineState. Failures become error records."""
    ctx: TurnContextView | None = None
    snapshot: PolicySnapshot | None = None
    input_kind = "timer_or_internal"
    started = time.perf_counter()
    try:
        ctx, input_kind = turn_context_view_from_scheduler(turn_context)
    except Exception as exc:
        return _base_record(
            state=state,
            input_kind=input_kind,
            snapshot=None,
            ctx=None,
            shadow_status="error",
            error_stage="turn_context_view",
            error_type=type(exc).__name__,
        )
    try:
        snapshot = build_policy_snapshot(state)
    except Exception as exc:
        return _base_record(
            state=state,
            input_kind=input_kind,
            snapshot=None,
            ctx=ctx,
            shadow_status="error",
            error_stage="build_policy_snapshot",
            error_type=type(exc).__name__,
        )

    record = _base_record(
        state=state,
        input_kind=input_kind,
        snapshot=snapshot,
        ctx=ctx,
        shadow_status="ok",
    )
    try:
        decision = choose(snapshot, ctx)
        latency_ms = (time.perf_counter() - started) * 1000.0
        shadow_label = decision.chosen.key.label()
        record["shadow_action"] = shadow_label
        record["shadow_latency_ms"] = round(latency_ms, 4)
        record["mandatory_class"] = compute_mandatory_class(snapshot, ctx).value
        if decision.candidates:
            record["chosen_score"] = float(decision.candidates[0].score)
            # Contributions only — no raw user text fields.
            record["chosen_contributions"] = {
                str(k): float(v)
                for k, v in (decision.candidates[0].contributions or {}).items()
            }
        else:
            record["chosen_score"] = None
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
        # Stash snapshot/ctx refs for finalize via private keys stripped before persist.
        record["_shadow_ctx"] = ctx
        record["_shadow_snapshot"] = snapshot
        return record
    except PolicyConstraintViolation as exc:
        latency_ms = (time.perf_counter() - started) * 1000.0
        record["shadow_status"] = "error"
        record["error_stage"] = "choose"
        record["error_type"] = "PolicyConstraintViolation"
        record["shadow_latency_ms"] = round(latency_ms, 4)
        record["mandatory_class"] = getattr(exc, "mandatory_class", None)
        record["rejection_rule_ids"] = sorted(
            {r.rule_id for r in getattr(exc, "rejected", ()) if getattr(r, "rule_id", None)}
        )
        critical, flags = evaluate_critical_violation(
            shadow_label=None,
            ctx=ctx,
            snapshot=snapshot,
            shadow_status="error",
            constraint_violation=True,
        )
        record["critical_violation"] = critical
        record["critical_violation_flags"] = flags
        record["_shadow_ctx"] = ctx
        record["_shadow_snapshot"] = snapshot
        return record
    except Exception as exc:
        latency_ms = (time.perf_counter() - started) * 1000.0
        record["shadow_status"] = "error"
        record["error_stage"] = "choose"
        record["error_type"] = type(exc).__name__
        record["shadow_latency_ms"] = round(latency_ms, 4)
        critical, flags = evaluate_critical_violation(
            shadow_label=None,
            ctx=ctx,
            snapshot=snapshot,
            shadow_status="error",
            constraint_violation=False,
        )
        record["critical_violation"] = critical
        record["critical_violation_flags"] = flags
        record["_shadow_ctx"] = ctx
        record["_shadow_snapshot"] = snapshot
        return record


def finalize_shadow_record(
    record: dict[str, Any],
    legacy_plan: ResponsePlan,
) -> dict[str, Any]:
    """Attach legacy comparison. Strips private keys. Never raises into caller if used carefully."""
    legacy_label = legacy_plan_to_action_key(legacy_plan).label()
    record["legacy_action"] = legacy_label
    record["policy_influenced_output"] = False
    shadow_label = record.get("shadow_action")
    if record.get("shadow_status") == "ok" and shadow_label:
        agree = shadow_label == legacy_label
        record["agree"] = agree
        record["divergence_class"] = classify_divergence(
            shadow_label=shadow_label,
            legacy_label=legacy_label,
            agree=agree,
        )
        if (
            record.get("critical_flags", {}).get("pending_obligation")
            and _critical_pending_discard(
                shadow_label,
                record.get("_shadow_ctx") or TurnContextView(),
                record.get("_shadow_snapshot")
                or PolicySnapshot(turn_number=0, wellness_entry_covered=True),
            )
        ):
            record["divergence_class"] = "critical_pending_difference"
            record["critical_violation"] = True
            flags = list(record.get("critical_violation_flags") or [])
            if "critical_pending_discard" not in flags:
                flags.append("critical_pending_discard")
            record["critical_violation_flags"] = flags
    else:
        record["agree"] = False
        record["divergence_class"] = "unclassified"

    # Strip private / forbidden fields before persistence.
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


def buffer_shadow_record(state: Any, record: dict[str, Any]) -> None:
    buf = getattr(state, "action_policy_shadow_records", None)
    if buf is None:
        return
    buf.append(record)


def drain_shadow_records(state: Any) -> list[dict[str, Any]]:
    buf = getattr(state, "action_policy_shadow_records", None)
    if not buf:
        return []
    out = list(buf)
    buf.clear()
    return out
