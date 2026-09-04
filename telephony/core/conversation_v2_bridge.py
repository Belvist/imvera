"""Orchestrator ↔ ConversationFacade — facade-only (legacy dialogue removed)."""
from __future__ import annotations

import logging
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple, TYPE_CHECKING

from conversation_system.domain.api import (
    SessionHandle,
    TurnPipelineError,
    TurnPlanV2,
)
from conversation_system.integration.facade import get_conversation_facade
from core.consent_call import plan_consent_turn, start_consent_call

if TYPE_CHECKING:
    from core.call_mirror import CallMirror
    from core.state import CallContext

_LOG = logging.getLogger(__name__)

_V2_KEY = "conversation_v2"


def _state(ctx: "CallContext") -> dict:
    st = ctx.dialogue_state.get(_V2_KEY)
    if not isinstance(st, dict):
        st = {}
        ctx.dialogue_state[_V2_KEY] = st
    return st


def get_v2_handle(ctx: "CallContext") -> Optional[SessionHandle]:
    handle = _state(ctx).get("handle")
    if isinstance(handle, SessionHandle):
        return handle
    return None


def get_v2_greeting(ctx: "CallContext") -> Optional[str]:
    g = _state(ctx).get("greeting")
    return g if isinstance(g, str) and g.strip() else None


def get_v2_last_plan(ctx: "CallContext") -> Optional[TurnPlanV2]:
    plan = _state(ctx).get("last_plan")
    return plan if isinstance(plan, TurnPlanV2) else None


def get_last_input_reason_for_call(ctx: "CallContext") -> str:
    """Why the last user turn was empty/rejected — for call_journal."""
    handle = get_v2_handle(ctx)
    if handle is None:
        return ""
    try:
        session = get_conversation_facade()._get_session(handle)  # noqa: SLF001
        return (session.memory.last_input_reason or "").strip()
    except Exception:
        return ""


def get_last_question_for_call(ctx: "CallContext") -> str:
    """Last question Vera asked — for mixed-audio rejection on the phone path."""
    handle = get_v2_handle(ctx)
    if handle is None:
        return ""
    try:
        session = get_conversation_facade()._get_session(handle)  # noqa: SLF001
        return (session.memory.last_question or "").strip()
    except Exception:
        return ""


def _store_v2_plan(ctx: "CallContext", plan: TurnPlanV2) -> None:
    _state(ctx)["last_plan"] = plan


def turn_plan_to_legacy(plan: TurnPlanV2) -> Dict[str, Any]:
    """Shim for orchestrator / reply_segments."""
    allow_llm = bool(plan.meta.get("allow_llm"))
    intent = (plan.meta.get("intent") or "").strip()
    current_slot = str(plan.meta.get("current_slot") or "")
    covered = plan.meta.get("covered_slots") or []
    forbidden = plan.meta.get("forbidden_slots") or []
    scripted = not allow_llm and bool((plan.spoken_reply or "").strip())
    return {
        "text": plan.user_text or "",
        "intent": intent if allow_llm else None,
        "fallback": plan.spoken_reply or "",
        "terminal": plan.terminal,
        "allow_llm": allow_llm,
        "scripted": scripted,
        "v2": True,
        "next_directive": plan.meta.get("next_directive") or "",
        "current_slot": current_slot,
        "goal_kind": plan.meta.get("goal_kind") or "",
        "agenda_context": {
            "current_slot": current_slot,
            "covered_slots": list(covered),
            "forbidden_slots": list(forbidden),
        },
    }


def begin_v2_call(
    ctx: "CallContext",
    *,
    caller_id: str = "",
    family_questions: Sequence[Mapping[str, str]] | None = None,
    elder_context: Mapping[str, str] | None = None,
    mode: str = "check_in",
) -> str:
    """Open facade session; greeting is played by Lua before the first turn."""
    facade = get_conversation_facade()
    handle, greeting = facade.begin_call(
        call_id=ctx.call_id,
        caller_id=caller_id or "",
        elder_context=elder_context,
        mode=mode,
        family_questions=family_questions,
        greeting_played=True,
    )
    st = _state(ctx)
    st["handle"] = handle
    st["greeting"] = greeting
    st["enabled"] = True
    ctx.agent._call_greeting = greeting
    ctx.agent._last_reply = greeting
    return greeting


