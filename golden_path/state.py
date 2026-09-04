"""Conversation state for Golden Path engine."""
from __future__ import annotations

import copy
import json
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from golden_path.safety import SafetyPhase, is_distress_followup, is_safety_resolving_text
from golden_path.semantics import detect_slot_answer, slot_from_text
from golden_path.slots import (
    SlotName,
    SlotStatus,
    SLOT_ORDER,
    default_slot_map,
    is_refusal,
)


@dataclass
class TurnRecord:
    """One dialogue turn."""

    role: str
    text: str

    def to_dict(self) -> dict[str, str]:
        return {"role": self.role, "text": self.text}


@dataclass
class ConversationState:
    """Mutable session state — single source of truth for planner."""

    session_id: str = ""
    facts: dict[str, str] = field(default_factory=dict)
    slot_statuses: dict[SlotName, SlotStatus] = field(default_factory=default_slot_map)
    declined_topics: set[str] = field(default_factory=set)
    pending_question: str | None = None
    pending_slot: SlotName | None = None
    current_topic: SlotName | None = None
    last_turns: deque[TurnRecord] = field(default_factory=lambda: deque(maxlen=10))
    user_questions: list[str] = field(default_factory=list)
    corrections: list[str] = field(default_factory=list)
    current_goal: str = "check_in"
    assistant_turn_count: int = 0
    turns_since_question: int = 0
    greeted: bool = False
    closing: bool = False
    safety_active: bool = False
    safety_phase: SafetyPhase = SafetyPhase.INACTIVE
    repair_pending: bool = False
    wait_request: bool = False
    user_fatigue: bool = False
    last_assistant_text: str = ""
    last_user_text: str = ""

    def compact_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "facts": dict(self.facts),
            "slot_statuses": {k.value: v.value for k, v in self.slot_statuses.items()},
            "declined_topics": sorted(self.declined_topics),
            "pending_question": self.pending_question,
            "pending_slot": self.pending_slot.value if self.pending_slot else None,
            "current_topic": self.current_topic.value if self.current_topic else None,
            "current_goal": self.current_goal,
            "assistant_turn_count": self.assistant_turn_count,
            "turns_since_question": self.turns_since_question,
            "greeted": self.greeted,
            "closing": self.closing,
            "safety_active": self.safety_active,
            "safety_phase": self.safety_phase.value,
            "repair_pending": self.repair_pending,
            "wait_request": self.wait_request,
            "user_fatigue": self.user_fatigue,
        }

    def compact_json(self) -> str:
        return json.dumps(self.compact_dict(), ensure_ascii=False, separators=(",", ":"))

    def clone(self) -> ConversationState:
        return copy.deepcopy(self)

    def record_turn(self, role: str, text: str) -> None:
        self.last_turns.append(TurnRecord(role=role, text=text.strip()))
        if role == "assistant":
            self.last_assistant_text = text.strip()
            self.assistant_turn_count += 1
        elif role == "user":
            self.last_user_text = text.strip()

    def mark_slot_answered(self, slot: SlotName) -> None:
        if self.slot_statuses.get(slot) == SlotStatus.OPEN:
            self.slot_statuses[slot] = SlotStatus.ANSWERED
            self.current_topic = slot
            if self.pending_slot == slot:
                self.pending_slot = None

    def mark_slot_declined(self, slot: SlotName) -> None:
        if self.slot_statuses.get(slot) == SlotStatus.OPEN:
            self.slot_statuses[slot] = SlotStatus.DECLINED
            self.declined_topics.add(slot.value)
            if self.pending_slot == slot:
                self.pending_slot = None

    def apply_analysis_facts(self, facts: dict[str, str]) -> None:
        for key, value in facts.items():
            if value:
                self.facts[key] = value

    def apply_user_message(self, text: str, analysis_kind: str, facts: dict[str, str]) -> None:
        """Update slots from user message after analyzer runs."""
        if not text.strip():
            return

        if analysis_kind == "TOPIC_REFUSAL":
            slot = self.pending_slot or slot_from_text(text) or self.current_topic
            if slot is not None:
                self.mark_slot_declined(slot)
            return

        if analysis_kind == "CORRECTION":
            return

        if is_refusal(text, self.pending_slot):
            if self.pending_slot is not None:
                self.mark_slot_declined(self.pending_slot)
            return

        answered_raw = facts.get("answered_slot")
        if answered_raw:
            try:
                self.mark_slot_answered(SlotName(answered_raw))
                return
            except ValueError:
                pass

        answered = detect_slot_answer(text, self.pending_slot)
        if answered is not None:
            self.mark_slot_answered(answered)

    def reduce_user_turn(
        self,
        text: str,
        analysis_kind: str,
        facts: dict[str, str],
        *,
        refusal_slot: SlotName | None = None,
    ) -> None:
        """Apply user analysis to state — must run before plan_turn()."""
        self.last_user_text = text.strip()

        if analysis_kind == "CORRECTION":
            self.corrections.append(text.strip())
            symptom = facts.get("symptom")
            if symptom:
                self.facts["symptom"] = symptom
        else:
            self.apply_analysis_facts(facts)

        if analysis_kind == "SAFETY":
            self.safety_phase = SafetyPhase.ACTIVE
            self.safety_active = True
        elif is_distress_followup(text) and self.safety_phase != SafetyPhase.INACTIVE:
            self.safety_phase = SafetyPhase.ACTIVE
            self.safety_active = True
        elif self.safety_phase == SafetyPhase.ACTIVE and analysis_kind == "NORMAL_RESPONSE":
            if is_safety_resolving_text(text):
                self.safety_phase = SafetyPhase.RESOLVING
        elif self.safety_phase == SafetyPhase.RESOLVING and analysis_kind == "NORMAL_RESPONSE":
            if is_safety_resolving_text(text) or not is_distress_followup(text):
                self.safety_phase = SafetyPhase.RESOLVED
                self.safety_active = False

        if analysis_kind == "REPAIR":
            self.repair_pending = True
        elif self.repair_pending and analysis_kind == "NORMAL_RESPONSE" and _is_repair_ack(text):
            self.repair_pending = False

        self.wait_request = analysis_kind == "WAIT_REQUEST"
        self.user_fatigue = analysis_kind == "USER_FATIGUE"

        if analysis_kind == "GOODBYE":
            self.closing = True

        if analysis_kind == "DIRECT_USER_QUESTION":
            self.user_questions.append(text.strip())

        if analysis_kind == "TOPIC_REFUSAL":
            slot = refusal_slot or self.pending_slot or slot_from_text(text) or self.current_topic
            if slot is not None:
                self.mark_slot_declined(slot)
            return

        skip_slot_apply = {
            "CORRECTION",
            "REPAIR",
            "DIRECT_USER_QUESTION",
            "WAIT_REQUEST",
            "USER_FATIGUE",
            "SAFETY",
            "GOODBYE",
        }
        if analysis_kind not in skip_slot_apply:
            self.apply_user_message(text, analysis_kind, facts)

    def all_slots_closed(self) -> bool:
        return all(
            self.slot_statuses.get(s) in (SlotStatus.ANSWERED, SlotStatus.DECLINED)
            for s in SLOT_ORDER
        )

    def question_budget_metric(self) -> int:
        """Style metric only — never blocks planner."""
        return self.turns_since_question

    def note_assistant_question(self, text: str) -> None:
        if "?" in text:
            self.pending_question = text.strip()
            self.turns_since_question = 0
        else:
            self.turns_since_question += 1


def _is_repair_ack(text: str) -> bool:
    low = (text or "").lower().strip()
    if not low:
        return False
    words = low.split()
    if len(words) > 5:
        return False
    ack_tokens = (
        "ага",
        "понял",
        "поняла",
        "ясно",
        "хорошо",
        "угу",
        "ладно",
        "спасибо",
    )
    return any(tok in low for tok in ack_tokens)
