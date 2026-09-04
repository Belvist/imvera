"""Spoken-reply resolver — orchestrator and harness share this path."""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional, TYPE_CHECKING

from conversation_system.agenda.topics import GOOD_PROBE_SUBTOPICS, TOPIC_KEYS
from conversation_system.ledger.action_supervisor import sanitize_delivery_claim
from conversation_system.reply import guards
from conversation_system.variety.dedupe import DedupeGuard, same_topic_question

if TYPE_CHECKING:
    from core.call_mirror import CallMirror


def _detect_good_slot(text: str) -> str:
    low = (text or "").lower()
    for slot in GOOD_PROBE_SUBTOPICS:
        keys = TOPIC_KEYS.get(slot, ())
        if any(k in low for k in keys):
            return slot
    return ""


def _slot_mismatch(required_slot: str, spoken: str) -> bool:
    if not required_slot or "?" not in spoken:
        return False
    detected = _detect_good_slot(spoken)
    return bool(detected and detected != required_slot)


def _deterministic_slot_fallback(required_slot: str, fallback: str) -> str:
    """Pool/script fallback when LLM question targets wrong slot."""
    labels = {
        "настроение": "Как настроение сегодня?",
        "сон": "Как спали ночью?",
        "планы": "Есть планы на день?",
    }
    return labels.get(required_slot, fallback)


def should_use_llm(
    plan: Optional[Dict[str, Any]],
    mirror: "CallMirror",
) -> bool:
    """True when plan explicitly opts into LLM streaming."""
    if not plan or plan.get("terminal") or plan.get("scripted"):
        return False
    if not plan.get("allow_llm"):
        return False
    if mirror.llm is None:
        return False
    if not (plan.get("text") or "").strip():
        return False
    if plan.get("intent") or plan.get("next_directive"):
        return True
    return plan.get("allow_llm", False)


def resolve_spoken_reply(
    mirror: "CallMirror",
    plan: Optional[Dict[str, Any]],
    llm_text: str = "",
    *,
    transcript: str = "",
    clean_llm=None,
    dedupe: DedupeGuard | None = None,
    regenerate_once: Callable[[str], str] | None = None,
) -> str:
    """Final string that reaches TTS."""
    if not plan:
        return ""
    fb = (plan.get("fallback") or "").strip()
    if plan.get("terminal") or plan.get("scripted"):
        return fb
    if not plan.get("allow_llm"):
        return fb
    raw = (llm_text or "").strip()
    if not raw:
        return fb
    cleaned = guards.sanitize_segment(
        raw,
        fallback=fb,
        transcript=transcript or (plan.get("text") or ""),
        llm_generated=True,
        clean_llm=clean_llm,
    )
    spoken = sanitize_delivery_claim((cleaned or fb).strip(), fallback=fb)
    agenda_ctx = plan.get("agenda_context") or {}
    required_slot = str(
        agenda_ctx.get("current_slot") or plan.get("current_slot") or ""
    ).strip()
    if _slot_mismatch(required_slot, spoken):
        retry = ""
        if regenerate_once is not None:
            try:
                retry = (regenerate_once(required_slot) or "").strip()
            except Exception:  # noqa: BLE001
                retry = ""
        if retry and not _slot_mismatch(required_slot, retry):
            spoken = sanitize_delivery_claim(
                guards.sanitize_segment(
                    retry,
                    fallback=fb,
                    transcript=transcript or (plan.get("text") or ""),
                    llm_generated=True,
                    clean_llm=clean_llm,
                ),
                fallback=fb,
            )
        else:
            spoken = _deterministic_slot_fallback(required_slot, fb) or fb or spoken
    if dedupe is not None:
        last_reply = getattr(mirror, "_last_reply", "") or ""
        last_question = ""
        history = getattr(mirror, "llm_history", []) or []
        for role, content in reversed(history):
            if role == "assistant" and "?" in (content or ""):
                last_question = content
                break
        topic = required_slot or str(plan.get("goal_kind") or "")
        spoken = dedupe.dedupe(
            spoken,
            last_reply=last_reply,
            last_question=last_question,
            topic=topic,
        )
        if required_slot and last_question and same_topic_question(
                spoken, last_question, required_slot):
            spoken = fb or spoken
    return spoken
