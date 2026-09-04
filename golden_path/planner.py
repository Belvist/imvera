"""Planner — sole authority for next conversational action."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from golden_path.analyzer import Analysis, AnalysisKind, AnswerType
from golden_path.safety import SafetyPhase, is_safety_resolving_text
from golden_path.slots import (
    SlotName,
    SlotStatus,
    SLOT_ORDER,
    may_ask_slot,
)
from golden_path.state import ConversationState


class PlannerAction(str, Enum):
    GREET = "GREET"
    ANSWER_USER = "ANSWER_USER"
    ACK_ONLY = "ACK_ONLY"
    ASK_SLOT = "ASK_SLOT"
    REPAIR = "REPAIR"
    HANDLE_CORRECTION = "HANDLE_CORRECTION"
    HANDLE_REFUSAL = "HANDLE_REFUSAL"
    HANDLE_FATIGUE = "HANDLE_FATIGUE"
    WAIT = "WAIT"
    SAFETY = "SAFETY"
    CLOSE = "CLOSE"


@dataclass(frozen=True)
class Plan:
    action: PlannerAction
    slot: SlotName | None = None
    answer_type: AnswerType | None = None
    reason: str = ""

    def action_name(self) -> str:
        if self.action == PlannerAction.ASK_SLOT and self.slot is not None:
            return f"ASK_SLOT({self.slot.value})"
        if self.action == PlannerAction.ANSWER_USER and self.answer_type is not None:
            return f"ANSWER_USER({self.answer_type.value})"
        return self.action.value

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action.value,
            "slot": self.slot.value if self.slot else None,
            "answer_type": self.answer_type.value if self.answer_type else None,
            "reason": self.reason,
            "action_name": self.action_name(),
        }


def _pick_next_slot(state: ConversationState) -> SlotName | None:
    for slot in SLOT_ORDER:
        if may_ask_slot(slot, state.slot_statuses):
            return slot
    return None


def _is_narrative_response(text: str) -> bool:
    words = (text or "").split()
    return len(words) >= 8


def _safety_holds(state: ConversationState) -> bool:
    return state.safety_phase in (SafetyPhase.ACTIVE, SafetyPhase.RESOLVING)


def plan_turn(state: ConversationState, analysis: Analysis) -> Plan:
    """Pure planner: state + analysis → next action."""
    if not state.greeted:
        return Plan(PlannerAction.GREET, reason="session_start")

    if analysis.kind == AnalysisKind.SAFETY or _safety_holds(state):
        if (
            state.safety_phase == SafetyPhase.RESOLVING
            and analysis.kind == AnalysisKind.NORMAL_RESPONSE
            and is_safety_resolving_text(state.last_user_text)
        ):
            return Plan(PlannerAction.SAFETY, reason="safety_resolving")
        if state.safety_phase == SafetyPhase.ACTIVE:
            return Plan(PlannerAction.SAFETY, reason="safety_active")
        if analysis.kind == AnalysisKind.SAFETY:
            return Plan(PlannerAction.SAFETY, reason="safety_signal")

    if analysis.kind == AnalysisKind.GOODBYE:
        return Plan(PlannerAction.CLOSE, reason="goodbye")

    if state.closing:
        return Plan(PlannerAction.CLOSE, reason="goodbye_confirmed")

    if analysis.kind == AnalysisKind.USER_FATIGUE:
        if any(w in state.last_user_text.lower() for w in ("закончим", "хватит", "пока")):
            return Plan(PlannerAction.CLOSE, reason="fatigue_close")
        return Plan(PlannerAction.HANDLE_FATIGUE, reason="user_fatigue")

    if analysis.kind == AnalysisKind.WAIT_REQUEST:
        return Plan(PlannerAction.WAIT, reason="wait_request")

    if analysis.kind == AnalysisKind.REPAIR:
        return Plan(PlannerAction.REPAIR, reason="repair_request")

    if analysis.kind == AnalysisKind.CORRECTION:
        return Plan(PlannerAction.HANDLE_CORRECTION, reason="user_correction")

    if analysis.kind == AnalysisKind.TOPIC_REFUSAL:
        slot = analysis.refusal_slot or state.pending_slot
        return Plan(PlannerAction.HANDLE_REFUSAL, slot=slot, reason="topic_refusal")

    if analysis.kind == AnalysisKind.DIRECT_USER_QUESTION:
        answer_type = analysis.answer_type or AnswerType.OTHER
        return Plan(
            PlannerAction.ANSWER_USER,
            answer_type=answer_type,
            reason="user_question",
        )

    if state.all_slots_closed():
        return Plan(PlannerAction.CLOSE, reason="all_slots_closed_wrap")

    answered_raw = analysis.facts.get("answered_slot")
    if answered_raw:
        try:
            slot_name = SlotName(answered_raw)
            if state.slot_statuses.get(slot_name) == SlotStatus.ANSWERED:
                nxt = _pick_next_slot(state)
                if nxt is not None:
                    return Plan(
                        PlannerAction.ASK_SLOT,
                        slot=nxt,
                        reason="slot_answered_advance",
                    )
        except ValueError:
            pass

    if state.pending_slot is not None:
        status = state.slot_statuses.get(state.pending_slot)
        if status == SlotStatus.OPEN:
            return Plan(
                PlannerAction.ASK_SLOT,
                slot=state.pending_slot,
                reason="pending_slot_open",
            )

    nxt = _pick_next_slot(state)
    if nxt is not None:
        return Plan(PlannerAction.ASK_SLOT, slot=nxt, reason="next_open_slot")

    if _is_narrative_response(state.last_user_text):
        return Plan(PlannerAction.ACK_ONLY, reason="narrative_ack")

    return Plan(PlannerAction.ACK_ONLY, reason="default_ack")


def blocked_slots(state: ConversationState) -> list[SlotName]:
    """Slots planner must never re-ask."""
    blocked: list[SlotName] = []
    for slot in SLOT_ORDER:
        status = state.slot_statuses.get(slot, SlotStatus.OPEN)
        if status in (SlotStatus.ANSWERED, SlotStatus.DECLINED):
            blocked.append(slot)
    return blocked


def plan_for_tests(state: ConversationState, analysis: Analysis) -> Plan:
    """Expose planner for unit tests."""
    return plan_turn(state, analysis)
