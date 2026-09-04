"""Post-LLM validation and typed fallbacks."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from golden_path.analyzer import AnswerType
from golden_path.fallbacks import SAFETY_FALLBACK, typed_fallback
from golden_path.planner import PlannerAction
from golden_path.slots import (
    SlotName,
    SLOT_LABELS_RU,
    SLOT_ORDER,
    answered_slots,
    declined_slots,
)
from golden_path.spoken_quality import check_spoken_quality
from golden_path.state import ConversationState

BANNED_PHRASES: tuple[str, ...] = (
    "давайте дальше",
    "давайте перейдём",
    "давайте перейдем",
    "скажите сейчас",
    "я вызову",
    "я позвоню",
    "я отправлю",
    "вызову скорую",
    "позвоню врачу",
    "отправлю сообщение",
    "как дела",
    "что нового",
)

PROMISE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bя\s+(вызову|позвоню|отправлю|сообщу|передам)\b",
        r"\bсейчас\s+вызову\b",
        r"\bблизкие\s+увидят\b",
        r"\bя\s+всё\s+записала\b",
        r"\bпереда\w+\s+близк",
    )
)

MALE_SELF_FORMS: dict[str, str] = {
    "рад": "рада",
    "понял": "поняла",
    "услышал": "услышала",
    "записал": "записала",
    "передал": "передала",
    "позвонил": "позвонила",
    "устал": "устала",
}


@dataclass
class ValidatorResult:
    ok: bool
    text: str
    violations: list[str]
    used_fallback: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "text": self.text,
            "violations": list(self.violations),
            "used_fallback": self.used_fallback,
        }


def _count_questions(text: str) -> int:
    return text.count("?")


def _mentions_blocked_slot(text: str, blocked: list[SlotName]) -> list[str]:
    low = text.lower()
    hits: list[str] = []
    for slot in blocked:
        label = SLOT_LABELS_RU[slot]
        if label in low and "?" in text:
            hits.append(f"reask_{slot.value}")
    return hits


def _feminize(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        word = match.group(2)
        fixed = MALE_SELF_FORMS.get(word.lower())
        if fixed:
            return f"{match.group(1)} {fixed}"
        return match.group(0)

    return re.sub(r"\b(я)\s+(\w+)", repl, text, flags=re.IGNORECASE)


def validate_reply(
    text: str | None,
    action: PlannerAction,
    state: ConversationState,
    slot: SlotName | None = None,
    answer_type: AnswerType | None = None,
    *,
    apply_fallback: bool = True,
) -> ValidatorResult:
    violations: list[str] = []

    if action == PlannerAction.SAFETY:
        return ValidatorResult(ok=True, text=SAFETY_FALLBACK, violations=[], used_fallback=True)

    candidate = (text or "").strip()
    if not candidate:
        violations.append("empty_llm_output")
        if apply_fallback:
            fb = typed_fallback(action, state, slot=slot, answer_type=answer_type)
            return ValidatorResult(ok=False, text=fb, violations=violations, used_fallback=True)
        return ValidatorResult(ok=False, text="", violations=violations, used_fallback=False)

    low = candidate.lower()
    for phrase in BANNED_PHRASES:
        if phrase in low:
            violations.append(f"banned:{phrase}")

    for pat in PROMISE_PATTERNS:
        if pat.search(candidate):
            violations.append("promise")

    blocked = answered_slots(state.slot_statuses) + declined_slots(state.slot_statuses)
    if action != PlannerAction.ASK_SLOT:
        violations.extend(_mentions_blocked_slot(candidate, blocked))

    if action == PlannerAction.ASK_SLOT and slot is not None:
        if slot in blocked:
            violations.append(f"ask_blocked_slot:{slot.value}")
        if _count_questions(candidate) > 1:
            violations.append("too_many_questions")
        for other in SLOT_ORDER:
            if other == slot:
                continue
            label = SLOT_LABELS_RU[other]
            if label in low and "?" in candidate:
                violations.append(f"forbidden_slot_question:{other.value}")

    if action == PlannerAction.ANSWER_USER and "?" in candidate:
        violations.append("question_on_answer_user")

    if action == PlannerAction.WAIT and "?" in candidate:
        violations.append("question_on_wait")

    if action == PlannerAction.HANDLE_FATIGUE and "?" in candidate:
        violations.append("question_on_fatigue")

    if action == PlannerAction.HANDLE_REFUSAL and "?" in candidate:
        violations.append("question_on_refusal")

    if action == PlannerAction.HANDLE_CORRECTION and "?" in candidate:
        violations.append("question_on_correction")

    if action == PlannerAction.CLOSE and "?" in candidate:
        violations.append("question_on_close")

    if action not in (PlannerAction.ASK_SLOT, PlannerAction.REPAIR) and _count_questions(candidate) > 1:
        violations.append("too_many_questions")

    if action == PlannerAction.ACK_ONLY and "?" in candidate:
        violations.append("question_on_ack_only")

    for code in check_spoken_quality(candidate):
        violations.append(f"spoken:{code}")

    cleaned = _feminize(candidate)
    if violations:
        if apply_fallback:
            fb = typed_fallback(action, state, slot=slot, answer_type=answer_type)
            return ValidatorResult(ok=False, text=fb, violations=violations, used_fallback=True)
        return ValidatorResult(ok=False, text=cleaned, violations=violations, used_fallback=False)

    return ValidatorResult(ok=True, text=cleaned, violations=[], used_fallback=False)