def plan_turn_for_call(
    ctx: "CallContext",
    mirror: "CallMirror",
    *,
    transcript: str = "",
    reason: str | None = None,
    stt_confidence: float | None = None,
) -> Tuple[Dict[str, Any], bool]:
    """Return (legacy_plan_dict, spoke_via_facade)."""
    if getattr(mirror, "_consent_call", False) and not mirror.done:
        plan = plan_consent_turn(mirror, transcript, reason=reason)
        if plan.get("fallback"):
            mirror._last_reply = plan["fallback"]
        return plan, False

    handle = get_v2_handle(ctx)
    if handle is None:
        raise TurnPipelineError(f"no facade session for {ctx.call_id}")

    facade = get_conversation_facade()
    try:
        _ensure_observer_llm(handle, mirror.llm)
        v2_plan = facade.plan_turn(
            handle,
            transcript=transcript,
            reason=reason,
            stt_confidence=stt_confidence,
        )
    except (TurnPipelineError, Exception) as exc:
        _LOG.warning(
            "conversation_system plan_turn failed call_id=%s: %s",
            ctx.call_id,
            exc,
            exc_info=True,
        )
        raise TurnPipelineError(
            f"facade plan failed for {ctx.call_id}"
        ) from exc

    v2_legacy = turn_plan_to_legacy(v2_plan)
    _store_v2_plan(ctx, v2_plan)
    _apply_mirror_from_plan(mirror, v2_plan)
    return v2_legacy, True


def commit_turn_for_call(
    ctx: "CallContext",
    mirror: "CallMirror",
    plan: Dict[str, Any],
    spoken_text: str,
    *,
    spoke_via_v2: bool,
) -> None:
    """Persist turn state in facade + mirror."""
    reply = (spoken_text or "").strip()
    if not reply:
        return

    if spoke_via_v2 and plan.get("v2"):
        handle = get_v2_handle(ctx)
        v2_plan = get_v2_last_plan(ctx)
        if handle is not None and v2_plan is not None:
            facade = get_conversation_facade()
            facade.commit_turn(handle, v2_plan, reply)
            user_text = (v2_plan.user_text or plan.get("text") or "").strip()
            if user_text:
                mirror.record_user(user_text)
            _apply_mirror_from_plan(mirror, v2_plan, spoken=reply)
            mirror.commit_reply(reply)
            return

    user_text = (plan.get("text") or "").strip()
    if user_text:
        mirror.record_user(user_text)
    mirror.commit_reply(reply)


def mark_segment_played_for_call(
    ctx: "CallContext",
    *,
    generation_id: int,
    segment_id: str = "",
    slot: str = "",
) -> None:
    handle = get_v2_handle(ctx)
    if handle is None:
        return
    get_conversation_facade().mark_segment_played(
        handle,
        generation_id=generation_id,
        segment_id=segment_id,
        slot=slot,
    )


def on_generation_cancelled_for_call(
    ctx: "CallContext",
    *,
    generation_id: int,
) -> None:
    handle = get_v2_handle(ctx)
    if handle is None:
        return
    get_conversation_facade().on_generation_cancelled(
        handle,
        generation_id=generation_id,
    )


def end_v2_call(ctx: "CallContext") -> Optional[dict]:
    """Finalize facade session; return outcome dict or None."""
    handle = get_v2_handle(ctx)
    if handle is None:
        return None
    facade = get_conversation_facade()
    summary = facade.end_call(handle)
    st = _state(ctx)
    st.pop("handle", None)
    st["finished"] = True
    verdict = _map_verdict(summary.verdict)
    return {
        "status": verdict,
        "notes": list(summary.notes),
        "family_questions": list(summary.family_questions),
        "duration_turns": summary.duration_turns,
        "consent_outcome": summary.consent_outcome,
    }


def v2_dialogue_step(ctx: "CallContext", mirror: "CallMirror") -> int:
    plan = get_v2_last_plan(ctx)
    if plan is not None:
        return plan.dialogue_step
    return mirror.step


def start_consent_for_call(mirror: "CallMirror") -> str:
    """Consent path when PG says no active consent."""
    return start_consent_call(mirror)


def _ensure_observer_llm(handle: SessionHandle, llm) -> None:
    """Wire orchestrator LLM into session observer when available."""
    if llm is None:
        return
    facade = get_conversation_facade()
    try:
        session = facade._get_session(handle)  # noqa: SLF001 — bridge wiring
    except Exception:
        return
    observer = getattr(session, "observer", None)
    if observer is not None and hasattr(observer, "set_llm"):
        observer.set_llm(llm)


def _map_verdict(verdict: str) -> str:
    v = (verdict or "ok").strip().lower()
    if v in ("alert", "attention", "ok", "unknown", "declined", "no_contact"):
        return v
    if v in ("red", "confirmed_red"):
        return "alert"
    if v in ("yellow", "possible_red"):
        return "attention"
    return "ok"


def _apply_mirror_from_plan(
    mirror: "CallMirror",
    plan: TurnPlanV2,
    *,
    spoken: str | None = None,
) -> None:
    if spoken:
        mirror._last_reply = spoken
    elif plan.spoken_reply:
        mirror._last_reply = plan.spoken_reply
    if plan.terminal:
        mirror.done = True
    status = _map_verdict(plan.verdict)
    mirror.status = status
    for note in plan.record_notes:
        n = (note or "").strip()
        if n and n not in mirror.notes:
            mirror.notes.append(n)
